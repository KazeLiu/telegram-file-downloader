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
    "download_parallelism": 4,
    # delete_psd retains its stored/API name and controls PSD and TXT together.
    "parallel_files": 5, "flatten": True, "delete_psd": True,
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
            CREATE INDEX IF NOT EXISTS task_status_scope ON tasks(status,scope);
        """)
        self.db.commit()
        settings = self.get("settings", {})
        if "delete_pdf" in settings:
            settings.pop("delete_pdf")
            self.put("settings", settings)
        manual = self.get("manual_job", {})
        if manual.get("status") == "running":
            manual["status"] = "interrupted"
            self.put("manual_job", manual)
        with self.db:
            rows = self.db.execute("SELECT id, data FROM tasks WHERE status IN ('queued','downloading','waiting','retrying','downloaded','extracting','organizing')").fetchall()
            for row in rows:
                data = json.loads(row["data"])
                data.update(status="interrupted", speed=0, eta=None, wait_until=None)
                self.db.execute("UPDATE tasks SET status = 'interrupted', data = ? WHERE id = ?",
                                (json.dumps(data), row["id"]))
            rows = self.db.execute("SELECT id,data FROM tasks WHERE json_extract(data,'$.stage') IN ('pdf','psd') AND status NOT IN ('completed','extracted','organized')").fetchall()
            for row in rows:
                data = json.loads(row["data"])
                data["stage"] = "cleanup"
                data.setdefault("steps", {}).pop("pdf", None)
                data["steps"].pop("psd", None)
                self.db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(data), row["id"]))

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
        data.update(wait_until=None, wait_reason="", parallelism=None)
        data.update(group_id="", volume=None, stage="download", steps={}, last_progress_at=None,
                    attempts=0, result_files=0, deleted_psds=0, deleted_txts=0)
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

    def tasks(self, scope=None, statuses=None):
        condition = " AND status IN (" + ",".join("?" for _ in statuses) + ")" if statuses else ""
        rows = self.db.execute("SELECT data FROM tasks WHERE (? IS NULL OR scope=?)" + condition + " ORDER BY id",
                               (scope, scope, *(statuses or [])))
        return [json.loads(row[0]) for row in rows]

    def volume_candidate(self, scope, signature, album):
        row = self.db.execute("""SELECT data FROM tasks WHERE scope=?
            AND json_extract(data,'$.volume_signature')=? AND json_extract(data,'$.album_id')=?
            AND status NOT IN ('completed','extracted','organized') ORDER BY id DESC LIMIT 1""",
            (scope, signature, album)).fetchone()
        return json.loads(row[0]) if row else None

    def group(self, group_id):
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT data FROM tasks WHERE json_extract(data,'$.group_id')=? ORDER BY id", (group_id,))]

    def summary(self):
        rows = self.db.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
        counts = {row["status"]: row["n"] for row in rows}
        active = [json.loads(row[0]) for row in self.db.execute("SELECT data FROM tasks WHERE status IN ('downloading','waiting','retrying','extracting','organizing','queued','waiting_volumes','paused','interrupted') ORDER BY CASE WHEN status IN ('downloading','waiting','retrying','extracting','organizing') THEN 0 WHEN status='queued' THEN 1 ELSE 2 END, id LIMIT 100")]
        total_bytes = self.db.execute("SELECT COALESCE(SUM(json_extract(data, '$.downloaded')), 0) FROM tasks").fetchone()[0]
        return dict(counts=counts, total_bytes=total_bytes, active=active[0] if active else None,
                    active_tasks=active, queue_paused=bool(self.get("queue_paused", False)))

    def close(self):
        self.db.close()
