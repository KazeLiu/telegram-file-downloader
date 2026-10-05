from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from .files import collision_safe_path, message_filename
from .history import DownloadHistory

LOGGER = logging.getLogger(__name__)


class DownloadQueue:
    def __init__(self, client: object, directory: Path, on_error, max_attempts: int = 3,
                 history: DownloadHistory | None = None):
        self.client = client
        self.directory = directory
        self.on_error = on_error
        self.max_attempts = max_attempts
        self.history = history
        self.queue: asyncio.Queue[object | None] = asyncio.Queue()

    async def enqueue(self, message: object) -> None:
        await self.queue.put(message)

    async def run(self) -> None:
        while True:
            message = await self.queue.get()
            try:
                if message is None:
                    return
                await self._download_with_retries(message)
            finally:
                self.queue.task_done()

    async def stop(self) -> None:
        await self.queue.put(None)

    async def download(self, message: object) -> Path | None:
        return await self._download_with_retries(message)

    async def _download_with_retries(self, message: object) -> Path | None:
        original_name = message_filename(message)
        message_id = getattr(message, "id", 0)
        record = self.history.download(message_id) if self.history else None
        destination = Path(record["path"]) if record else collision_safe_path(self.directory, original_name)
        if record and record["ready"] and destination.is_file():
            LOGGER.info("Recovered completed download for message %s: %s", message_id, destination)
            return destination
        if destination.exists():
            destination = collision_safe_path(self.directory, original_name)
        if self.history:
            self.history.reserve(message_id, destination)
        partial = destination.with_name(f"{destination.name}.part")
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                LOGGER.info("Downloading message %s to %s", getattr(message, "id", "?"), destination)
                downloaded = await self.client.download_media(message, file=str(partial))
                if not downloaded:
                    raise RuntimeError("Telegram returned no downloaded file")

                actual_partial = Path(downloaded)
                if not actual_partial.exists():
                    raise RuntimeError(f"Downloaded file was not found at {actual_partial}")

                expected_size = getattr(getattr(message, "file", None), "size", None)
                if expected_size is not None and actual_partial.stat().st_size != expected_size:
                    raise RuntimeError("Downloaded file size does not match Telegram")
                # Make the file contents durable before committing completion intent.
                with actual_partial.open("r+b") as handle:
                    os.fsync(handle.fileno())

                while destination.exists():
                    destination = collision_safe_path(self.directory, original_name)
                    if self.history:
                        self.history.reserve(message_id, destination)
                if self.history:
                    self.history.ready(message_id)
                actual_partial.rename(destination)
                LOGGER.info("Downloaded %s", destination)
                return destination
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # an individual Telegram/file failure must not stop the queue
                last_error = exc
                LOGGER.exception("Download attempt %d/%d failed", attempt, self.max_attempts)
                if attempt < self.max_attempts:
                    await asyncio.sleep(2 ** (attempt - 1))

        message_id = getattr(message, "id", "unknown")
        error = f"Failed to download Telegram message {message_id}: {last_error}"
        self.on_error(error)
        return None
