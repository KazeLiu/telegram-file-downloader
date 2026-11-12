from __future__ import annotations

import os
import asyncio
import errno
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryFile
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as FastAPIPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from telethon import errors

from .console_store import ConsoleStore
from .config import compact_connection_input
from .web_runtime import WebRuntime, telegram_proxy
from .diagnostics import configure_logs, read_log
from .organizer import browse, plan_counts
from .image_library import IMAGE_EXTENSIONS, ImageLibrary, recycle_thumbnail
from .image_dedup import ImageDedup
from .saved_image_check import SavedImageCheck
from .linked_recycle import LinkedRecycle
from .recycle_cleanup import RecycleCleaner
from .storage import RecycleBin, inside, restore_batch
from .playback import queue as playback_queue, selected_media
from .xiaomi_batch import XiaomiBatch, local_media
from .xiaomi_local import XiaomiLocalIndex
from .xiaomi_cloud import CONNECTION_PATTERN, DAY_PATTERN, ID_PATTERN, UPLOAD_LIMIT, XiaomiCloud, XiaomiError, upload_media


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
    delete_psd: bool | None = None

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
    action: Literal["pause", "resume", "retry", "extract_only", "mark_manual_extracted"]
    member_ids: list[int] | None = Field(default=None, min_length=1)


class QueuePause(BaseModel):
    paused: bool


class FolderSelection(BaseModel):
    path: str = Field(default="", max_length=4096)
    delete_psd: bool = False


class OrganizeSelection(BaseModel):
    token: str = Field(default="", max_length=32, pattern=r"^[a-f0-9]*$")


class ImageSelection(BaseModel):
    id: int = Field(gt=0)
    version: str = Field(max_length=80)


class ImagesSelection(BaseModel):
    items: list[ImageSelection] = Field(min_length=1, max_length=200)


class PlaybackSelection(BaseModel):
    roots: list[Annotated[str, Field(pattern=r"^(?:downloads|[a-f0-9]{32})$")]] = Field(min_length=1, max_length=100)
    kind: Literal["image", "video", "mixed"] = "mixed"


class RestoreSelection(BaseModel):
    ids: list[Annotated[str, Field(pattern=r"^[a-f0-9]{32}(?:-[0-9]+)?$")]] = Field(min_length=1, max_length=200)


class XiaomiConnection(BaseModel):
    connection: str = Field(pattern=CONNECTION_PATTERN)


class XiaomiRecycle(XiaomiConnection):
    id: str = Field(pattern=ID_PATTERN)
    token: str | None = Field(default=None, pattern=CONNECTION_PATTERN)


class XiaomiNameMatch(XiaomiConnection):
    album: str = Field(pattern=ID_PATTERN)
    page: int = Field(ge=0)
    names: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(min_length=1, max_length=2000)


class XiaomiAlbumSelection(XiaomiConnection):
    album: str = Field(pattern=ID_PATTERN)


class XiaomiFolderBinding(XiaomiAlbumSelection):
    path: str = Field(max_length=4096)


class XiaomiRecyclePreview(XiaomiAlbumSelection):
    ids: list[Annotated[str, Field(pattern=ID_PATTERN)]] = Field(min_length=1, max_length=2000)


class XiaomiLocalFile(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    size: int | None = Field(default=None, ge=0)


class XiaomiLocalStatus(XiaomiAlbumSelection):
    items: list[XiaomiLocalFile] = Field(default_factory=list, max_length=2000)


class LocalMediaSelection(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=128)


class XiaomiBatchSelection(XiaomiConnection):
    album: str = Field(pattern=ID_PATTERN)
    items: list[LocalMediaSelection] = Field(min_length=1)


class XiaomiBatchAction(XiaomiConnection):
    job: str = Field(pattern=CONNECTION_PATTERN)


class XiaomiBatchControl(XiaomiBatchAction):
    action: Literal["pause", "resume", "stop"]


class XiaomiBatchRecycle(XiaomiBatchAction):
    revision: int = Field(ge=0)


class DedupScan(XiaomiConnection):
    roots: list[Annotated[str, Field(pattern=CONNECTION_PATTERN)]] = Field(min_length=1, max_length=100)
    distance: int = Field(default=10, ge=0, le=24)


class DedupSelection(XiaomiConnection):
    run: str = Field(pattern=CONNECTION_PATTERN)
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=200)


