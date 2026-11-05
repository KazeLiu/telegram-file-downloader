from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

from telethon import TelegramClient, errors, utils

from .archives import seven_zip
from .config import AppConfig, proxy_from_mapping
from .console_store import ConsoleStore
from .media_pipeline import ConsoleProcessor
from .state import AppState
from .watcher import TelegramWatcher

def telegram_proxy(settings):
    if settings["proxy_type"] == "direct":
        return None
    return proxy_from_mapping({
        "TELEGRAM_PROXY_TYPE": settings["proxy_type"], "TELEGRAM_PROXY_HOST": settings["proxy_host"],
        "TELEGRAM_PROXY_PORT": str(settings["proxy_port"]),
        "TELEGRAM_PROXY_USERNAME": settings["proxy_username"], "TELEGRAM_PROXY_PASSWORD": settings["proxy_password"],
    })


class WebRuntime:
    def __init__(self, store: ConsoleStore, data_dir: Path, download_dir: Path):
        self.store, self.data_dir, self.download_dir = store, data_dir, download_dir
        self.state = AppState()
        self.account = None
        self.phase = "unconfigured"
        self.error = ""
        self.phone = None
        self.phone_code_hash = None
        self.auth_client = None
        self.watcher = None
        self.watcher_task = None
        self.supervisor = None
        self.changed = asyncio.Event()
        self.control_lock = asyncio.Lock()
        self.operation_lock = asyncio.Lock()
        self.pending = False
        self.stopping = False

    def status(self):
        return dict(phase=self.phase, account=self.account, error=self.error or self.state.latest_error,
                    connection=self.state.status.value, pending=self.pending,
                    download_dir=str(self.download_dir), data_dir=str(self.data_dir),
                    extractor_available=bool(seven_zip()), **self.store.summary())

    async def start(self):
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.supervisor = asyncio.create_task(self._supervise(), name="console-supervisor")
        self.schedule_apply()

    def schedule_apply(self):
        self.pending = True
        self.changed.set()

    async def _supervise(self):
        while not self.stopping:
            await self.changed.wait()
            self.changed.clear()
            try:
                async with self.control_lock, self.operation_lock:
                    await self._apply()
            except (ValueError, OSError, ConnectionError, errors.RPCError, TimeoutError):
                self.phase = "connection_error"
                self.error = "连接失败，请检查 API、代理和网络后点击重新连接"
                await self._disconnect_auth()
            finally:
                self.pending = self.changed.is_set()

    async def _disconnect_auth(self):
        if self.auth_client:
            await self.auth_client.disconnect()
            self.auth_client = None

    async def _stop_watcher(self):
        if self.watcher_task:
            self.watcher.request_shutdown()
            await self.watcher_task
            self.watcher_task = None
            self.watcher = None

    async def _apply(self):
        await self._stop_watcher()
        await self._disconnect_auth()
        self.phone = self.phone_code_hash = None
        self.error = ""
        self.state.clear_error()
        settings = self.store.settings()
        if not settings["api_id"] or not settings["api_hash"]:
            self.phase = "unconfigured"
            return
        telegram_proxy(settings)  # Require a complete proxy before attempting a connection.
        self.phase = "connecting"
        client = await self._connect(settings)
        if not await client.is_user_authorized():
            self.account = None
            self.phase = "phone"
            return
        await self._identify(client)
        if settings["chat"] and settings["enabled"]:
            await self._disconnect_auth()
            config = AppConfig(int(settings["api_id"]), settings["api_hash"], int(settings["chat"]),
                self.download_dir, self.download_dir / "wanted_tracks.txt", self.data_dir,
                frozenset({".zip", ".rar"}), proxy=telegram_proxy(settings))

            def processor_factory(client, history, recorder):
                return ConsoleProcessor(client, self.download_dir, history, recorder,
                                        self.store, settings, self.operation_lock)

            self.watcher = TelegramWatcher(config, self.state, processor_factory, self.login_required)
            self.watcher_task = asyncio.create_task(self._watch(), name="console-watcher")
            self.phase = "watching"
        else:
            self.phase = "ready" if settings["chat"] else "choose_chat"

    async def _watch(self):
        try:
            await self.watcher.run()
        except (errors.UnauthorizedError, errors.AuthKeyError):
            self.login_required()

    def login_required(self):
        self.account = None
        self.phase = "phone"
        self.error = "Telegram 登录已失效，请重新登录；下载文件和历史记录会保留"

    async def _connect(self, settings=None):
        if self.auth_client:
            if not self.auth_client.is_connected():
                await asyncio.wait_for(self.auth_client.connect(), 45)
            return self.auth_client
        settings = settings or self.store.settings()
        if not settings["api_id"] or not settings["api_hash"]:
            raise ValueError("请先保存 Telegram API 信息和代理")
        self.auth_client = TelegramClient(str(self.data_dir / "telegram"), int(settings["api_id"]),
            settings["api_hash"], proxy=telegram_proxy(settings), connection_retries=2, request_retries=1,
            timeout=15, flood_sleep_threshold=0)
        await asyncio.wait_for(self.auth_client.connect(), 45)
        return self.auth_client

    async def _identify(self, client):
        user = await client.get_me()
        self.account = {"name": " ".join(filter(None, [user.first_name, user.last_name])),
                        "username": user.username or "", "id": user.id}

    async def send_code(self, phone):
        async with self.control_lock, self.operation_lock:
            if self.pending:
                raise ValueError("连接配置正在应用，请稍后再试")
            if self.account:
                raise ValueError("当前账号已登录；更换账号请先退出 Telegram")
            await self._stop_watcher()
            client = await self._connect()
            sent = await client.send_code_request(phone)
            self.phone, self.phone_code_hash = phone, sent.phone_code_hash
            self.phase, self.error = "code", ""

    async def sign_in(self, code="", password=""):
        async with self.control_lock:
            client = await self._connect()
            try:
                if password:
                    if self.phase != "password":
                        raise ValueError("请先完成验证码步骤")
                    await client.sign_in(password=password)
                else:
                    if not self.phone or not self.phone_code_hash:
                        raise ValueError("请先发送登录验证码")
                    code = code.strip().replace(" ", "")
                    if self.phase != "code" or not code.isdigit():
                        raise ValueError("请输入收到的数字验证码")
                    await client.sign_in(phone=self.phone, code=code, phone_code_hash=self.phone_code_hash)
            except errors.SessionPasswordNeededError:
                self.phase = "password"
                return
            await self._identify(client)
            self.phone = self.phone_code_hash = None
            self.schedule_apply()

    async def dialogs(self):
        async with self.control_lock:
            if not self.account or self.pending:
                raise ValueError("请先登录，并等待连接配置应用完成")
            client = self.watcher.client if self.watcher and self.watcher.client else await self._connect()
            return [{"id": str(utils.get_peer_id(dialog.entity)), "title": dialog.title}
                    async for dialog in client.iter_dialogs() if dialog.is_group or dialog.is_channel]

    async def logout_telegram(self):
        async with self.control_lock, self.operation_lock:
            await self._stop_watcher()
            client = await self._connect()
            if not await client.log_out():
                self.schedule_apply()
                raise ValueError("Telegram 未确认退出，原会话已保留，请稍后再试")
            self.auth_client = None
            settings = self.store.settings()
            settings.update(enabled=False, chat="", chat_title="")
            self.store.put("settings", settings)
            self.account, self.phone, self.phone_code_hash = None, None, None
            self.phase, self.error = "phone", ""

    async def retry_extraction(self, task_id):
        async with self.control_lock, self.operation_lock:
            task = self.store.task(task_id)
            if not task or task["kind"] != "archive" or task["status"] not in {"extraction_failed", "completed", "interrupted"}:
                raise ValueError("这个任务不需要重新解压")
            if not Path(task["path"]).is_file():
                raise ValueError("原压缩包不在原下载目录，无法重试")
            settings = self.store.settings()
            client = self.watcher.client if self.watcher else self.auth_client
            processor = ConsoleProcessor(client, self.download_dir, None, None, self.store, settings, self.operation_lock)
            await processor.unpack(task_id)
            if client:
                await processor.receipt(self.store.task(task_id))

    async def close(self):
        self.stopping = True
        if self.supervisor:
            self.supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await self.supervisor
        if self.watcher_task:
            self.watcher.request_shutdown()
            with suppress(asyncio.CancelledError):
                await self.watcher_task
        await self._disconnect_auth()
