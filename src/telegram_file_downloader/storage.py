"""Download-mount path boundaries and a persistent, recoverable application recycle bin."""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)
TRASH_DIRECTORY = ".tg-trash"


def internal_directory(name):
    name = name.casefold()
    return name in {".tg-work", TRASH_DIRECTORY} or name.startswith(".tg-extract-")


def inside(root: Path, value: str = "") -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("请选择下载目录内的路径")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (current.exists() and getattr(current.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("不允许操作链接目录或文件")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("路径超出下载目录")
    return current


def is_link(entry):
    return entry.is_symlink() or (os.name == "nt" and entry.stat(follow_symlinks=False).st_file_attributes & 0x400)


class RecycleBin:
    def __init__(self, root):
        self.root = root
        self.folder = inside(root, TRASH_DIRECTORY)
        self.files = inside(root, f"{TRASH_DIRECTORY}/files")
        self.files.mkdir(parents=True, exist_ok=True)
        database = inside(root, f"{TRASH_DIRECTORY}/index.sqlite3")
        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY, original TEXT NOT NULL, size INTEGER NOT NULL,
                created REAL NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS recycle_state_created ON items(state,created);
        """)
        self._recover()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def _paths(self, record):
        original = inside(self.root, record["original"])
        target = inside(self.root, f"{TRASH_DIRECTORY}/files/{record['id']}")
        return original, target

    def _state(self, record_id, state):
        with self.db:
            self.db.execute("UPDATE items SET state=? WHERE id=?", (state, record_id))

    def _recover(self):
        for record in self.db.execute("SELECT * FROM items WHERE state IN ('pending','restoring')").fetchall():
            original, target = self._paths(record)
            if record["state"] == "pending" and target.is_file():
                if original.exists() and original.samefile(target):
                    original.unlink()
                self._state(record["id"], "trashed")
            elif record["state"] == "restoring" and original.is_file():
                if target.exists():
                    if not original.samefile(target):
                        continue
                    target.unlink()
                self._state(record["id"], "restored")

    def move(self, file, record_id, reason):
        if not re.fullmatch(r"[a-f0-9]{32}(?:-[0-9]+)?", record_id):
            raise ValueError("无效的回收记录")
        relative = file.relative_to(self.root).as_posix()
        if relative.split("/")[0].casefold() == TRASH_DIRECTORY:
            raise ValueError("不能再次回收回收站中的文件")
        file = inside(self.root, relative)
        record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
        if record:
            if record["original"] != relative:
                raise ValueError("回收记录与源文件不一致")
            if record["state"] == "restored":
                return record_id  # A replay must not undo the user's subsequent restoration.
        else:
            if not file.is_file():
                raise ValueError(f"待回收文件不存在：{relative}")
            with self.db:
                self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?)",
                                (record_id, relative, file.stat().st_size, time.time(), reason, "pending"))
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
        _, target = self._paths(record)
        if file.exists():
            if target.exists():
                if not file.samefile(target):
                    raise ValueError("源文件已变化，已停止回收；原回收文件保留")
            else:
                os.link(file, target)
            if not file.samefile(target):
                raise ValueError("源文件在回收期间发生变化，已保留两边的文件")
            file.unlink()
        elif not target.is_file():
            raise ValueError("源文件和回收副本均不存在，请检查下载挂载")
        self._state(record_id, "trashed")
        LOGGER.info("recycle moved id=%s source=%s reason=%s", record_id, relative, reason)
        return record_id

    def listing(self, page=1):
        total = self.db.execute("SELECT COUNT(*) FROM items WHERE state IN ('trashed','restoring')").fetchone()[0]
        rows = self.db.execute("SELECT * FROM items WHERE state IN ('trashed','restoring') ORDER BY created DESC,id LIMIT 50 OFFSET ?",
                               ((page - 1) * 50,)).fetchall()
        return dict(items=[dict(row) for row in rows], total=total, page=page, page_size=50)

    def restore(self, record_id):
        record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
        if not record or record["state"] not in {"trashed", "restoring"}:
            raise ValueError("回收文件不存在或已还原")
        original, target = self._paths(record)
        if not target.is_file():
            raise ValueError("找不到回收文件，请检查下载挂载")
        if original.exists() and not original.samefile(target):
            raise ValueError("原位置已存在同名文件，还原不会覆盖；请先处理该文件")
        self._state(record_id, "restoring")
        original.parent.mkdir(parents=True, exist_ok=True)
        inside(self.root, record["original"])
        if not original.exists():
            os.link(target, original)
        if not original.samefile(target):
            raise ValueError("原位置在还原期间发生变化，回收文件已保留")
        target.unlink()
        self._state(record_id, "restored")
        LOGGER.info("recycle restored id=%s target=%s", record_id, record["original"])
        return record["original"]
