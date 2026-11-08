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
RETENTION_SECONDS = 15 * 86400


def file_version(stat):
    # Windows stat/fstat can disagree on ctime; birthtime preserves the existing creation-time contract.
    changed = getattr(stat, "st_birthtime_ns", stat.st_ctime_ns) if os.name == "nt" else stat.st_ctime_ns
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{changed}"


def internal_directory(name):
    name = name.casefold()
    return name in {".tg-work", TRASH_DIRECTORY} or name.startswith(".tg-extract-")


def inside(root: Path, value: str = "") -> Path:
    if root.resolve() != root.absolute():
        raise ValueError("根目录路径已变化或变为链接，请重新确认目录")
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


def restore_batch(root, ids):
    restored, failures = [], []
    with RecycleBin(root) as recycle:
        for record_id in dict.fromkeys(ids):
            try:
                recycle.restore(record_id)
                restored.append(record_id)
            except (OSError, ValueError) as exc:
                failures.append(dict(id=record_id, error=str(exc)))
    LOGGER.log(logging.WARNING if failures else logging.INFO,
               "recycle restore batch finished restored=%s failed=%s", len(restored), len(failures))
    return dict(restored=restored, failures=failures)


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

    def _recover(self):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for record in self.db.execute("SELECT * FROM items WHERE state IN ('pending','restoring','purging','exporting','windows')").fetchall():
                original, target = self._paths(record)
                if record["state"] == "pending" and target.is_file():
                    if original.exists() and original.samefile(target):
                        original.unlink()
                    self.db.execute("UPDATE items SET state='trashed' WHERE id=?", (record["id"],))
                elif record["state"] == "restoring" and original.is_file():
                    if target.exists():
                        if not original.samefile(target):
                            continue
                        target.unlink()
                    self.db.execute("UPDATE items SET state='restored' WHERE id=?", (record["id"],))
                elif record["state"] == "purging" and not target.exists():
                    self.db.execute("UPDATE items SET state='purged' WHERE id=?", (record["id"],))
                elif record["state"] in {"exporting", "windows"} and target.is_file():
                    self.db.execute("UPDATE items SET state='trashed',created=? WHERE id=?", (time.time(), record["id"]))

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
            if record["state"] in {"restored", "purged"}:
                return record_id  # A replay must not undo the user's subsequent restoration.
        else:
            if not file.is_file():
                raise ValueError(f"待回收文件不存在：{relative}")
            with self.db:
                self.db.execute("INSERT INTO items VALUES (?,?,?,?,?,?)",
                                (record_id, relative, file.stat().st_size, time.time(), reason, "pending"))
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT state FROM items WHERE id=?", (record_id,)).fetchone()[0] in {"restored", "purged"}:
                return record_id
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
            self.db.execute("UPDATE items SET state='trashed' WHERE id=?", (record_id,))
        LOGGER.debug("recycle moved id=%s source=%s reason=%s", record_id, relative, reason)
        return record_id

    def listing(self, page=1):
        states = "('trashed','restoring','purging','exporting')"
        total = self.db.execute(f"SELECT COUNT(*) FROM items WHERE state IN {states}").fetchone()[0]
        rows = self.db.execute(f"SELECT * FROM items WHERE state IN {states} ORDER BY created DESC,id LIMIT 50 OFFSET ?",
                               ((page - 1) * 50,)).fetchall()
        return dict(items=[dict(row) for row in rows], total=total, page=page, page_size=50)

    def preview(self, record_id):
        record = self.db.execute("SELECT * FROM items WHERE id=? AND state IN ('trashed','restoring','purging')", (record_id,)).fetchone()
        if not record:
            raise ValueError("回收文件不存在或不可预览")
        _, file = self._paths(record)
        if not file.is_file() or file.stat().st_size != record["size"]:
            raise ValueError("回收文件缺失或大小已变化")
        return dict(record), file

    def restore(self, record_id):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
            if not record or record["state"] not in {"trashed", "restoring", "purging"}:
                raise ValueError("回收文件不存在、已还原或已永久删除")
            original, target = self._paths(record)
            if not target.is_file():
                raise ValueError("找不到回收文件，可能已永久删除或被移走")
            if target.stat().st_size != record["size"]:
                raise ValueError("回收文件大小已变化，已停止还原")
            if original.exists() and not original.samefile(target):
                raise ValueError("原位置已存在同名文件，还原不会覆盖；请先处理该文件")
            self.db.execute("UPDATE items SET state='restoring' WHERE id=?", (record_id,))
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            state = self.db.execute("SELECT state FROM items WHERE id=?", (record_id,)).fetchone()[0]
            if state != "restored":
                original.parent.mkdir(parents=True, exist_ok=True)
                inside(self.root, record["original"])
                if not original.exists():
                    os.link(target, original)
                if not original.samefile(target):
                    raise ValueError("原位置在还原期间发生变化，回收文件已保留")
                target.unlink()
                self.db.execute("UPDATE items SET state='restored' WHERE id=?", (record_id,))
        LOGGER.debug("recycle restored id=%s target=%s", record_id, record["original"])
        return record["original"]

    def purge_expired(self, after=None):
        cutoff = time.time() - RETENTION_SECONDS
        query = "SELECT * FROM items WHERE state IN ('trashed','purging') AND created<=?"
        parameters = [cutoff]
        if after:
            query += " AND (created,id)>(?,?)"
            parameters.extend(after)
        records = self.db.execute(query + " ORDER BY created,id LIMIT 100", parameters).fetchall()
        removed, errors = 0, []
        for record in records:
            try:
                with self.db:
                    self.db.execute("BEGIN IMMEDIATE")
                    current = self.db.execute("SELECT * FROM items WHERE id=?", (record["id"],)).fetchone()
                    if current["state"] not in {"trashed", "purging"} or current["created"] > cutoff:
                        continue
                    _, file = self._paths(current)
                    info = file.stat()
                    if not file.is_file() or info.st_size != current["size"]:
                        raise ValueError("回收文件大小或类型已变化，已停止清理")
                    if info.st_mtime > cutoff:
                        continue
                    self.db.execute("UPDATE items SET state='purging' WHERE id=?", (record["id"],))
                with self.db:
                    self.db.execute("BEGIN IMMEDIATE")
                    state = self.db.execute("SELECT state FROM items WHERE id=?", (record["id"],)).fetchone()[0]
                    if state != "purging":
                        continue
                    _, file = self._paths(current)
                    info = file.stat()
                    if info.st_mtime > cutoff or info.st_size != current["size"]:
                        self.db.execute("UPDATE items SET state='trashed' WHERE id=?", (record["id"],))
                        continue
                    file.unlink()
                    self.db.execute("UPDATE items SET state='purged' WHERE id=?", (record["id"],))
                removed += 1
                LOGGER.info("recycle permanently deleted id=%s original=%s", record["id"], record["original"])
            except (OSError, ValueError, sqlite3.Error) as exc:
                errors.append(dict(id=record["id"], error=str(exc)))
        cursor = (records[-1]["created"], records[-1]["id"]) if len(records) == 100 else None
        return dict(removed=removed, errors=errors, after=cursor)
