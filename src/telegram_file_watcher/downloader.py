from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .files import collision_safe_path, message_filename

LOGGER = logging.getLogger(__name__)


class DownloadQueue:
    def __init__(self, client: object, directory: Path, on_error, max_attempts: int = 3):
        self.client = client
        self.directory = directory
        self.on_error = on_error
        self.max_attempts = max_attempts
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

    async def _download_with_retries(self, message: object) -> Path | None:
        original_name = message_filename(message)
        destination = collision_safe_path(self.directory, original_name)
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

                while destination.exists():
                    destination = collision_safe_path(self.directory, original_name)
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
