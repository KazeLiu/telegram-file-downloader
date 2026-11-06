"""Download-mount path boundaries and a persistent, recoverable application recycle bin."""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

LOGGER = logging.getLogger(__name__)
TRASH_DIRECTORY = ".tg-trash"
RETENTION_SECONDS = 15 * 86400


def file_version(stat):
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"


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
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for record in self.db.execute("SELECT * FROM items WHERE state IN ('pending','restoring')").fetchall():
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
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT state FROM items WHERE id=?", (record_id,)).fetchone()[0] == "restored":
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
        LOGGER.info("recycle moved id=%s source=%s reason=%s", record_id, relative, reason)
        return record_id

    def listing(self, page=1, windows=False):
        states = "('windows')" if windows else "('trashed','restoring','exporting')"
        total = self.db.execute(f"SELECT COUNT(*) FROM items WHERE state IN {states}").fetchone()[0]
        rows = self.db.execute(f"SELECT * FROM items WHERE state IN {states} ORDER BY created DESC,id LIMIT 50 OFFSET ?",
                               ((page - 1) * 50,)).fetchall()
        return dict(items=[dict(row) for row in rows], total=total, page=page, page_size=50)

    def restore(self, record_id):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
            if not record or record["state"] not in {"trashed", "restoring", "windows"}:
                raise ValueError("回收文件不存在、已还原或正在转入 Windows 回收站")
            original, target = self._paths(record)
            if not target.is_file():
                raise ValueError("找不到回收文件；已转入 Windows 的文件需先从系统回收站还原，再恢复原路径")
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
        LOGGER.info("recycle restored id=%s target=%s", record_id, record["original"])
        return record["original"]

    def prepare_windows(self, record_id):
        if not re.fullmatch(r"[a-f0-9]{32}(?:-[0-9]+)?", record_id):
            raise ValueError("无效的回收记录")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
            if not record or record["state"] not in {"trashed", "exporting"}:
                raise ValueError("文件已还原或不再等待转移")
            _, source = self._paths(record)
            ticket_file = inside(self.root, f"{TRASH_DIRECTORY}/handoff/{record_id}.json")
            if record["state"] == "trashed":
                info = source.stat()
                if max(record["created"], info.st_mtime) > time.time() - RETENTION_SECONDS:
                    raise ValueError("文件在回收站内尚未静置满 15 天")
                ticket_file.parent.mkdir(parents=True, exist_ok=True)
                ticket = dict(nonce=uuid4().hex, id=record_id, original=record["original"], created=record["created"],
                              path=source.relative_to(self.root).as_posix(), size=info.st_size, mtime=info.st_mtime)
                temporary = inside(self.root, f"{TRASH_DIRECTORY}/handoff/{record_id}.tmp")
                temporary.write_text(json.dumps(ticket, ensure_ascii=False), encoding="utf-8")
                temporary.replace(ticket_file)
                self.db.execute("UPDATE items SET state='exporting' WHERE id=?", (record_id,))
            return json.loads(ticket_file.read_text(encoding="utf-8"))

    def finish_windows(self, record_id, success):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            record = self.db.execute("SELECT * FROM items WHERE id=?", (record_id,)).fetchone()
            if not record or record["state"] != "exporting":
                raise ValueError("文件不在 Windows 交接状态")
            _, file = self._paths(record)
            if success:
                if file.exists():
                    raise ValueError("回收文件仍在原处，不能确认转移成功")
                ticket = json.loads(inside(self.root, f"{TRASH_DIRECTORY}/handoff/{record_id}.json").read_text(encoding="utf-8"))
                receipt = json.loads(inside(self.root, f"{TRASH_DIRECTORY}/handoff/{record_id}.receipt.json").read_text(encoding="utf-8"))
                if receipt.get("nonce") != ticket["nonce"] or not receipt.get("destination"):
                    raise ValueError("Windows 交接凭据不匹配，不能确认转移成功")
                self.db.execute("UPDATE items SET state='windows' WHERE id=?", (record_id,))
            else:
                if not file.is_file():
                    raise ValueError("转移结果未确认，文件不在原处；请检查 Windows 回收站和交接凭据")
                self.db.execute("UPDATE items SET state='trashed' WHERE id=?", (record_id,))
