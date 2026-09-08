from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from telethon import TelegramClient, events

from .config import AppConfig
from .downloader import DownloadQueue
from .links import LinkRecorder
from .processor import MessageProcessor
from .state import AppState, ConnectionStatus

LOGGER = logging.getLogger(__name__)


class TelegramWatcher:
    def __init__(self, config: AppConfig, state: AppState):
        self.config = config
        self.state = state
        self.client: TelegramClient | None = None
        self.shutdown = asyncio.Event()
        self.reconnect_requested = asyncio.Event()
        self.started_at = datetime.now(timezone.utc)

    async def run(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.download_dir.mkdir(parents=True, exist_ok=True)
        self.config.wanted_links_file.parent.mkdir(parents=True, exist_ok=True)

        self.client = TelegramClient(
            str(self.config.session_path),
            self.config.api_id,
            self.config.api_hash,
            auto_reconnect=True,
            catch_up=False,
            sequential_updates=True,
        )

        try:
            while not self.shutdown.is_set():
                self.reconnect_requested.clear()
                try:
                    await self._run_connected_session()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
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
        download_queue: DownloadQueue | None = None
        download_task: asyncio.Task | None = None
        handler = None
        self.state.set_status(ConnectionStatus.CONNECTING)
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                raise RuntimeError("Telegram login is required. Run the configure command from the project folder.")

            target = await self.client.get_entity(self.config.chat)
            recorder = LinkRecorder(self.config.wanted_links_file)
            download_queue = DownloadQueue(self.client, self.config.download_dir, self.state.set_error)
            processor = MessageProcessor(recorder, download_queue, self.started_at, self.config.allowed_extensions)
            download_task = asyncio.create_task(download_queue.run(), name="download-queue")

            async def handle_message(event) -> None:
                try:
                    await processor.process(event.message)
                except Exception as exc:
                    LOGGER.exception("Could not process Telegram message")
                    self.state.set_error(f"Could not process a Telegram message: {exc}")

            handler = handle_message
            self.client.add_event_handler(handler, events.NewMessage(chats=target))
            LOGGER.info("Watching Telegram chat %s", getattr(target, "title", self.config.chat))
            self.state.clear_error()
            self.state.set_status(ConnectionStatus.CONNECTED)

            while not self.shutdown.is_set() and not self.reconnect_requested.is_set():
                if self.client.is_connected():
                    self.state.set_status(ConnectionStatus.CONNECTED)
                else:
                    self.state.set_status(ConnectionStatus.DISCONNECTED)
                    await self.client.connect()
                try:
                    await asyncio.wait_for(self.shutdown.wait(), timeout=2)
                except TimeoutError:
                    pass
        finally:
            if handler:
                self.client.remove_event_handler(handler)
            if download_queue and download_task:
                await download_queue.stop()
                try:
                    await asyncio.wait_for(download_task, timeout=10)
                except TimeoutError:
                    download_task.cancel()
            if self.client.is_connected():
                await self.client.disconnect()

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
