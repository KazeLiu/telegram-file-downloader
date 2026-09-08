from __future__ import annotations

import logging
from datetime import datetime

from .files import message_filename
from .links import LinkRecorder

LOGGER = logging.getLogger(__name__)


class MessageProcessor:
    def __init__(
        self,
        link_recorder: LinkRecorder,
        download_queue: object,
        started_at: datetime,
        allowed_extensions: frozenset[str],
    ):
        self.link_recorder = link_recorder
        self.download_queue = download_queue
        self.started_at = started_at
        self.allowed_extensions = allowed_extensions

    async def process(self, message: object) -> None:
        message_date = getattr(message, "date", None)
        if message_date is not None and message_date < self.started_at:
            LOGGER.debug("Ignoring pre-start message %s", getattr(message, "id", "?"))
            return

        text = getattr(message, "message", None) or getattr(message, "raw_text", None)
        added = self.link_recorder.append_from_text(text)
        for link in added:
            LOGGER.info("Recorded wanted link: %s", link)

        if getattr(message, "file", None) is not None:
            filename = message_filename(message)
            extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            normalized_extension = f".{extension}" if extension else ""
            if normalized_extension not in self.allowed_extensions:
                LOGGER.info("Skipping %s: extension %s is not allowed", filename, normalized_extension or "(none)")
                return
            await self.download_queue.enqueue(message)
