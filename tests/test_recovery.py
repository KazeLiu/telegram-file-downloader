import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from telethon.tl.types import PeerChannel

from telegram_file_downloader.config import AppConfig, ConfigError, config_from_mapping
from telegram_file_downloader.downloader import DownloadQueue
from telegram_file_downloader.history import DownloadHistory
from telegram_file_downloader.links import LinkRecorder
from telegram_file_downloader.processor import MessageProcessor
from telegram_file_downloader.state import AppState
from telegram_file_downloader.watcher import TelegramWatcher

SINCE = datetime(2026, 9, 24, 13, 15, 16, tzinfo=timezone.utc)


def message(number, name="song.mp3", date=SINCE):
    return SimpleNamespace(id=number, date=date, message="", file=SimpleNamespace(name=name, size=3))


class Client:
    def __init__(self, messages):
        self.messages = messages
        self.downloaded = []
        self.fail = set()
        self.cancel = False
        self.options = []

    async def iter_messages(self, target, **options):
        self.options.append(options)
        for msg in list(self.messages):
            if msg.id > options["min_id"] and msg.date > options.get("offset_date", datetime.min.replace(tzinfo=timezone.utc)):
                yield msg

    async def download_media(self, msg, file):
        self.downloaded.append(msg.id)
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        Path(file).write_bytes(b"par" if self.cancel else b"mp3")
        if self.cancel:
            raise asyncio.CancelledError()
        if msg.id in self.fail:
            raise OSError("offline")
        return file


def setup(tmp_path, client, scope="account:chat", since=SINCE):
    config = AppConfig(1, "hash", 123, tmp_path / "files", tmp_path / "links.txt", tmp_path,
                       frozenset({".mp3"}), since)
    watcher = TelegramWatcher(config, AppState())
    watcher.client = client
    history = DownloadHistory(tmp_path / "history.sqlite3", scope, since)
    queue = DownloadQueue(client, config.download_dir, watcher.state.set_error, max_attempts=1, history=history)
    processor = MessageProcessor(LinkRecorder(config.wanted_links_file), queue, config.allowed_extensions)
    return watcher, history, queue, processor


def scan(watcher, history, processor):
    return asyncio.run(watcher._scan_history("chat", processor, history))


def test_restart_downloads_offline_arrivals_without_duplicates(tmp_path):
    client = Client([message(10)])
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    history.close()
    client.messages.extend([message(11), message(12)])  # Same timestamp; IDs distinguish them.
    watcher, history, _, processor = setup(tmp_path, client, since=SINCE + timedelta(days=7))
    assert history.since == SINCE
    assert scan(watcher, history, processor)
    assert client.downloaded == [10, 11, 12]
    assert client.options[-1]["min_id"] == 10
    assert history.message_id == 12
    assert history.progress["checked_at"] is not None
    assert len(list((tmp_path / "files").glob("*.mp3"))) == 3
    history.close()


def test_failure_does_not_advance_past_missing_download(tmp_path):
    client = Client([message(1), message(2), message(3)])
    client.fail.add(2)
    watcher, history, _, processor = setup(tmp_path, client)
    assert not scan(watcher, history, processor)
    assert history.message_id == 1
    assert history.progress["checked_at"] is None
    assert client.downloaded == [1, 2]
    history.close()
    client.fail.clear()
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    assert client.downloaded == [1, 2, 2, 3]
    assert history.message_id == 3
    assert not list((tmp_path / "files").glob("*.part"))
    history.close()


def test_cancelled_download_reuses_partial_destination(tmp_path):
    client = Client([message(1)])
    client.cancel = True
    watcher, history, _, processor = setup(tmp_path, client)
    with pytest.raises(asyncio.CancelledError):
        scan(watcher, history, processor)
    assert history.message_id == 0
    reserved = history.download(1)["path"]
    history.close()
    client.cancel = False
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    assert history.download(1)["path"] == reserved
    assert Path(reserved).read_bytes() == b"mp3"
    assert len(list((tmp_path / "files").iterdir())) == 1
    history.close()


def test_rename_before_checkpoint_crash_does_not_download_twice(tmp_path):
    client = Client([message(1)])
    watcher, history, queue, processor = setup(tmp_path, client)
    asyncio.run(queue.download(client.messages[0]))
    assert history.message_id == 0  # Process dies between rename and checkpoint update.
    history.close()
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    assert client.downloaded == [1]
    assert history.message_id == 1
    history.close()


def test_ready_before_rename_crash_retries_safely(tmp_path):
    client = Client([message(1)])
    watcher, history, _, processor = setup(tmp_path, client)
    destination = tmp_path / "files" / "song.mp3"
    destination.parent.mkdir()
    destination.with_suffix(".mp3.part").write_bytes(b"mp3")
    history.reserve(1, destination)
    history.ready(1)
    history.close()
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    assert destination.read_bytes() == b"mp3"
    assert len(list(destination.parent.iterdir())) == 1
    history.close()


def test_old_messages_and_disallowed_files_are_skipped(tmp_path):
    client = Client([message(1, date=SINCE - timedelta(hours=1)), message(2, "photo.jpg"), message(3)])
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    assert client.downloaded == [3]
    assert history.message_id == 3
    history.close()


def test_chat_and_account_have_independent_checkpoints(tmp_path):
    for scope, expected in [("a:chat1", 0), ("a:chat2", 0), ("b:chat1", 0), ("a:chat1", 99)]:
        history = DownloadHistory(tmp_path / "history.sqlite3", scope, SINCE)
        assert history.message_id == expected
        history.advance(99, SINCE)
        history.advance(3, SINCE)
        assert history.message_id == 99
        history.close()


