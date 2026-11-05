"""Bounded document transfers over the existing Telegram account and proxy."""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from telethon import errors
# Pinned Telethon 1.44 exposes this through iter_download; download_media owns CDN handling.
from telethon.client.downloads import _CdnRedirect

LOGGER = logging.getLogger(__name__)
PART_SIZE = 512 * 1024
FLOOD_ERRORS = (errors.FloodWaitError, errors.FloodPremiumWaitError)


async def notify(callback, *args):
    if callback:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result


class TransferThrottle:
    def __init__(self, parallelism=1, saved=None, persist=None):
        saved = saved or {}
        self.until = float(saved.get("until", 0))
        remaining = max(0, self.until - time.time())
        self.deadline = time.monotonic() + remaining
        self.parallelism = min(parallelism, int(saved.get("parallelism", parallelism))) if remaining else parallelism
        self.reason = saved.get("reason", "flood")
        self.active = 0
        self.condition = asyncio.Condition()
        self.persist = persist

    @asynccontextmanager
    async def request(self, on_wait=None):
        async with self.condition:
            while True:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0 and self.active < self.parallelism:
                    self.active += 1
                    break
                if remaining > 0:
                    await notify(on_wait, self.until, self.reason, self.parallelism)
                    try:
                        await asyncio.wait_for(self.condition.wait(), remaining)
                    except TimeoutError:
                        pass
                else:
                    await self.condition.wait()
        try:
            yield
        except FLOOD_ERRORS as exc:
            # Publish the pause before releasing this slot to another waiting worker.
            await self.pause(exc)
            raise
        finally:
            async with self.condition:
                self.active -= 1
                self.condition.notify_all()

    async def pause(self, error):
        async with self.condition:
            self.deadline = max(self.deadline, time.monotonic() + max(1, error.seconds))
            self.until = time.time() + max(0, self.deadline - time.monotonic())
            self.parallelism = max(1, self.parallelism // 2)
            self.reason = "premium" if isinstance(error, errors.FloodPremiumWaitError) else "flood"
            if self.persist:
                self.persist(dict(until=self.until, parallelism=self.parallelism, reason=self.reason))
            self.condition.notify_all()
        LOGGER.warning("Telegram requested a transfer pause for %s seconds; concurrency reduced to %s",
                       error.seconds, self.parallelism)


async def download_document(client, message, destination: Path, parallelism, throttle, progress, on_wait):
    document = message.document
    file_size = document.size
    part_count = (file_size + PART_SIZE - 1) // PART_SIZE
    worker_count = min(parallelism, part_count)
    downloaded = 0
    completed_parts = 0
    refresh_lock = asyncio.Lock()

    async def refresh_reference(failed_reference):
        nonlocal document
        async with refresh_lock:
            if document.file_reference != failed_reference:
                return
            while True:
                try:
                    async with throttle.request(on_wait):
                        fresh = await client.get_messages(message.chat_id, ids=message.id)
                    break
                except FLOOD_ERRORS:
                    continue
            media = getattr(fresh, "media", None)
            candidates = [getattr(media, "document", None), *(getattr(media, "alt_documents", None) or [])]
            match = next((item for item in candidates if item and item.id == document.id), None)
            if not match or match.size != file_size:
                raise RuntimeError("Telegram 附件已变化或无法访问，无法继续同一文件")
            document = match

    with destination.open("wb") as output:
        await notify(progress, 0, file_size)

        async def worker(index):
            nonlocal downloaded, completed_parts
            refreshed = False
            while index < part_count:
                reference = document.file_reference
                remaining = (part_count - 1 - index) // worker_count + 1
                iterator = client.iter_download(document, offset=index * PART_SIZE, stride=worker_count * PART_SIZE,
                    limit=remaining, chunk_size=PART_SIZE, request_size=PART_SIZE, file_size=file_size)
                try:
                    while index < part_count:
                        try:
                            async with throttle.request(on_wait):
                                chunk = await iterator.__anext__()
                        except StopAsyncIteration as exc:
                            raise RuntimeError("Telegram 提前结束下载，分片尚未完整") from exc
                        offset = index * PART_SIZE
                        expected = min(PART_SIZE, file_size - offset)
                        if len(chunk) != expected:
                            raise RuntimeError("Telegram 下载分片大小不匹配")
                        # All workers share this event loop: seek/write must stay together without an await.
                        output.seek(offset)
                        written = output.write(chunk)
                        if written != expected:
                            raise OSError("下载分片未完整写入磁盘")
                        downloaded += written
                        completed_parts += 1
                        index += worker_count
                        refreshed = False
                        await notify(progress, downloaded, file_size)
                except FLOOD_ERRORS:
                    continue
                except (errors.FilerefUpgradeNeededError, errors.FileReferenceExpiredError):
                    if refreshed:
                        raise
                    await refresh_reference(reference)
                    refreshed = True
                finally:
                    # Telethon can fail exporting a DC sender before assigning it to the iterator.
                    if getattr(iterator, "_sender", None) is not None:
                        await iterator.close()

        tasks = [asyncio.create_task(worker(index)) for index in range(worker_count)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if completed_parts != part_count or downloaded != file_size:
            raise RuntimeError("Telegram 下载分片不完整")
    return str(destination)


async def transfer_media(client, message, destination, parallelism=None, throttle=None,
                         progress=None, on_wait=None, on_notice=None):
    throttle = throttle or TransferThrottle(parallelism or 1)
    document = getattr(message, "document", None)
    if parallelism and document and document.size:
        try:
            return await download_document(client, message, destination, parallelism, throttle, progress, on_wait)
        except _CdnRedirect:
            LOGGER.info("Telegram CDN redirect: using Telethon's standard CDN download path")
            await notify(on_notice, "此文件由 Telegram CDN 分发，使用标准下载路径处理")
    while True:
        try:
            async with throttle.request(on_wait):
                options = {"progress_callback": progress} if progress else {}
                return await client.download_media(message, file=str(destination), **options)
        except FLOOD_ERRORS:
            continue
