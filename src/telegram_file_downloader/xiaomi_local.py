"""Read-only folder inventories shared by cloud albums; never read file contents."""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from itertools import islice
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from .storage import internal_directory, is_link

REFRESH_INTERVAL = 6 * 3600


def folder_entries(root):
    pending = [root]
    while pending:
        folder = pending.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                if internal_directory(entry.name):
                    continue
                try:
                    if is_link(entry):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry.name, entry.stat(follow_symlinks=False).st_size
                except FileNotFoundError:
                    continue
            # Yield control even when a tree contains many empty directories.
            yield None


class XiaomiLocalIndex:
    def __init__(self, data_dir, busy):
        self.database = data_dir / "xiaomi-local.sqlite3"
        self.busy = busy
        self.db = sqlite3.connect(self.database)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS roots (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, generation TEXT NOT NULL DEFAULT '',
                updated REAL NOT NULL DEFAULT 0, attempted REAL NOT NULL DEFAULT 0,
                count INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS bindings (
                owner TEXT NOT NULL, album TEXT NOT NULL, root_id TEXT NOT NULL,
                PRIMARY KEY(owner,album));
            CREATE TABLE IF NOT EXISTS files (
                root_id TEXT NOT NULL, generation TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
                PRIMARY KEY(root_id,generation,name,size));
            DELETE FROM files WHERE NOT EXISTS (
                SELECT 1 FROM roots WHERE roots.id=files.root_id AND roots.generation=files.generation);
            UPDATE roots SET attempted=0 WHERE generation='' AND error='';
        """)
        self.db.commit()
        if os.name != "nt":
            self.database.chmod(0o600)
        self.requested = set()
        self.progress = {}
        self.scan_errors = {}
        self.wake = asyncio.Event()
        self.task = None
        self.closing = False

    def start(self):
        self.task = asyncio.create_task(self.run(), name="xiaomi-local-inventory")

    async def close(self):
        self.closing = True
        self.wake.set()
        if self.task:
            await self.task
        self.db.close()

    def bind(self, owner, album, path):
        if not path:
            with self.db:
                self.db.execute("DELETE FROM bindings WHERE owner=? AND album=?", (owner, album))
            return
        folder = Path(path)
        if not folder.is_absolute() or not folder.is_dir():
            raise ValueError("请输入程序所在机器可访问的绝对目录路径；Docker 中需先挂载此目录")
        folder = folder.resolve()
        root_id = uuid4().hex
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO roots(id,path) VALUES (?,?)", (root_id, str(folder)))
            source = self.db.execute("SELECT * FROM roots WHERE path=?", (str(folder),)).fetchone()
            self.db.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?)", (owner, album, source["id"]))
        if not source["generation"]:
            self.requested.add(source["id"])
            self.wake.set()

    def source(self, owner, album):
        return self.db.execute("""SELECT roots.* FROM bindings JOIN roots ON roots.id=bindings.root_id
            WHERE owner=? AND album=?""", (owner, album)).fetchone()

    def refresh(self, owner, album):
        source = self.source(owner, album)
        if not source:
            raise ValueError("请先绑定本地文件夹")
        if source["id"] not in self.progress:
            self.requested.add(source["id"])
            self.wake.set()

    def compare(self, owner, album, items):
        with closing(sqlite3.connect(self.database)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            source = db.execute("""SELECT roots.* FROM bindings JOIN roots ON roots.id=bindings.root_id
                WHERE owner=? AND album=?""", (owner, album)).fetchone()
            if not source:
                return {"binding": None, "states": {}}
            root_id = source["id"]
            state = self.progress.get(root_id, {})
            available = Path(source["path"]).is_dir()
            error = self.scan_errors.get(root_id, source["error"])
            ready = bool(source["generation"]) and available and not error
            binding = {"path": source["path"], "updated": source["updated"], "count": source["count"],
                       "state": state.get("state", "queued" if root_id in self.requested else "ready"),
                       "done": state.get("done", 0), "error": error, "available": available, "ready": ready}
            names = list({item["name"] for item in items})
            known = {}
            if ready and names:
                placeholders = ",".join("?" for _ in names)
                rows = db.execute(f"""SELECT name,size FROM files WHERE root_id=? AND generation=?
                    AND name IN ({placeholders})""", (root_id, source["generation"], *names))
                for row in rows:
                    known.setdefault(row["name"], set()).add(row["size"])
        states = {}
        for item in items:
            sizes = known.get(item["name"], set())
            states[item["id"]] = ("unknown" if not ready or item["size"] is None else
                                  "missing" if not sizes else "same" if item["size"] in sizes else "different")
        return {"binding": binding, "states": states}

    def write_batch(self, root_id, generation, batch):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executemany("INSERT OR IGNORE INTO files VALUES (?,?,?,?)",
                           ((root_id, generation, name, size) for name, size in batch))

    def publish(self, root_id, generation, count):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE roots SET generation=?,updated=?,count=?,error='' WHERE id=?",
                       (generation, time.time(), count, root_id))
            db.execute("DELETE FROM files WHERE root_id=? AND generation<>?", (root_id, generation))

    async def scan(self, source):
        root_id, generation = source["id"], uuid4().hex
        iterator = folder_entries(source["path"])
        count = 0
        self.scan_errors.pop(root_id, None)
        self.progress[root_id] = {"state": "waiting", "done": 0}
        try:
            with self.db:
                self.db.execute("UPDATE roots SET attempted=? WHERE id=?", (time.time(), root_id))
            while not self.closing:
                if not self.db.execute("SELECT 1 FROM bindings WHERE root_id=? LIMIT 1", (root_id,)).fetchone():
                    break
                if self.busy():
                    self.progress[root_id]["state"] = "waiting"
                    await asyncio.sleep(2)
                    continue
                self.progress[root_id]["state"] = "scanning"
                batch = await asyncio.to_thread(lambda: list(islice(iterator, 256)))
                if not batch:
                    await asyncio.to_thread(self.publish, root_id, generation, count)
                    break
                records = [item for item in batch if item is not None]
                await asyncio.to_thread(self.write_batch, root_id, generation, records)
                count += len(records)
                self.progress[root_id]["done"] = count
                await asyncio.sleep(.05)
        except OSError as exc:
            message = f"目录索引未完成：{exc.strerror or type(exc).__name__}"
            self.scan_errors[root_id] = message
            try:
                with self.db:
                    self.db.execute("UPDATE roots SET error=? WHERE id=?", (message, root_id))
            except sqlite3.Error:
                self.scan_errors[root_id] = message + "；索引数据库无法写入"
        except sqlite3.Error:
            self.scan_errors[root_id] = "索引数据库读写失败，请检查数据目录可用空间后更新索引"
        finally:
            iterator.close()
            self.progress.pop(root_id, None)

    async def run(self):
        while not self.closing:
            self.wake.clear()
            sources = self.db.execute("SELECT * FROM roots WHERE EXISTS (SELECT 1 FROM bindings WHERE bindings.root_id=roots.id)").fetchall()
            for source in sources:
                if self.closing:
                    break
                if source["id"] in self.requested or source["attempted"] < time.time() - REFRESH_INTERVAL:
                    self.requested.discard(source["id"])
                    await self.scan(source)
            if not self.closing and not self.wake.is_set():
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=60)
                except TimeoutError:
                    pass
