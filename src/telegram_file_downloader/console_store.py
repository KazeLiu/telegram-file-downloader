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

from .organizer import restore_progress, plan_counts
from .archive_groups import archive_set_updates, task_view


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
            CREATE INDEX IF NOT EXISTS task_archive_set ON tasks(json_extract(data,'$.archive_set'));
            CREATE INDEX IF NOT EXISTS task_volume_signature ON tasks(scope,json_extract(data,'$.volume_signature'));
        """)
        self.db.commit()
        settings = self.get("settings", {})
        if "delete_pdf" in settings:
            settings.pop("delete_pdf")
            self.put("settings", settings)
        manual = self.get("manual_job", {})
        if "plan" in manual:
            plan = manual.pop("plan")
            manual.update(plan_key=f"manual_preview:{manual['token']}", summary=plan_counts(plan))
            self.put_plan(manual["plan_key"], plan)
        if manual.get("status") == "running":
            manual["status"] = "interrupted"
        if manual:
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
        self.refresh_archive_sets()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    def get_plan(self, key):
        plan = self.get(key)
        return restore_progress(plan, self.get(f"progress:{key}", {})) if plan else None

    def put_plan(self, key, plan):
        # Snapshot and cursor reset are atomic; each intervening file commits only a small cursor.
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(plan)))
            self.db.execute("DELETE FROM kv WHERE key = ?", (f"progress:{key}",))

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
                    attempts=0, result_files=0, deleted_psds=0, deleted_txts=0, recycled_psds=0, recycled_txts=0)
        with self.db:
            cursor = self.db.execute("INSERT INTO tasks(scope,message_id,status,filename,data) VALUES (?,?,?,?,?)",
                                     (scope, message_id, "queued", filename, "{}"))
            data["id"] = cursor.lastrowid
            self.db.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(data), data["id"]))
        return data

    def update_task(self, task_id, **changes):
        return self.update_tasks([(task_id, changes)])[0]

    def update_tasks(self, changes):
        updated = []
        with self.db:
            for task_id, values in changes:
                data = self.task(task_id)
                data.update(values)
                data["updated_at"] = now()
                self.db.execute("UPDATE tasks SET status = ?, data = ? WHERE id = ?",
                                (data["status"], json.dumps(data, ensure_ascii=False), task_id))
                updated.append(data)
        return updated

    def refresh_archive_sets(self, scope=None, signature=None):
        conditions, args = ["json_extract(data,'$.kind')='archive'"], []
        if scope is not None:
            conditions.append("scope=?")
            args.append(scope)
        if signature is not None:
            conditions.append("json_extract(data,'$.volume_signature')=?")
            args.append(signature)
        rows = self.db.execute("SELECT data FROM tasks WHERE " + " AND ".join(conditions) + " ORDER BY id", args).fetchall()
        tasks = {item["id"]: item for row in rows if (item := json.loads(row[0]))}
        changes = [(task_id, values) for task_id, values in archive_set_updates(tasks.values())
                   if any(tasks[task_id].get(key) != value for key, value in values.items())]
        self.update_tasks(changes)

    def archive_members(self, task):
        if task.get("archive_set"):
            return [json.loads(row[0]) for row in self.db.execute(
                "SELECT data FROM tasks WHERE json_extract(data,'$.archive_set')=? ORDER BY id", (task["archive_set"],))]
        return self.group(task["group_id"]) if task.get("group_id") else [task]

    def task_view(self, task):
        return task_view(task, self.archive_members(task))

    def history(self, page=1, status="", search=""):
        grouped = """WITH grouped AS (
            SELECT MIN(id) AS leader, MAX(id) AS latest FROM tasks
            GROUP BY COALESCE(json_extract(data,'$.archive_set'),'task:'||id)
            HAVING (?='' OR MAX(status=?)=1) AND (?='' OR MAX(instr(lower(filename),lower(?))>0)=1)) """
        args = (status, status, search, search)
        count = self.db.execute(grouped + "SELECT COUNT(*) FROM grouped", args).fetchone()[0]
        rows = self.db.execute(grouped + "SELECT tasks.data FROM grouped JOIN tasks ON tasks.id=grouped.leader ORDER BY grouped.latest DESC LIMIT 25 OFFSET ?",
                               (*args, (page - 1) * 25)).fetchall()
        return {"items": [self.task_view(json.loads(row[0])) for row in rows], "total": count, "page": page, "page_size": 25}

    def tasks(self, scope=None, statuses=None):
        condition = " AND status IN (" + ",".join("?" for _ in statuses) + ")" if statuses else ""
        rows = self.db.execute("SELECT data FROM tasks WHERE (? IS NULL OR scope=?)" + condition + " ORDER BY id",
                               (scope, scope, *(statuses or [])))
        return [json.loads(row[0]) for row in rows]

    def volume_candidate(self, scope, signature, album):
        rows = self.db.execute("""SELECT data FROM tasks WHERE scope=?
            AND json_extract(data,'$.volume_signature')=?
            AND COALESCE(json_extract(data,'$.manual_extract_only'),0)=0
            AND status NOT IN ('completed','extracted','organized','manual_extracted') ORDER BY id DESC""",
            (scope, signature)).fetchall()
        tasks = [json.loads(row[0]) for row in rows]
        exact = [task for task in tasks if album and task.get("album_id") == album]
        candidates = exact or tasks
        return candidates[0] if len({task["group_id"] for task in candidates}) == 1 else None

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
