import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from telegram_file_watcher.links import LinkRecorder
from telegram_file_watcher.processor import MessageProcessor


class FakeDownloadQueue:
    def __init__(self) -> None:
        self.messages = []

    async def enqueue(self, message) -> None:
        self.messages.append(message)


def test_message_with_link_and_file_performs_both_actions(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    queue = FakeDownloadQueue()
    links_file = tmp_path / "wanted.txt"
    processor = MessageProcessor(LinkRecorder(links_file), queue, started, frozenset({".flac"}))
    message = SimpleNamespace(
        id=10,
        date=started + timedelta(seconds=1),
        message="Find https://www.discogs.com/release/123",
        file=SimpleNamespace(name="track.flac"),
    )

    asyncio.run(processor.process(message))

    assert queue.messages == [message]
    assert links_file.read_text(encoding="utf-8").splitlines() == [
        "https://www.discogs.com/release/123"
    ]


def test_message_from_before_start_is_ignored(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    queue = FakeDownloadQueue()
    links_file = tmp_path / "wanted.txt"
    processor = MessageProcessor(LinkRecorder(links_file), queue, started, frozenset({".flac"}))
    message = SimpleNamespace(
        id=9,
        date=started - timedelta(seconds=1),
        message="https://youtu.be/old",
        file=SimpleNamespace(name="old.flac"),
    )

    asyncio.run(processor.process(message))

    assert queue.messages == []
    assert not links_file.exists()


def test_disallowed_file_is_not_queued(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    queue = FakeDownloadQueue()
    processor = MessageProcessor(LinkRecorder(tmp_path / "wanted.txt"), queue, started, frozenset({".flac"}))
    message = SimpleNamespace(
        id=11,
        date=started + timedelta(seconds=1),
        message=None,
        file=SimpleNamespace(name="cover.jpg"),
    )

    asyncio.run(processor.process(message))

    assert queue.messages == []
