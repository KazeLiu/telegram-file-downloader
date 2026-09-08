import asyncio
from pathlib import Path
from types import SimpleNamespace

from telegram_file_watcher.downloader import DownloadQueue


class FakeTelegramClient:
    async def download_media(self, _message, file: str) -> str:
        Path(file).write_bytes(b"complete audio")
        return file


def test_download_completes_via_partial_file(tmp_path: Path) -> None:
    message = SimpleNamespace(
        id=22,
        file=SimpleNamespace(name="track.flac", ext=".flac", mime_type="audio/flac"),
    )
    errors: list[str] = []
    queue = DownloadQueue(FakeTelegramClient(), tmp_path, errors.append)

    destination = asyncio.run(queue._download_with_retries(message))

    assert destination == tmp_path / "track.flac"
    assert destination.read_bytes() == b"complete audio"
    assert not (tmp_path / "track.flac.part").exists()
    assert errors == []


def test_download_never_overwrites_existing_file(tmp_path: Path) -> None:
    existing = tmp_path / "track.flac"
    existing.write_bytes(b"original")
    message = SimpleNamespace(
        id=23,
        file=SimpleNamespace(name="track.flac", ext=".flac", mime_type="audio/flac"),
    )
    queue = DownloadQueue(FakeTelegramClient(), tmp_path, lambda _message: None)

    destination = asyncio.run(queue._download_with_retries(message))

    assert existing.read_bytes() == b"original"
    assert destination == tmp_path / "track (2).flac"
    assert destination.read_bytes() == b"complete audio"
