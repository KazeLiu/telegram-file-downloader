"""Delete expired application recycle files in small, serialized batches."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from .storage import RecycleBin, inside

LOGGER = logging.getLogger(__name__)


def purge_batch(root, after):
    if not root.is_dir():
        raise OSError("回收目录不可访问，请检查挂载")
    if not inside(root, ".tg-trash/index.sqlite3").is_file():
        return dict(removed=0, errors=[], after=None)
    with RecycleBin(root) as recycle:
        return recycle.purge_expired(after)


class RecycleCleaner:
    def __init__(self, local_index, download_dir, operation_lock):
        self.index, self.root, self.lock = local_index, download_dir, operation_lock
        self.stop = asyncio.Event()
        self.task = None
        self.state = dict(running=False, checked=0, removed=0, failed=0)

    def start(self):
        self.task = asyncio.create_task(self.run(), name="recycle-expiry")

    async def close(self):
        self.stop.set()
        if self.task:
            await self.task

    async def wait(self, seconds):
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def run(self):
        while not self.stop.is_set():
            self.state.update(running=True, removed=0, failed=0)
            try:
                sources = self.index.recycle_roots(self.root)
            except sqlite3.Error as exc:
                self.state.update(running=False, failed=1)
                LOGGER.warning("recycle directories unavailable: %s", exc)
                await self.wait(60)
                continue
            for source in sources:
                after = None
                while not self.stop.is_set():
                    if self.lock.locked():
                        await self.wait(5)
                        continue
                    try:
                        async with self.lock:
                            result = await asyncio.to_thread(purge_batch, Path(source["path"]), after)
                    except (OSError, ValueError, sqlite3.Error) as exc:
                        self.state["failed"] += 1
                        LOGGER.warning("recycle cleanup failed root=%s: %s", source["path"], exc)
                        break
                    self.state["removed"] += result["removed"]
                    self.state["failed"] += len(result["errors"])
                    for error in result["errors"]:
                        LOGGER.warning("recycle cleanup failed root=%s id=%s: %s", source["path"], error["id"], error["error"])
                    after = result["after"]
                    if not after:
                        break
                    await asyncio.sleep(.05)
            self.state.update(running=False, checked=time.time())
            LOGGER.info("recycle cleanup complete removed=%s failed=%s", self.state["removed"], self.state["failed"])
            await self.wait(3600)
