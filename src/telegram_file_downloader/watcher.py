from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, errors, utils

from .config import AppConfig
from .downloader import DownloadQueue
from .history import DownloadHistory
from .links import LinkRecorder
from .processor import MessageProcessor
from .state import AppState, ConnectionStatus

LOGGER = logging.getLogger(__name__)


class TelegramWatcher:
    def __init__(self, config: AppConfig, state: AppState, processor_factory=None, on_login_required=None):
        self.config = config
        self.state = state
        self.client: TelegramClient | None = None
        self.shutdown = asyncio.Event()
        self.reconnect_requested = asyncio.Event()
        self.started_at = datetime.now(timezone.utc)
        self.processor_factory = processor_factory
        self.on_login_required = on_login_required

    async def run(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.download_dir.mkdir(parents=True, exist_ok=True)
        self.config.wanted_links_file.parent.mkdir(parents=True, exist_ok=True)

        self.client = TelegramClient(
            str(self.config.session_path),
            self.config.api_id,
            self.config.api_hash,
            proxy=self.config.proxy,
            auto_reconnect=True,
            catch_up=False,
            sequential_updates=True,
            flood_sleep_threshold=0 if self.processor_factory else 60,
        )

        try:
            while not self.shutdown.is_set():
                self.reconnect_requested.clear()
                try:
                    await self._run_connected_session()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self.on_login_required and isinstance(exc, (errors.UnauthorizedError, errors.AuthKeyError)):
                        self.on_login_required()
                        self.request_shutdown()
                    else:
                        LOGGER.exception("Telegram connection failed")
                        self.state.set_error(str(exc))
                        self.state.set_status(ConnectionStatus.DISCONNECTED)

                if not self.shutdown.is_set():
                    try:
                        await asyncio.wait_for(self.reconnect_requested.wait(), timeout=10)
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            raise
        finally:
            if self.client and self.client.is_connected():
                await self.client.disconnect()
            self.state.set_status(ConnectionStatus.DISCONNECTED)

    async def _run_connected_session(self) -> None:
        assert self.client is not None
        history = None
        processor = None
        scan_task = None
        stop_tasks = []
        self.state.set_status(ConnectionStatus.CONNECTING)
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                if self.on_login_required:
                    self.on_login_required()
                    self.request_shutdown()
                    return
                raise RuntimeError("Telegram login is required. Run the configure command from the project folder.")

            target = await self.client.get_entity(self.config.chat)
            account = await self.client.get_me()
            history = DownloadHistory(
                self.config.data_dir / "download_history.sqlite3",
                f"{account.id}:{utils.get_peer_id(target)}",
                self.config.history_start_date or self.started_at,
            )
            recorder = LinkRecorder(self.config.wanted_links_file)
            download_queue = DownloadQueue(self.client, self.config.download_dir, self.state.set_error, history=history)
            processor = MessageProcessor(recorder, download_queue, self.config.allowed_extensions)
            if self.processor_factory:
                processor = self.processor_factory(self.client, history, recorder)
                await processor.start()
            LOGGER.info(
                "Watching Telegram chat %s; tracking since %s; resume after message %s (%s); last complete scan %s",
                getattr(target, "title", self.config.chat), history.since.isoformat(), history.message_id,
                history.progress["message_date"], history.progress["checked_at"],
            )
            self.state.clear_error()
            self.state.set_status(ConnectionStatus.CONNECTED)

            async def scan_loop():
                while not self.shutdown.is_set() and not self.reconnect_requested.is_set():
                    if not self.client.is_connected():
                        self.state.set_status(ConnectionStatus.DISCONNECTED)
                        await self.client.connect()
                    complete = await self._scan_history(target, processor, history)
                    self.state.set_status(ConnectionStatus.CONNECTED)
                    if complete:
                        self.state.clear_error()
                    # History is authoritative, including gaps during automatic reconnects.
                    await asyncio.sleep(5 if complete else 30)

            scan_task = asyncio.create_task(scan_loop(), name="history-scan")
            stop_tasks = [asyncio.create_task(self.shutdown.wait()), asyncio.create_task(self.reconnect_requested.wait())]
            done, _ = await asyncio.wait([scan_task, *stop_tasks], return_when=asyncio.FIRST_COMPLETED)
            if scan_task in done:
                await scan_task
        finally:
            for task in [scan_task, *stop_tasks]:
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
            if self.processor_factory and processor:
                await processor.close()
            if history:
                history.close()
            if self.client.is_connected():
                await self.client.disconnect()

    async def _scan_history(self, target, processor: MessageProcessor, history: DownloadHistory) -> bool:
        assert self.client is not None
        started = datetime.now(timezone.utc)
        before = history.message_id
        options = {"min_id": before, "reverse": True}
        if not before:
            # Telegram's offset is exclusive; include the boundary second then filter locally.
            options["offset_date"] = history.since - timedelta(seconds=1)
        iterator = self.client.iter_messages(target, **options).__aiter__()
        if self.processor_factory:
            processor.begin_scan()
        while True:
            try:
                message = await asyncio.wait_for(iterator.__anext__(), 45) if self.processor_factory else await iterator.__anext__()
            except StopAsyncIteration:
                break
            if self.shutdown.is_set() or self.reconnect_requested.is_set():
                return False
            if message.id <= history.message_id:
                continue
            if message.date >= history.since and not await processor.process(message):
                LOGGER.warning("Catch-up paused at message %s; checkpoint retained for retry", message.id)
                return False
            history.advance(message.id, message.date)
            LOGGER.info("Progress saved through Telegram message %s dated %s", message.id, message.date.isoformat())
        history.checked(started)
        if self.processor_factory:
            processor.scan_complete()
        if history.message_id != before:
            LOGGER.info("Catch-up complete; checked through %s", started.isoformat())
        return True

    def request_reconnect(self) -> None:
        self.reconnect_requested.set()

    def request_shutdown(self) -> None:
        self.shutdown.set()


class WatcherController:
    def __init__(self, config: AppConfig, state: AppState):
        self.config = config
        self.state = state
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.watcher: TelegramWatcher | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        self.thread = threading.Thread(target=self._thread_main, name="telegram-watcher", daemon=True)
        self.thread.start()
        self._ready.wait(timeout=5)

    def _thread_main(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.watcher = TelegramWatcher(self.config, self.state)
        self._ready.set()
        try:
            self.loop.run_until_complete(self.watcher.run())
        finally:
            self.loop.close()

    def reconnect(self) -> None:
        if self.loop and self.watcher and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.watcher.request_reconnect)

    def stop(self) -> None:
        if self.loop and self.watcher and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.watcher.request_shutdown)
        if self.thread:
            self.thread.join(timeout=12)