def test_existing_file_is_not_overwritten(tmp_path):
    client = Client([message(1)])
    watcher, history, _, processor = setup(tmp_path, client)
    files = tmp_path / "files"
    files.mkdir()
    (files / "song.mp3").write_bytes(b"original")
    assert scan(watcher, history, processor)
    assert (files / "song.mp3").read_bytes() == b"original"
    assert (files / "song (2).mp3").read_bytes() == b"mp3"
    history.close()


def test_shutdown_leaves_unprocessed_messages_for_restart(tmp_path):
    watcher, history, _, processor = setup(tmp_path, Client([message(1)]))
    watcher.request_shutdown()
    assert not scan(watcher, history, processor)
    assert history.message_id == 0
    history.close()


def test_empty_scan_keeps_start_date_for_next_connection(tmp_path):
    client = Client([])
    watcher, history, _, processor = setup(tmp_path, client)
    assert scan(watcher, history, processor)
    history.close()
    client.messages.append(message(1, date=SINCE + timedelta(minutes=1)))
    watcher, history, _, processor = setup(tmp_path, client, since=SINCE + timedelta(days=1))
    assert scan(watcher, history, processor)
    assert client.downloaded == [1]
    history.close()


@pytest.mark.parametrize("value, expected", [("2026-09-24", "2026-09-24T00:00:00+00:00"),
    ("2026-09-24T15:15:16+02:00", SINCE.isoformat()), ("2026-09-24T13:15:16Z", SINCE.isoformat())])
def test_start_date_parsing(tmp_path, value, expected):
    values = dict(TELEGRAM_API_ID="1", TELEGRAM_API_HASH="hash", TELEGRAM_CHAT="123",
                  DOWNLOAD_DIR=str(tmp_path), ALLOWED_EXTENSIONS="mp3", HISTORY_START_DATE=value)
    assert config_from_mapping(values, tmp_path).history_start_date.isoformat() == expected


@pytest.mark.parametrize("value", ["yesterday", "2099-01-01"])
def test_bad_start_date(tmp_path, value):
    values = dict(TELEGRAM_API_ID="1", TELEGRAM_API_HASH="hash", TELEGRAM_CHAT="123",
                  DOWNLOAD_DIR=str(tmp_path), ALLOWED_EXTENSIONS="mp3", HISTORY_START_DATE=value)
    with pytest.raises(ConfigError, match="HISTORY_START_DATE"):
        config_from_mapping(values, tmp_path)


def test_short_download_is_not_marked_complete(tmp_path):
    msg = message(1)
    msg.file.size = 100
    watcher, history, _, processor = setup(tmp_path, Client([msg]))
    assert not scan(watcher, history, processor)
    assert history.message_id == 0
    assert not history.download(1)["ready"]
    history.close()


class SessionClient(Client):
    connected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    async def is_user_authorized(self):
        return True

    async def get_entity(self, chat):
        return PeerChannel(123)

    async def get_me(self):
        return SimpleNamespace(id=1)


def test_session_polls_and_recovers_without_new_message_events(tmp_path, monkeypatch):
    real_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    class PollClient(SessionClient):
        scans = 0

        async def iter_messages(self, target, **options):
            self.scans += 1
            async for msg in super().iter_messages(target, **options):
                yield msg
            if self.scans == 1:
                self.messages.append(message(2))
                self.connected = False  # A connection gap between scans.
            elif self.scans == 2:
                watcher.request_shutdown()

    client = PollClient([message(1)])
    watcher, history, _, _ = setup(tmp_path, client)
    history.close()
    asyncio.run(asyncio.wait_for(watcher._run_connected_session(), timeout=2))
    assert client.downloaded == [1, 2]
    assert not client.connected
    saved = DownloadHistory(tmp_path / "download_history.sqlite3", "1:-1000000000123", SINCE)
    assert saved.message_id == 2
    saved.close()


def test_session_shutdown_cancels_transfer_and_preserves_retry(tmp_path):
    async def scenario():
        started = asyncio.Event()

        class BlockingClient(SessionClient):
            async def download_media(self, msg, file):
                Path(file).parent.mkdir(parents=True, exist_ok=True)
                Path(file).write_bytes(b"partial")
                started.set()
                await asyncio.Event().wait()

        client = BlockingClient([message(1)])
        watcher, history, _, _ = setup(tmp_path, client)
        history.close()
        task = asyncio.create_task(watcher._run_connected_session())
        await asyncio.wait_for(started.wait(), timeout=2)
        watcher.request_shutdown()
        await asyncio.wait_for(task, timeout=2)
        saved = DownloadHistory(tmp_path / "download_history.sqlite3", "1:-1000000000123", SINCE)
        assert saved.message_id == 0
        assert not saved.download(1)["ready"]
        saved.close()
        assert not client.connected

    asyncio.run(scenario())


def test_failed_link_write_remains_retryable(tmp_path, monkeypatch):
    recorder = LinkRecorder(tmp_path / "links.txt")
    def fail_open(self, *args, **kwargs):
        raise OSError("disk temporarily unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_open)
        with pytest.raises(OSError):
            recorder.append_from_text("https://youtu.be/example")
    assert recorder.append_from_text("https://youtu.be/example") == ["https://youtu.be/example"]
    assert recorder.append_from_text("https://youtu.be/example") == []
