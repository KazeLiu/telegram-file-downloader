"""Private settings and task journal for the web console (single event-loop owner)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS = {
    "api_id": "", "api_hash": "", "chat": "", "chat_title": "",
    "proxy_type": "socks5", "proxy_host": "", "proxy_port": "",
    "proxy_username": "", "proxy_password": "",
    "videos": True, "photos": False, "archives": True,
    "extract": True, "delete_archive": False, "archive_passwords": [],
    "receipts": True, "mark_read": True, "enabled": False,
}
SECRET_KEYS = {"api_hash", "proxy_password", "archive_passwords"}


class ConsoleStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        database = directory / "console.sqlite3"
        self.db = sqlite3.connect(database)
        if os.name != "nt":
            database.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY, scope TEXT NOT NULL, message_id INTEGER NOT NULL,
                status TEXT NOT NULL, filename TEXT NOT NULL, data TEXT NOT NULL,
                UNIQUE(scope, message_id));
        """)
        self.db.commit()
        with self.db:
            rows = self.db.execute("SELECT id, data FROM tasks WHERE status IN ('queued','downloading','downloaded','extracting')").fetchall()
            for row in rows:
                data = json.loads(row["data"])
                data.update(status="interrupted", speed=0, eta=None)
                self.db.execute("UPDATE tasks SET status = 'interrupted', data = ? WHERE id = ?",
                                (json.dumps(data), row["id"]))

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    def settings(self):
        return {**DEFAULT_SETTINGS, **self.get("settings", {})}

    def public_settings(self):
        settings = self.settings()
        public = {k: v for k, v in settings.items() if k not in SECRET_KEYS}
        public.update(api_hash_saved=bool(settings["api_hash"]),
                      proxy_password_saved=bool(settings["proxy_password"]),
                      archive_passwords_count=len(settings["archive_passwords"]))
        return public

    def set_password(self, password: str):
        if not 10 <= len(password) <= 256:
            raise ValueError("管理密码需要 10–256 个字符")
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
        self.put("admin", {"salt": salt, "digest": digest})
        with self.db:
            self.db.execute("DELETE FROM sessions")

    def check_password(self, password: str):
        admin = self.get("admin")
        if not admin or len(password) > 256:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(admin["salt"]), 600_000).hex()
        return hmac.compare_digest(digest, admin["digest"])

    def session(self):
        token = secrets.token_urlsafe(32)
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            self.db.execute("INSERT INTO sessions VALUES (?, ?)",
                            (hashlib.sha256(token.encode()).hexdigest(), time.time() + 7 * 86400))
        return token

    def authorized(self, token: str):
        return self.db.execute("SELECT 1 FROM sessions WHERE token = ? AND expires > ?",
                               (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone() is not None

    def revoke(self, token):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE token = ?", (hashlib.sha256(token.encode()).hexdigest(),))

    def task(self, task_id):
        row = self.db.execute("SELECT data FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def find(self, scope, message_id):
        row = self.db.execute("SELECT data FROM tasks WHERE scope = ? AND message_id = ?",
                              (scope, message_id)).fetchone()
        return json.loads(row[0]) if row else None

    def create_task(self, scope, message_id, filename, kind, size, quality):
        existing = self.find(scope, message_id)
        if existing:
            return existing
        data = dict(scope=scope, message_id=message_id, filename=filename, kind=kind, size=size or 0,
                    quality=quality, status="queued", created_at=now(), started_at=None,
                    completed_at=None, downloaded=0, speed=0, average_speed=0, eta=None,
                    elapsed=0, path="", output="", archive_deleted=False, error="", warning="",
                    receipt_id=None)
        with self.db:
            cursor = self.db.execute("INSERT INTO tasks(scope,message_id,status,filename,data) VALUES (?,?,?,?,?)",
                                     (scope, message_id, "queued", filename, "{}"))
            data["id"] = cursor.lastrowid
            self.db.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(data), data["id"]))
        return data

    def update_task(self, task_id, **changes):
        data = self.task(task_id)
        data.update(changes)
        data["updated_at"] = now()
        with self.db:
            self.db.execute("UPDATE tasks SET status = ?, data = ? WHERE id = ?",
                            (data["status"], json.dumps(data, ensure_ascii=False), task_id))
        return data

    def history(self, page=1, status="", search=""):
        condition = "WHERE (? = '' OR status = ?) AND (? = '' OR instr(lower(filename), lower(?)) > 0)"
        args = (status, status, search, search)
        count = self.db.execute(f"SELECT COUNT(*) FROM tasks {condition}", args).fetchone()[0]
        rows = self.db.execute(f"SELECT data FROM tasks {condition} ORDER BY id DESC LIMIT 25 OFFSET ?",
                               (*args, (page - 1) * 25)).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": count, "page": page, "page_size": 25}

    def summary(self):
        rows = self.db.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
        counts = {row["status"]: row["n"] for row in rows}
        active = self.db.execute("SELECT data FROM tasks WHERE status IN ('downloading','extracting','queued') ORDER BY id LIMIT 1").fetchone()
        total_bytes = self.db.execute("SELECT COALESCE(SUM(json_extract(data, '$.downloaded')), 0) FROM tasks").fetchone()[0]
        return dict(counts=counts, total_bytes=total_bytes, active=json.loads(active[0]) if active else None)

    def close(self):
        self.db.close()
