from __future__ import annotations

import os
import asyncio
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from telethon import errors

from .console_store import ConsoleStore
from .config import compact_connection_input
from .web_runtime import WebRuntime, telegram_proxy
from .diagnostics import configure_logs, read_log
from .organizer import browse


class Credentials(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(Credentials):
    current_password: str = Field(max_length=256)


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_id: str | None = Field(default=None, max_length=16)
    api_hash: str | None = Field(default=None, max_length=128)
    proxy_type: str | None = None
    proxy_host: str | None = Field(default=None, max_length=255)
    proxy_port: str | None = Field(default=None, max_length=5)
    proxy_username: str | None = Field(default=None, max_length=255)
    proxy_password: str | None = Field(default=None, max_length=512)
    clear_proxy_password: bool = False
    archive_passwords: list[str] | None = Field(default=None, max_length=30)
    videos: bool | None = None
    photos: bool | None = None
    archives: bool | None = None
    extract: bool | None = None
    delete_archive: bool | None = None
    receipts: bool | None = None
    mark_read: bool | None = None
    download_parallelism: Literal[1, 2, 4] | None = None
    parallel_files: int | None = Field(default=None, ge=1, le=5)
    flatten: bool | None = None
    delete_pdf: bool | None = None

    @field_validator("proxy_host", "proxy_port", mode="before")
    @classmethod
    def clean_endpoint(cls, value):
        return compact_connection_input(value) if isinstance(value, str) else value


class Phone(BaseModel):
    phone: str = Field(pattern=r"^\+?[0-9]{7,16}$")

    @field_validator("phone", mode="before")
    @classmethod
    def clean_phone(cls, value):
        return compact_connection_input(value) if isinstance(value, str) else value


class LoginCode(BaseModel):
    code: str = Field(default="", max_length=16)
    password: str = Field(default="", max_length=256)


class Chat(BaseModel):
    id: str = Field(pattern=r"^-?[0-9]{1,20}$")


class Enabled(BaseModel):
    enabled: bool


class TaskAction(BaseModel):
    action: Literal["pause", "resume", "retry"]


class QueuePause(BaseModel):
    paused: bool


class FolderSelection(BaseModel):
    path: str = Field(default="", max_length=4096)


class OrganizeSelection(BaseModel):
    token: str = Field(default="", max_length=32, pattern=r"^[a-f0-9]*$")


def create_app():
    data_dir = Path(os.environ.get("DATA_DIR", str(Path.cwd() / "data"))).resolve()
    download_dir = Path(os.environ.get("DOWNLOAD_DIR", str(Path.cwd() / "downloads"))).resolve()
    log_dir = configure_logs(data_dir)
    store = ConsoleStore(data_dir)
    runtime = WebRuntime(store, data_dir, download_dir)
    failures: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()
            store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in {"GET", "HEAD"}:
                origin = request.headers.get("origin")
                if origin != f"{request.url.scheme}://{request.headers.get('host')}":
                    return JSONResponse({"detail": "请从本页面操作"}, status_code=403)
                if request.headers.get("content-type", "").split(";")[0] != "application/json":
                    return JSONResponse({"detail": "请求需要 JSON 内容"}, status_code=415)
            public = {"/api/auth/status", "/api/auth/setup", "/api/auth/login"}
            if request.url.path not in public and not store.authorized(request.cookies.get("console_session", "")):
                return JSONResponse({"detail": "请先登录管理页面"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def malformed(request, exc):
        # Default validation errors include the submitted input, which can contain credentials.
        return JSONResponse({"detail": "填写格式不正确，请检查输入内容"}, status_code=422)

    @app.exception_handler(errors.RPCError)
    async def telegram_error(request, exc):
        if isinstance(exc, errors.FloodWaitError):
            detail = f"Telegram 要求等待 {exc.seconds} 秒，请勿反复发送验证码"
        elif isinstance(exc, errors.PhoneCodeInvalidError):
            detail = "验证码不正确，请重新输入"
        elif isinstance(exc, errors.PhoneCodeExpiredError):
            detail = "验证码已过期，请重新发送"
        elif isinstance(exc, errors.PasswordHashInvalidError):
            detail = "两步验证密码不正确"
        else:
            detail = f"Telegram 操作失败（{type(exc).__name__}），请检查配置和账号状态"
        return JSONResponse({"detail": detail}, status_code=400)

    @app.exception_handler(ConnectionError)
    @app.exception_handler(OSError)
    @app.exception_handler(TimeoutError)
    @app.exception_handler(EOFError)
    async def network_error(request, exc):
        return JSONResponse({"detail": "连接或文件操作失败，请检查代理、网络和目录权限"}, status_code=400)

    def cookie(request, response):
        response.set_cookie("console_session", store.session(), httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", max_age=7 * 86400)

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        return dict(initialized=bool(store.get("admin")),
                    authenticated=store.authorized(request.cookies.get("console_session", "")))

    @app.post("/api/auth/setup")
    async def setup(body: Credentials, request: Request, response: Response):
        if store.get("admin"):
            raise HTTPException(409, "管理密码已设置，请登录")
        store.set_password(body.password)
        cookie(request, response)
        return {"ok": True}

    @app.post("/api/auth/login")
    async def login(body: Credentials, request: Request, response: Response):
        address = request.client.host
        attempts = [stamp for stamp in failures.get(address, []) if stamp > time.monotonic() - 300]
        failures[address] = attempts
        if len(attempts) >= 10:
            raise HTTPException(429, "尝试过多，请在五分钟后重试")
        if not store.check_password(body.password):
            attempts.append(time.monotonic())
            raise HTTPException(401, "管理密码不正确")
        failures.pop(address, None)
        cookie(request, response)
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        store.revoke(request.cookies.get("console_session", ""))
        response.delete_cookie("console_session")
        return {"ok": True}

    @app.post("/api/auth/password")
    async def password(body: PasswordChange, request: Request, response: Response):
        if not store.check_password(body.current_password):
            raise HTTPException(400, "原管理密码不正确")
        store.set_password(body.password)
        cookie(request, response)
        return {"ok": True}

    @app.get("/api/status")
    async def status():
        return runtime.status()

    @app.get("/api/settings")
    async def settings():
        return store.public_settings()

    @app.put("/api/settings")
    async def save_settings(body: SettingsPatch):
        previous = store.settings()
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        clear_proxy_password = changes.pop("clear_proxy_password", False)
        for key in ("api_hash", "proxy_password"):
            if changes.get(key) == "":
                changes.pop(key)
        settings = {**previous, **changes}
        if clear_proxy_password:
            settings["proxy_password"] = ""
        if settings["api_id"] and (not str(settings["api_id"]).isdigit() or int(settings["api_id"]) <= 0):
            raise ValueError("API ID 需要填写正整数")
        if settings["api_hash"] and not re.fullmatch(r"[a-fA-F0-9]{32}", settings["api_hash"]):
            raise ValueError("API Hash 需要填写 32 位十六进制字符")
        if settings["proxy_type"] not in {"socks5", "http", "direct"}:
            raise ValueError("请选择 SOCKS5、HTTP 或直连")
        if settings["proxy_host"] or settings["proxy_port"] or settings["api_id"]:
            proxy = telegram_proxy(settings)
            if proxy:
                settings.update(proxy_type=proxy["proxy_type"], proxy_host=proxy["addr"],
                                proxy_port=str(proxy["port"]))
        if any(len(value) > 256 for value in settings["archive_passwords"]):
            raise ValueError("单个解压密码不能超过 256 个字符")
        if runtime.account and (settings["api_id"], settings["api_hash"]) != (previous["api_id"], previous["api_hash"]):
            raise ValueError("修改 API 身份前，请先退出 Telegram 账号")
        store.put("settings", settings)
        runtime.schedule_apply()
        return store.public_settings()

    @app.post("/api/telegram/code")
    async def code(body: Phone):
        await runtime.send_code(body.phone)
        return {"ok": True}

    @app.post("/api/telegram/login")
    async def telegram_login(body: LoginCode):
        await runtime.sign_in(body.code, body.password)
        return {"ok": True}

    @app.get("/api/telegram/dialogs")
    async def dialogs():
        return await runtime.dialogs()

    @app.post("/api/telegram/chat")
    async def chat(body: Chat):
        matches = [dialog for dialog in await runtime.dialogs() if dialog["id"] == body.id]
        if not matches:
            raise ValueError("请选择当前账号可访问的群或频道")
        settings = store.settings()
        settings.update(chat=body.id, chat_title=matches[0]["title"])
        store.put("settings", settings)
        runtime.schedule_apply()
        return {"ok": True}

    @app.post("/api/telegram/reconnect")
    async def reconnect():
        runtime.schedule_apply()
        return {"ok": True}

    @app.post("/api/telegram/logout")
    async def telegram_logout():
        if store.tasks(statuses={"downloading", "waiting", "retrying", "extracting", "organizing"}):
            raise ValueError("请先暂停下载，并等待解压整理结束后再退出 Telegram")
        await runtime.logout_telegram()
        return {"ok": True}

    @app.post("/api/watcher")
    async def watcher(body: Enabled):
        settings = store.settings()
        if body.enabled and (not runtime.account or not settings["chat"]):
            raise ValueError("请先登录 Telegram 并选择收集群")
        settings["enabled"] = body.enabled
        store.put("settings", settings)
        runtime.schedule_apply()
        return {"ok": True}

    @app.get("/api/history")
    async def history(page: int = 1, status: str = "", search: str = ""):
        if page < 1 or len(search) > 255:
            raise ValueError("无效的记录查询")
        return store.history(page, status, search)

    @app.post("/api/history/{task_id}/extract")
    async def retry(task_id: int):
        await runtime.retry_extraction(task_id)
        return {"ok": True}

    @app.get("/api/history/{task_id}")
    async def task_detail(task_id: int):
        task = store.task(task_id)
        if not task:
            raise HTTPException(404, "任务不存在")
        task["group_members"] = [dict(id=item["id"], filename=item["filename"], status=item["status"], downloaded=item["downloaded"], size=item["size"])
                                  for item in store.group(task.get("group_id", ""))] if task.get("group_id") else []
        return task

    @app.post("/api/history/{task_id}/action")
    async def task_action(task_id: int, body: TaskAction):
        await runtime.task_action(task_id, body.action)
        return {"ok": True}

    @app.post("/api/queue")
    async def queue(body: QueuePause):
        await runtime.queue_action(body.paused)
        return {"ok": True}

    @app.get("/api/files")
    async def files(path: str = "", page: int = 1, search: str = ""):
        if page < 1 or len(path) > 4096 or len(search) > 255:
            raise ValueError("无效的文件查询")
        return await asyncio.to_thread(browse, download_dir, path, page, search)

    @app.post("/api/files/preview")
    async def preview(body: FolderSelection):
        return await runtime.preview_folder(body.path)

    @app.post("/api/files/organize")
    async def organize(body: OrganizeSelection):
        await runtime.organize_folder(body.token)
        return {"ok": True}

    @app.get("/api/files/job")
    async def organize_job():
        job = store.get("manual_job", {})
        plan = job.get("plan", {})
        return dict(status=job.get("status", ""), error=job.get("error", ""), total=len(plan.get("moves", [])),
                    done=sum(bool(move["done"]) for move in plan.get("moves", [])), result=job.get("result"))

    @app.get("/api/logs")
    async def logs(name: str = "collector.log"):
        content = await asyncio.to_thread(read_log, log_dir, name)
        return dict(name=name, content=content, files=[file.name for file in sorted(log_dir.glob("collector.log*")) if file.is_file()])

    @app.get("/api/logs/download")
    async def log_download(name: str = "collector.log"):
        read_log(log_dir, name)  # Validate against the fixed log filename allowlist.
        file = log_dir / name
        if not file.is_file():
            raise HTTPException(404, "日志文件不存在")
        return FileResponse(file, filename=name, media_type="text/plain")

    static = Path(__file__).parent / "static"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="console")
    return app


def main():
    # One process owns Telegram's session and SQLite connection; do not use multiple workers.
    uvicorn.run(create_app(), host=os.environ.get("WEB_HOST", "127.0.0.1"),
                port=int(os.environ.get("WEB_PORT", "18880")), access_log=False, log_config=None)


if __name__ == "__main__":
    main()
