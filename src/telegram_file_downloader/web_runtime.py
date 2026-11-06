from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from telethon import TelegramClient, errors, utils

from .archives import ARCHIVE_EXTENSIONS, seven_zip
from .config import AppConfig, proxy_from_mapping
from .console_store import ConsoleStore, now
from .media_pipeline import ConsoleProcessor
from .state import AppState
from .watcher import TelegramWatcher
from .organizer import inside, make_plan, execute_plan

LOGGER = logging.getLogger(__name__)

def telegram_proxy(settings):
    if settings["proxy_type"] == "direct":
        return None
    return proxy_from_mapping({
        "TELEGRAM_PROXY_TYPE": settings["proxy_type"], "TELEGRAM_PROXY_HOST": settings["proxy_host"],
        "TELEGRAM_PROXY_PORT": str(settings["proxy_port"]),
        "TELEGRAM_PROXY_USERNAME": settings["proxy_username"], "TELEGRAM_PROXY_PASSWORD": settings["proxy_password"],
    })


def connection_error_message(error, settings):
    if isinstance(error, EOFError):
        if settings["proxy_type"] == "direct":
            return "Telegram 握手连接被关闭。当前为直连，请设置可用代理后重新连接"
        return "Telegram 握手连接被关闭，请核对代理类型、端口及其 Telegram 访问能力，再重新连接"
    if isinstance(error, TimeoutError):
        return "Telegram 连接或登录请求超时，请检查代理和网络后重新连接；请勿连续发送验证码"
    if isinstance(error, OSError):
        if settings["proxy_type"] == "direct":
            return "无法直连 Telegram，请设置可用代理后重新连接"
        return "无法通过代理连接 Telegram，请检查容器能否访问代理，以及代理类型和端口是否正确"
    return "Telegram 连接失败，请检查 API 信息、代理和账号状态后重新连接"


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
        self.processor = None
        self.local_jobs = set()
        self.manual_task = None

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
                async with self.control_lock:
                    async with asyncio.timeout(60):
                        await self._apply()
            except (ValueError, OSError, EOFError, errors.RPCError) as exc:
                self.phase = "connection_error"
                self.error = str(exc) if isinstance(exc, ValueError) else connection_error_message(exc, self.store.settings())
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
            self.watcher_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.watcher_task
            self.watcher_task = None
            self.watcher = None
            self.processor = None

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
                ARCHIVE_EXTENSIONS, proxy=telegram_proxy(settings))

            def processor_factory(client, history, recorder):
                self.processor = ConsoleProcessor(client, self.download_dir, history, recorder,
                                                 self.store, settings, self.operation_lock)
                return self.processor

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

    @asynccontextmanager
    async def _login_connection(self):
        try:
            async with asyncio.timeout(60):
                yield await self._connect()
        except (OSError, EOFError) as exc:
            self.phase = "connection_error"
            self.error = connection_error_message(exc, self.store.settings())
            self.phone = self.phone_code_hash = None
            await self._disconnect_auth()
            raise ValueError(self.error) from exc

    async def send_code(self, phone):
        async with self.control_lock:
            if self.pending:
                raise ValueError("连接配置正在应用，请稍后再试")
            if self.account:
                raise ValueError("当前账号已登录；更换账号请先退出 Telegram")
            await self._stop_watcher()
            async with self._login_connection() as client:
                sent = await client.send_code_request(phone)
                self.phone, self.phone_code_hash = phone, sent.phone_code_hash
                self.phase, self.error = "code", ""

    async def sign_in(self, code="", password=""):
        async with self.control_lock:
            if self.pending:
                raise ValueError("连接配置正在应用，请稍后再试")
            async with self._login_connection() as client:
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
        async with self.control_lock:
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
        async with self.control_lock:
            task = self.store.task(task_id)
            if not task or task["kind"] != "archive" or task["status"] not in {"extraction_failed", "processing_failed", "waiting_volumes", "completed", "interrupted"}:
                raise ValueError("这个任务不需要重新解压")
            group = task.get("group_id") or str(task_id)
            if not task["path"] or (not Path(task["path"]).is_file() and not self.store.get(f"organize:{group}")):
                raise ValueError("原压缩包不在原下载目录，无法重试")
            if self.processor and (task_id in self.processor.running or group in self.processor.post_tasks):
                raise ValueError("这一组资源正在处理")
            if any(job.get_name() == f"local-workflow-{group}" for job in self.local_jobs):
                raise ValueError("这一组资源正在处理")
            if not task.get("group_id"):
                self.store.update_task(task_id, group_id=group)
            members = self.store.group(group)
            for member in members:
                if member["status"] not in {"failed", "paused", "queued"}:
                    self.store.update_task(member["id"], status="downloaded")
            self.store.put(f"volume_attempt:{group}", None)
            if self.processor:
                await self.processor.unpack(task_id)
                return
            processor = ConsoleProcessor(None, self.download_dir, None, None, self.store, self.store.settings(), self.operation_lock)
            job = asyncio.create_task(processor._postprocess(group), name=f"local-workflow-{group}")
            self.local_jobs.add(job)
            job.add_done_callback(self.local_jobs.discard)

    async def task_action(self, task_id, action):
        task = self.store.task(task_id)
        if not task:
            raise ValueError("任务不存在")
        if action == "retry" and task["kind"] == "archive" and (task.get("stage", "download") != "download" or task["status"] in {"extraction_failed", "processing_failed", "waiting_volumes"}):
            return await self.retry_extraction(task_id)
        if not self.processor:
            if action == "pause" and task["status"] in {"queued", "interrupted", "failed"}:
                self.store.update_task(task_id, status="paused", speed=0)
                return
            raise ValueError("请先连接当前账号与收集群，并开启收集，再继续下载")
        await self.processor.control(task_id, action)

    async def queue_action(self, paused):
        if not paused and self.manual_task and not self.manual_task.done():
            raise ValueError("手动整理正在进行，请完成后再继续下载")
        if self.processor:
            await self.processor.pause_queue(paused)
        else:
            self.store.put("queue_paused", paused)

    def selected_folder(self, value):
        if Path(value).parts and Path(value).parts[0] == ".tg-work":
            raise ValueError("工作流内部目录不能手动整理")
        folder = inside(self.download_dir, value)
        if not folder.is_dir():
            raise ValueError("文件夹不存在")
        return folder

    def ensure_idle_folder(self, folder):
        if self.processor and not self.store.get("queue_paused", False):
            raise ValueError("请先暂停下载队列，再手动整理")
        if self.store.tasks(statuses={"downloading", "retrying", "waiting", "extracting", "organizing"}):
            raise ValueError("请先暂停下载队列，并等待解压和整理完成，再手动整理")

    async def preview_folder(self, value):
        folder = self.selected_folder(value)
        self.ensure_idle_folder(folder)
        if self.manual_task and not self.manual_task.done():
            raise ValueError("已有文件整理正在执行")
        old = self.store.get("manual_job", {})
        if old.get("status") in {"running", "interrupted", "failed"}:
            raise ValueError("上次整理尚未完成，请先继续原任务")
        prefix = "-".join(folder.relative_to(self.download_dir).parts)
        plan = await asyncio.to_thread(make_plan, self.download_dir, folder, prefix, False)
        token = uuid.uuid4().hex
        self.store.put(f"manual_preview:{token}", plan)
        return dict(token=token, total=len(plan["moves"]), items=[
            dict(source=str(Path(move["source"]).relative_to(self.download_dir)), target=Path(move["target"]).name)
            for move in plan["moves"][:200]])

    async def organize_folder(self, token):
        if self.manual_task and not self.manual_task.done():
            raise ValueError("已有文件整理正在执行")
        self.ensure_idle_folder(self.download_dir)
        job = self.store.get("manual_job", {})
        if token:
            if job.get("status") in {"running", "interrupted", "failed"}:
                raise ValueError("请先继续上次整理")
            plan = self.store.get(f"manual_preview:{token}")
            if not plan or plan["complete"]:
                raise ValueError("预览已失效，请重新预览")
            job = dict(status="running", token=token, plan=plan, error="", created_at=now())
        elif job.get("status") not in {"failed", "interrupted", "running"}:
            raise ValueError("没有需要继续的整理任务")
        job["status"], job["error"] = "running", ""
        self.store.put("queue_paused", True)
        self.store.put("manual_job", job)
        async def run():
            try:
                async with self.operation_lock:
                    def save(plan):
                        job["plan"] = plan
                        self.store.put("manual_job", job)
                    job["result"] = await execute_plan(self.download_dir, job["plan"], save)
                    job["status"] = "completed"
            except asyncio.CancelledError:
                job["status"] = "interrupted"
                raise
            except (OSError, ValueError) as exc:
                LOGGER.exception("manual organize failed")
                job.update(status="failed", error=str(exc))
            finally:
                self.store.put("manual_job", job)
        self.manual_task = asyncio.create_task(run(), name="manual-organize")

    async def close(self):
        self.stopping = True
        for job in [self.manual_task, *self.local_jobs]:
            if job:
                job.cancel()
        await asyncio.gather(*(job for job in [self.manual_task, *self.local_jobs] if job), return_exceptions=True)
        if self.supervisor:
            self.supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await self.supervisor
        if self.watcher_task:
            await self._stop_watcher()
        await self._disconnect_auth()