class DedupScores(DedupSelection):
    reference: int = Field(gt=0)
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=40)


class DedupRecycle(XiaomiConnection):
    token: str = Field(pattern=CONNECTION_PATTERN)


class WorkflowImageSettings(XiaomiConnection):
    enabled: bool
    roots: list[Annotated[str, Field(pattern=CONNECTION_PATTERN)]] = Field(default_factory=list, max_length=100)


def create_app():
    data_dir = Path(os.environ.get("DATA_DIR", str(Path.cwd() / "data"))).resolve()
    download_dir = Path(os.environ.get("DOWNLOAD_DIR", str(Path.cwd() / "downloads"))).resolve()
    log_dir = configure_logs(data_dir)
    store = ConsoleStore(data_dir)
    library = ImageLibrary(download_dir, data_dir)
    runtime = WebRuntime(store, data_dir, download_dir, library.start_scan)
    xiaomi = XiaomiCloud(store)
    batch = XiaomiBatch(xiaomi, download_dir)
    local_index = XiaomiLocalIndex(data_dir, lambda: (
        runtime.operation_lock.locked() or library.state["running"] or xiaomi.write_lock.locked()
        or bool(runtime.local_jobs) or bool(runtime.processor and runtime.processor.running)
        or bool(runtime.manual_task and not runtime.manual_task.done())))
    linked_recycle = LinkedRecycle(store, xiaomi, local_index)
    dedup = ImageDedup(data_dir, store, xiaomi, local_index)
    saved_check = SavedImageCheck(library, dedup, local_index, xiaomi, store,
        lambda: runtime.operation_lock.locked() or library.state["running"] or bool(dedup.task and not dedup.task.done()))
    library.saved_check = saved_check
    runtime.check_images = saved_check.queue_batch
    recycle_cleaner = RecycleCleaner(local_index, download_dir, runtime.operation_lock)
    failures: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        local_index.start()
        saved_check.start()
        recycle_cleaner.start()
        try:
            yield
        finally:
            await saved_check.close()
            await dedup.close()
            await recycle_cleaner.close()
            await local_index.close()
            await batch.close()
            await xiaomi.close()
            await runtime.close()
            await library.close()
            store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in {"GET", "HEAD"}:
                origin = request.headers.get("origin")
                if origin != f"{request.url.scheme}://{request.headers.get('host')}":
                    return JSONResponse({"detail": "请从本页面操作"}, status_code=403)
                upload = request.method == "POST" and request.url.path == "/api/xiaomi/upload"
                content_type = "application/octet-stream" if upload else "application/json"
                if request.headers.get("content-type", "").split(";")[0] != content_type:
                    return JSONResponse({"detail": "请选择要上传的文件" if upload else "请求需要 JSON 内容"}, status_code=415)
            public = {"/api/auth/status", "/api/auth/setup", "/api/auth/login"}
            if request.url.path not in public and not store.authorized(request.cookies.get("console_session", "")):
                return JSONResponse({"detail": "请先登录管理页面"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(XiaomiError)
    async def xiaomi_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

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

    @app.get("/api/xiaomi/account")
    async def xiaomi_account():
        return {"account": xiaomi.account()}

    @app.post("/api/xiaomi/disconnect")
    async def xiaomi_disconnect(body: XiaomiConnection):
        xiaomi.disconnect(body.connection)
        saved_check.request()
        return {"ok": True}

    @app.post("/api/xiaomi/qr")
    async def xiaomi_qr(request: Request):
        if xiaomi.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)
        async with xiaomi.write_lock:
            return await xiaomi.start_qr(request.cookies["console_session"])

    @app.get("/api/xiaomi/qr/{session_id}")
    async def xiaomi_qr_status(session_id: str, request: Request):
        qr = xiaomi.qr_session(session_id, request.cookies["console_session"])
        return {"state": qr.state, "error": qr.error}

    @app.get("/api/xiaomi/qr/{session_id}/image")
    async def xiaomi_qr_image(session_id: str, request: Request):
        qr = xiaomi.qr_session(session_id, request.cookies["console_session"])
        if not qr.image:
            raise XiaomiError("二维码已结束", 404)
        return Response(qr.image, media_type=qr.media_type)

    @app.post("/api/xiaomi/qr/{session_id}/cancel")
    async def xiaomi_qr_cancel(session_id: str, request: Request):
        xiaomi.cancel_qr(session_id, request.cookies["console_session"])
        return {"ok": True}

    @app.get("/api/xiaomi/albums")
    async def xiaomi_albums(connection: str = Query(pattern=CONNECTION_PATTERN)):
        return {"items": await xiaomi.albums(connection)}

    @app.get("/api/xiaomi/media")
    async def xiaomi_media(connection: str = Query(pattern=CONNECTION_PATTERN),
                           album: str = Query(pattern=ID_PATTERN), page: int = Query(default=0, ge=0), wall: bool = False):
        return await xiaomi.media(connection, album, page, wall)

    @app.get("/api/xiaomi/timeline")
    async def xiaomi_timeline(connection: str = Query(pattern=CONNECTION_PATTERN), album: str = Query(pattern=ID_PATTERN)):
        return await xiaomi.timeline(connection, album)

    @app.get("/api/xiaomi/day")
    async def xiaomi_day(connection: str = Query(pattern=CONNECTION_PATTERN), album: str = Query(pattern=ID_PATTERN),
                         date: str = Query(pattern=DAY_PATTERN), page: int = Query(default=0, ge=0)):
        return await xiaomi.day_media(connection, album, date, page)

    @app.post("/api/xiaomi/local/status")
    async def xiaomi_local_status(body: XiaomiLocalStatus):
        owner = xiaomi.local_owner(body.connection)
        return await asyncio.to_thread(local_index.compare, owner, body.album, [item.model_dump() for item in body.items])

    @app.post("/api/xiaomi/local/bind")
    async def xiaomi_local_bind(body: XiaomiFolderBinding):
        owner = xiaomi.local_owner(body.connection)
        try:
            local_index.bind(owner, body.album, body.path.strip())
        except OSError:
            raise ValueError("无法读取此目录，请检查路径、挂载和读取权限") from None
        saved_check.request()
        return {"ok": True}

    @app.post("/api/xiaomi/local/refresh")
    async def xiaomi_local_refresh(body: XiaomiAlbumSelection):
        local_index.refresh(xiaomi.local_owner(body.connection), body.album)
        return {"ok": True}

    @app.post("/api/xiaomi/media/match")
    async def xiaomi_match(body: XiaomiNameMatch):
        return await xiaomi.match_media(body.connection, body.album, body.page, set(body.names))

    @app.get("/api/xiaomi/thumbnail/{media_id}")
    async def xiaomi_thumbnail(request: Request, media_id: Annotated[str, FastAPIPath(pattern=ID_PATTERN)],
                               connection: str = Query(pattern=CONNECTION_PATTERN)):
        return await thumbnail_response(request, connection, media_id)

    @app.get("/api/xiaomi/album-cover/{album_id}")
    async def xiaomi_album_cover(request: Request, album_id: Annotated[str, FastAPIPath(pattern=ID_PATTERN)],
                                  connection: str = Query(pattern=CONNECTION_PATTERN)):
        return await thumbnail_response(request, connection, "album:" + album_id)

    async def thumbnail_response(request, connection, key):
        data, media_type, etag = await xiaomi.thumbnail(connection, key)
        headers = {"Cache-Control": "private, no-cache", "ETag": etag, "Vary": "Cookie", "X-Content-Type-Options": "nosniff"}
        # Revalidate through authentication even when the browser already holds the bytes.
        matches = [tag.strip().removeprefix("W/") for tag in request.headers.get("if-none-match", "").split(",")]
        if etag in matches or "*" in matches:
            return Response(status_code=304, headers=headers)
        return Response(data, media_type=media_type, headers=headers)

    @app.post("/api/xiaomi/recycle")
    async def xiaomi_recycle(body: XiaomiRecycle):
        if body.token:
            ensure_library_idle()
            async with runtime.operation_lock:
                result = await linked_recycle.execute(body.connection, body.id, body.token)
            if result["local_done"]:
                library.start_scan()
            return result
        await xiaomi.recycle(body.connection, body.id)
        return {"ok": True}

    @app.post("/api/xiaomi/recycle/preview")
    async def xiaomi_recycle_preview(body: XiaomiRecyclePreview):
        return linked_recycle.preview(body.connection, body.album, body.ids)

    @app.get("/api/xiaomi/recycle/pending")
    async def xiaomi_recycle_pending(connection: str = Query(pattern=CONNECTION_PATTERN)):
        return {"items": linked_recycle.pending(connection)}

    @app.get("/api/xiaomi/local-media")
    async def xiaomi_local_media(connection: str = Query(pattern=CONNECTION_PATTERN),
                                 album: str | None = Query(default=None, pattern=ID_PATTERN)):
        owner = batch.account(connection)
        items = await asyncio.to_thread(local_media, download_dir)
        return {"items": batch.files(owner, album, items) if album else items}

    @app.get("/api/xiaomi/batch/history")
    async def xiaomi_batch_history(connection: str = Query(pattern=CONNECTION_PATTERN),
                                    album: str = Query(pattern=ID_PATTERN)):
        return {"items": batch.journal.history(batch.account(connection), album)}

    @app.post("/api/xiaomi/batch/recover")
    async def xiaomi_batch_recover(body: XiaomiAlbumSelection):
        owner = batch.account(body.connection)
        items = await asyncio.to_thread(local_media, download_dir)
        if not items:
            raise ValueError("下载根目录没有符合条件的图片或视频")
        items = [item for item in batch.files(owner, body.album, items) if not item["uploaded"]]
        if not items:
            raise ValueError("当前文件均有已确认回执，请在上传记录中选择原批次核对或回收")
        return {"job": await batch.start(body.connection, body.album, items, recover=True)}

    @app.get("/api/xiaomi/batch")
    async def xiaomi_batch(connection: str = Query(pattern=CONNECTION_PATTERN), page: int = Query(default=1, ge=1),
                           job: str | None = Query(default=None, pattern=CONNECTION_PATTERN),
                           album: str | None = Query(default=None, pattern=ID_PATTERN)):
        return {"job": batch.view(connection, page, job or "", album or "")}

    @app.post("/api/xiaomi/batch")
    async def xiaomi_batch_start(body: XiaomiBatchSelection):
        return {"ok": True, "job": await batch.start(body.connection, body.album, [item.model_dump() for item in body.items])}

    @app.post("/api/xiaomi/batch/verify")
    async def xiaomi_batch_verify(body: XiaomiBatchAction):
        job = batch.completed(body.connection, body.job)
        async with xiaomi.write_lock:
            await batch.verify(job, fresh=True)
        return {"ok": True}

    @app.post("/api/xiaomi/batch/control")
    async def xiaomi_batch_control(body: XiaomiBatchControl):
        batch.control(body.connection, body.job, body.action)
        return {"ok": True}

    @app.post("/api/xiaomi/batch/retry")
    async def xiaomi_batch_retry(body: XiaomiBatchAction):
        await batch.retry(body.connection, body.job)
        return {"ok": True}

    @app.post("/api/xiaomi/batch/recycle")
    async def xiaomi_batch_recycle(body: XiaomiBatchRecycle):
        job = batch.completed(body.connection, body.job)
        if job["revision"] != body.revision:
            raise XiaomiError("待回收清单已变化，请刷新后重新确认", 409)
        candidates = [item for item in job["items"] if item["status"] == "verified" and item["kind"] == "image"]
        if not candidates:
            return {"moved": 0}
        ensure_library_idle()
        async with xiaomi.write_lock:
            await batch.verify(job, candidates, fresh=True)
            ensure_library_idle()
            async with runtime.operation_lock:
                moved = await batch.recycle_images(job, candidates)
                job["revision"] += 1
                batch.journal.save(job)
        if moved:
            library.start_scan()
        return {"moved": moved}

    @app.post("/api/xiaomi/upload")
    async def xiaomi_upload(request: Request, connection: str = Query(pattern=CONNECTION_PATTERN),
                            album: str = Query(pattern=ID_PATTERN), name: str = Query(min_length=1, max_length=255),
                            size: int = Query(gt=0), modified_at: int | None = Query(default=None)):
        kind, mime = upload_media(name)
        if album == "1000":
            raise XiaomiError("请在小米云网页版向隐私相册上传", 400)
        if xiaomi.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)
        if size >= UPLOAD_LIMIT[kind]:
            raise XiaomiError("图片需小于 100 MiB，视频需小于 4 GiB", 413)
        length = request.headers.get("content-length", "")
        if length.isdecimal() and int(length) != size:
            raise XiaomiError("上传内容与所选文件大小不符，请重新选择文件", 400)
        async with xiaomi.write_lock:
            account = xiaomi.account()
            if not account or account["connection"] != connection:
                raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
            staging = inside(download_dir, ".tg-work")
            try:
                staging.mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(staging).free < size:
                    raise XiaomiError("下载盘空间不足，无法暂存上传文件", 507)
                with TemporaryFile(dir=staging) as file:
                    received = 0
                    async for chunk in request.stream():
                        received += len(chunk)
                        if received > size:
                            raise XiaomiError("上传内容超过所选文件大小，请重新选择文件", 400)
                        await asyncio.to_thread(file.write, chunk)
                    if received != size:
                        raise XiaomiError("文件未传完整，请重新选择文件", 400)
                    result = await xiaomi.upload(connection, album, name, kind, mime, size, file, modified_at=modified_at)
                    return {"id": result["id"], "exists": result["exists"]}
            except OSError as exc:
                if exc.errno != errno.ENOSPC:
                    raise
                raise XiaomiError("下载盘空间不足，无法暂存上传文件", 507) from None

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
        return store.task_view(task)

    @app.post("/api/history/{task_id}/action")
    async def task_action(task_id: int, body: TaskAction):
        if body.action in {"extract_only", "mark_manual_extracted"} and not body.member_ids:
            raise ValueError("请确认本次要处理的压缩包清单")
        await runtime.task_action(task_id, body.action, body.member_ids)
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
        return await runtime.preview_folder(body.path, body.delete_psd)

    @app.post("/api/files/organize")
    async def organize(body: OrganizeSelection):
        await runtime.organize_folder(body.token)
        return {"ok": True}

    @app.get("/api/files/job")
    async def organize_job():
        job = store.get("manual_job", {})
        counts = store.get(f"progress:{job['plan_key']}", job["summary"]) if "plan_key" in job else plan_counts(job.get("plan", {}))
        return dict(status=job.get("status", ""), error=job.get("error", ""),
                    total=counts["move_total"] + counts["cleanup_total"], done=counts["moved_files"] + counts["cleanup_done"],
                    result=job.get("result"), **counts)

    @app.get("/api/playback/galleries")
    async def playback_galleries():
        return {"items": local_index.recycle_roots(download_dir)}

    @app.post("/api/playback/queue")
    async def load_playback_queue(body: PlaybackSelection):
        galleries = local_index.recycle_roots(download_dir)
        items = await asyncio.to_thread(playback_queue, galleries, body.roots, body.kind)
        return {"items": items}

    @app.get("/api/playback/media")
    async def playback_media(root: str = Query(pattern=r"^(?:downloads|[a-f0-9]{32})$"),
                             path: str = Query(min_length=1, max_length=4096),
                             version: str = Query(min_length=1, max_length=160)):
        file, mime = selected_media(local_index.recycle_roots(download_dir), root, path, version)
        return FileResponse(file, media_type=mime, headers={"Cache-Control": "private, no-store"})

    @app.post("/api/images/scan")
    async def scan_images():
        saved_check.request(refresh=True, force=True)
        return library.start_scan()

    @app.get("/api/images")
    async def images(page: int = 1, candidate: bool = False, search: str = "", after: int | None = None, compressed: bool = False):
        if page < 1 or len(search) > 255 or (after is not None and after < 1):
            raise ValueError("无效的图片查询")
        return library.listing(page, candidate, search, after, compressed)

    @app.get("/api/images/status")
    async def image_status(candidate: bool = False, search: str = "", compressed: bool = False):
        if len(search) > 255:
            raise ValueError("无效的图片查询")
        return library.status(candidate, search, compressed)

    @app.get("/api/images/{image_id}")
    async def image_details(image_id: int):
        return library.picture(image_id)

    @app.get("/api/images/{image_id}/thumbnail")
    async def image_thumbnail(image_id: int, version: str):
        record, _ = library.selected(image_id, version)
        target = library.cache / f"{image_id}.jpg"
        if record["error"] or not target.is_file():
            raise HTTPException(404, "缩略图尚未生成或图片读取失败")
        return FileResponse(target, media_type="image/jpeg")

    @app.get("/api/images/{image_id}/saved/thumbnail")
    async def saved_image_thumbnail(image_id: int, version: str):
        match, _ = saved_check.selected_reference(image_id, version)
        row = dedup.db.execute("SELECT version FROM features WHERE id=?", (match["feature_id"],)).fetchone()
        target = dedup.cache / f"{match['feature_id']}.jpg"
        if not row or row["version"] != match["version"] or not target.is_file():
            raise HTTPException(409, "参考图缓存已变化，请刷新图片后重新检查")
        return FileResponse(target, media_type="image/jpeg")

    @app.get("/api/images/{image_id}/original")
    async def original_image(image_id: int, version: str):
        _, file = library.selected(image_id, version)
        return FileResponse(file)

    @app.get("/api/images/{image_id}/saved/original")
    async def saved_image_original(image_id: int, version: str):
        _, file = saved_check.selected_reference(image_id, version)
        return FileResponse(file)

    def ensure_library_idle():
        if runtime.operation_lock.locked() or store.get("manual_job", {}).get("status") in {"running", "failed", "interrupted"}:
            raise ValueError("请等待当前文件操作结束；存在未完成的手动整理时，请先完成该任务")

    @app.post("/api/images/recycle")
    async def recycle_images(body: ImagesSelection):
        ensure_library_idle()
        moved, failures = [], []
        async with runtime.operation_lock:
            with RecycleBin(download_dir) as recycle:
                for item in body.items:
                    try:
                        record, file = library.selected(item.id, item.version)
                        recycle.move(file, uuid.uuid4().hex, "image")
                        library.remove(item.id)
                        moved.append(item.id)
                    except (OSError, ValueError) as exc:
                        failures.append(dict(id=item.id, error=str(exc)))
                    await asyncio.sleep(0)
        return dict(moved=moved, failures=failures)

    recycle_thumbnail_slots = asyncio.Semaphore(4)

    @app.get("/api/recycle/roots")
    async def recycle_roots():
        return {"items": local_index.recycle_roots(download_dir)}

    @app.get("/api/recycle")
    async def recycle_items(page: int = 1, root: str = "downloads", search: str = ""):
        if page < 1 or len(search) > 255:
            raise ValueError("无效的回收站查询")
        if runtime.operation_lock.locked():
            raise ValueError("文件整理或回收站清理正在进行，请稍后再查看")
        async with runtime.operation_lock:
            directory = local_index.recycle_root(root, download_dir)
            if not directory.is_dir():
                raise ValueError("回收目录不可访问，请检查挂载")
            with RecycleBin(directory) as recycle:
                result = recycle.listing(page, search)
                for item in result["items"]:
                    item["is_image"] = Path(item["original"]).suffix.lower() in IMAGE_EXTENSIONS
                return dict(result, cleanup=dict(recycle_cleaner.state))

    @app.get("/api/recycle/{record_id}/thumbnail")
    async def recycle_image(record_id: Annotated[str, FastAPIPath(pattern=r"^[a-f0-9]{32}(?:-[0-9]+)?$")], request: Request, root: str = "downloads"):
        directory = local_index.recycle_root(root, download_dir)
        try:
            with RecycleBin(directory) as recycle:
                record, file = recycle.preview(record_id)
            if Path(record["original"]).suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError("此文件不是可预览的图片")
            async with recycle_thumbnail_slots:
                if await request.is_disconnected():
                    return Response(status_code=499)
                data = await asyncio.to_thread(recycle_thumbnail, file)
        except (OSError, ValueError, SyntaxError) as exc:
            raise HTTPException(404, str(exc)) from None
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60", "Vary": "Cookie", "X-Content-Type-Options": "nosniff"})

    def restored_directory(directory):
        for source in local_index.db.execute("""SELECT owner,album FROM bindings JOIN roots ON roots.id=bindings.root_id
                                               WHERE roots.path=?""", (str(directory),)).fetchall():
            local_index.refresh(source["owner"], source["album"])
        library.start_scan()

    @app.post("/api/recycle/restore")
    async def restore_items(body: RestoreSelection, root: str = "downloads"):
        ensure_library_idle()
        directory = local_index.recycle_root(root, download_dir)
        async with runtime.operation_lock:
            result = await asyncio.to_thread(restore_batch, directory, body.ids)
        if result["restored"]:
            restored_directory(directory)
        return result

    @app.post("/api/recycle/{record_id}/restore")
    async def restore_item(record_id: str, root: str = "downloads"):
        ensure_library_idle()
        async with runtime.operation_lock:
            directory = local_index.recycle_root(root, download_dir)
            with RecycleBin(directory) as recycle:
                original = recycle.restore(record_id)
        restored_directory(directory)
        return dict(original=original)

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

    @app.get("/api/dedup/automatic")
    async def automatic_image_settings(connection: str = Query(pattern=CONNECTION_PATTERN)):
        return saved_check.settings(connection)

    @app.post("/api/dedup/automatic")
    async def save_automatic_image_settings(body: WorkflowImageSettings):
        return saved_check.save_settings(body.connection, body.enabled, body.roots)

    @app.post("/api/dedup/automatic/refresh")
    async def refresh_automatic_image_cache(body: XiaomiConnection):
        settings = saved_check.settings(body.connection)
        if not settings["enabled"] or not settings["roots"]:
            raise ValueError("请先开启工作流自动检查并保存目录")
        saved_check.request(refresh=True, force=True)
        return {"ok": True}

    @app.get("/api/dedup/sources")
    async def dedup_sources(connection: str = Query(pattern=CONNECTION_PATTERN)):
        return {"items": await dedup.sources(connection)}

    @app.get("/api/dedup/status")
    async def dedup_status(connection: str = Query(pattern=CONNECTION_PATTERN)):
        return {"job": dedup.status(connection), "preview": dedup.preview(connection), "pending": dedup.pending(connection)}

    @app.post("/api/dedup/scan")
    async def dedup_scan(body: DedupScan):
        return await dedup.start(body.connection, body.roots, body.distance)

    @app.post("/api/dedup/cancel")
    async def dedup_cancel(body: XiaomiConnection):
        dedup.cancel(body.connection)
        return {"ok": True}

    @app.get("/api/dedup/groups")
    async def dedup_groups(connection: str = Query(pattern=CONNECTION_PATTERN), run: str = Query(pattern=CONNECTION_PATTERN),
                           page: int = Query(default=1, ge=1)):
        return dedup.groups(connection, run, page)

    @app.get("/api/dedup/groups/{group_id}")
    async def dedup_pictures(group_id: int, connection: str = Query(pattern=CONNECTION_PATTERN),
                             run: str = Query(pattern=CONNECTION_PATTERN), page: int = Query(default=1, ge=1)):
        return dedup.pictures(connection, run, group_id, page)

    @app.get("/api/dedup/errors")
    async def dedup_errors(connection: str = Query(pattern=CONNECTION_PATTERN), run: str = Query(pattern=CONNECTION_PATTERN),
                           page: int = Query(default=1, ge=1)):
        return {"items": dedup.errors(connection, run, page)}

    @app.post("/api/dedup/scores")
    async def dedup_scores(body: DedupScores, request: Request):
        return await dedup.scores(body.connection, body.run, body.reference, body.ids, request.is_disconnected)

    @app.get("/api/dedup/files/{file_id}/thumbnail")
    async def dedup_thumbnail(file_id: int, connection: str = Query(pattern=CONNECTION_PATTERN), run: str = Query(pattern=CONNECTION_PATTERN)):
        dedup.file(connection, run, file_id)
        target = dedup.cache / f"{file_id}.jpg"
        if not target.is_file():
            raise HTTPException(404, "缩略图不可用，请重新扫描")
        return FileResponse(target, media_type="image/jpeg")

    @app.get("/api/dedup/files/{file_id}/original")
    async def dedup_original(file_id: int, connection: str = Query(pattern=CONNECTION_PATTERN), run: str = Query(pattern=CONNECTION_PATTERN)):
        return FileResponse(dedup.file(connection, run, file_id))

    @app.post("/api/dedup/preview")
    async def dedup_preview(body: DedupSelection):
        return await dedup.prepare(body.connection, body.run, body.ids)

    @app.post("/api/dedup/preview/cancel")
    async def dedup_preview_cancel(body: XiaomiConnection):
        dedup.cancel_preview(body.connection)
        return {"ok": True}

    @app.post("/api/dedup/recycle")
    async def dedup_recycle(body: DedupRecycle):
        ensure_library_idle()
        async with runtime.operation_lock:
            result = await dedup.execute(body.connection, body.token)
        if result["local_done"]:
            library.start_scan()
        return result

    @app.post("/api/dedup/recycle/dismiss")
    async def dedup_dismiss(body: DedupRecycle):
        ensure_library_idle()
        dedup.dismiss(body.connection, body.token)
        return {"ok": True}

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
