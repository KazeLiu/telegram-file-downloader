"""Durable progress and file intent, independent of Telegram's update session."""
from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path


class DownloadHistory:
    def __init__(self, path: Path, scope: str, since: datetime):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.scope = scope
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS transfers (
            scope TEXT NOT NULL, message_id INTEGER NOT NULL, document_id TEXT NOT NULL,
            size INTEGER NOT NULL, parts TEXT NOT NULL, PRIMARY KEY(scope,message_id))""")
        with self.db:
            self.db.execute("""CREATE TABLE IF NOT EXISTS progress (
                scope TEXT PRIMARY KEY, since TEXT NOT NULL,
                message_id INTEGER NOT NULL DEFAULT 0, message_date TEXT,
                checked_at TEXT)""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS downloads (
                scope TEXT NOT NULL, message_id INTEGER NOT NULL,
                path TEXT NOT NULL, ready INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (scope, message_id))""")
            self.db.execute(
                "INSERT OR IGNORE INTO progress(scope, since) VALUES (?, ?)",
                (scope, since.astimezone(timezone.utc).isoformat()),
            )

    @property
    def progress(self):
        return self.db.execute("SELECT * FROM progress WHERE scope = ?", (self.scope,)).fetchone()

    @property
    def since(self) -> datetime:
        return datetime.fromisoformat(self.progress["since"])

    @property
    def message_id(self) -> int:
        return self.progress["message_id"]

    def advance(self, message_id: int, date: datetime) -> None:
        with self.db:
            self.db.execute(
                "UPDATE progress SET message_id = ?, message_date = ? WHERE scope = ? AND message_id < ?",
                (message_id, date.isoformat(), self.scope, message_id),
            )

    def checked(self, date: datetime) -> None:
        with self.db:
            self.db.execute("UPDATE progress SET checked_at = ? WHERE scope = ?", (date.isoformat(), self.scope))

    def download(self, message_id: int):
        return self.db.execute(
            "SELECT * FROM downloads WHERE scope = ? AND message_id = ?", (self.scope, message_id)
        ).fetchone()

    def reserve(self, message_id: int, path: Path) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO downloads(scope, message_id, path, ready) VALUES (?, ?, ?, 0)",
                (self.scope, message_id, str(path)),
            )

    def ready(self, message_id: int) -> None:
        with self.db:
            self.db.execute(
                "UPDATE downloads SET ready = 1 WHERE scope = ? AND message_id = ?", (self.scope, message_id)
            )

    def transfer(self, message_id, document_id, size):
        row = self.db.execute("SELECT * FROM transfers WHERE scope=? AND message_id=?",
                              (self.scope, message_id)).fetchone()
        if row and (row["document_id"] != str(document_id) or row["size"] != size):
            raise ValueError("附件版本已变化，不能复用原下载分片")
        return set(json.loads(row["parts"])) if row else set()

    def save_parts(self, message_id, document_id, size, parts):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO transfers VALUES (?,?,?,?,?)",
                            (self.scope, message_id, str(document_id), size, json.dumps(sorted(parts))))

    def clear_parts(self, message_id):
        with self.db:
            self.db.execute("DELETE FROM transfers WHERE scope=? AND message_id=?", (self.scope, message_id))

    def close(self) -> None:
        self.db.close()
