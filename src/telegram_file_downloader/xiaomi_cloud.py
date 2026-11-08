"""Xiaomi web account and gallery protocol; independent of the Telegram runtime."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import mimetypes
import os
import re
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from urllib.parse import quote, urljoin, urlsplit
from uuid import uuid4

import httpx
from PIL import Image

from .console_store import ConsoleStore
from .image_library import image_time


CLOUD = "https://i.mi.com"
ACCOUNT = "https://account.xiaomi.com"
ACCOUNT_HOSTS = ("account.xiaomi.com",)
CLOUD_HOSTS = ("i.mi.com",)
STORAGE_HOSTS = ("i.mi.com", "mi-fds.com", "fds.api.xiaomi.com", "mi-img.com", "ksyuncs.com", "ks-cdn.com", "ksyun.com", "xmssdn.micloud.mi.com")
THUMBNAIL_HOSTS = STORAGE_HOSTS
ID_PATTERN = r"^[0-9]{1,32}$"
CONNECTION_PATTERN = r"^[a-f0-9]{32}$"
BLOCK_SIZE = 4 * 1024 * 1024
UPLOAD_LIMIT = {"image": 100 * 1024**2, "video": 4 * 1024**3}
ALBUM_NAMES = {"1": "相机", "2": "屏幕截图", "1000": "隐私相册"}
THUMBNAIL_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
THUMBNAIL_LIMIT = 512 * 1024
THUMBNAIL_CACHE_BYTES = 64 * 1024**2
THUMBNAIL_CACHE_SECONDS = 15 * 60
DAY_PATTERN = r"^[0-9]{8}$"
LOGGER = logging.getLogger(__name__)


class XiaomiError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def milliseconds():
    return time.time_ns() // 1_000_000


def xiaomi_url(value, hosts):
    try:
        parts = urlsplit(value) if isinstance(value, str) else None
        if (parts and parts.scheme == "https" and parts.hostname and parts.port in {None, 443}
                and parts.username is None and not parts.fragment
                and any(parts.hostname == host or parts.hostname.endswith("." + host) for host in hosts)):
            return value
    except ValueError:
        pass
    raise XiaomiError("小米返回了无法使用的地址，操作已停止")


def response_json(response):
    try:
        value = json.loads(response.text.removeprefix("&&&START&&&"))
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise XiaomiError("小米返回了无法识别的响应")
    return value


def page_data(data, key):
    if not isinstance(data, dict) or type(data.get("isLastPage")) is not bool:
        raise XiaomiError("小米云相册列表格式有变化，请稍后再试")
    entries, last = data.get(key), data["isLastPage"]
    # The web client allows the media array to be absent when there are no more files.
    if key == "galleries" and last and entries is None:
        return [], last
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise XiaomiError("小米云相册列表格式有变化，请稍后再试")
    return entries, last


def remote_id(value):
    value = str(value)
    if not re.fullmatch(ID_PATTERN, value):
        raise XiaomiError("小米云相册返回了无法识别的文件或相册编号")
    return value


def receipt_record(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("id", "sha1", "size", "groupId", "status", "sortTime", "dateTaken", "dateModified", "createTime") if key in value}


def record_time(record):
    for key in ("sortTime", "dateTaken", "dateModified", "createTime"):
        value = record.get(key)
        if type(value) is int and value != 0:
            return value
    return None


def upload_media(name):
    if not name.strip() or name != name.strip() or re.search(r"[\\/\x00-\x1f\x7f]", name):
        raise XiaomiError("请输入有效的云端文件名", 400)
    suffix = PurePath(name).suffix.lower()
    mime = {".jfif": "image/jpeg", ".heic": "image/heic", ".heif": "image/heif", ".avci": "image/avci"}.get(suffix)
    mime = mime or mimetypes.guess_type("file" + suffix)[0] or ""
    kind = mime.split("/", 1)[0]
    if kind not in {"image", "video"}:
        raise XiaomiError("只能上传图片和视频，请保留文件扩展名", 400)
    return kind, mime


def upload_dates(file, kind, modified_at=None):
    info = os.fstat(file.fileno())
    birth = getattr(info, "st_birthtime", None) if modified_at is None else None
    created = round(birth * 1000) if birth is not None else None
    modified = info.st_mtime_ns // 1_000_000 if modified_at is None else modified_at
    taken = created if created is not None else modified
    if kind == "image":
        try:
            file.seek(0)
            with Image.open(file) as image:
                taken, _ = image_time(image, {"created_ms": created, "mtime_ns": modified * 1_000_000})
        except (OSError, ValueError, SyntaxError) as exc:
            LOGGER.warning("Image date metadata unavailable; using file time: %s", type(exc).__name__)
        finally:
            file.seek(0)
    return {"dateTaken": taken, "dateModified": modified}


@dataclass
class QrLogin:
    id: str
    owner: str
    image: bytes
    media_type: str
    deadline: float
    last_poll: float
    state: str = "waiting"
    error: str = ""


class XiaomiCloud:
    def __init__(self, store: ConsoleStore):
        self.store = store
        self.http = httpx.AsyncClient(trust_env=False, timeout=20, follow_redirects=False)
        self.qr: QrLogin | None = None
        self.qr_task: asyncio.Task | None = None
        self.ticket: tuple[str, str, float] | None = None
        self.token_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.thumbnail_slots = asyncio.Semaphore(4)
        self.day_slots = asyncio.Semaphore(2)
        self.thumbnail_sources = OrderedDict()
        self.thumbnail_source_size = 0
        self.thumbnail_contents = OrderedDict()
        self.thumbnail_content_size = 0
        self.thumbnail_tasks = {}
        self.thumbnail_pause_until = 0.0
        self.media_snapshots = OrderedDict()

    async def close(self):
        tasks = list(self.thumbnail_tasks.values())
        for pending in tasks:
            pending.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        task = self.qr_task
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.http.aclose()

    def account(self):
        account = self.store.get("xiaomi_account")
        if not account:
            return None
        return {"connection": account["connection"], "label": "尾号 " + account["userId"][-4:]}

    def local_owner(self, connection):
        account = self.store.get("xiaomi_account")
        if not account or account["connection"] != connection:
            raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
        return account["userId"]

    def disconnect(self, connection):
        if self.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束后再断开连接", 409)
        account = self.account()
        if not account or account["connection"] != connection:
            raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
        self.store.put("xiaomi_account", None)
        self.ticket = None
        self.thumbnail_sources.clear()
        self.thumbnail_contents.clear()
        self.thumbnail_content_size = 0
        for task in self.thumbnail_tasks.values():
            task.cancel()
        self.thumbnail_tasks.clear()
        self.media_snapshots.clear()
        self.thumbnail_source_size = 0
        self.thumbnail_pause_until = 0.0

    async def request(self, method, url, *, cookies=None, headers=None, timeout=20, stream=False, **kwargs):
        # Construct the request directly: redirects and the client's cookie jar must not forward credentials.
        try:
            request = httpx.Request(method, url, cookies=cookies, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                **(headers or {}),
            }, extensions={"timeout": httpx.Timeout(timeout, connect=15).as_dict()}, **kwargs)
            return await self.http.send(request, stream=stream)
        except httpx.TimeoutException:
            raise XiaomiError("连接小米超时，请刷新确认结果后再试", 504) from None
        except (httpx.RequestError, httpx.InvalidURL):
            raise XiaomiError("无法连接小米，请检查运行工作台的设备能否访问小米云", 503) from None
        finally:
            self.http.cookies.clear()

    @staticmethod
    def check_http(response):
        if response.status_code == 429:
            raise XiaomiError("小米云暂时限制请求，请稍后再试", 429)
        if response.status_code in {401, 403}:
            data = response_json(response) if "json" in response.headers.get("content-type", "") else {}
            if data.get("isSecondValidation"):
                raise XiaomiError("请先在小米云网页版打开相册并完成安全验证", 409)
            raise XiaomiError("小米云拒绝访问，请检查账号权限或重新连接", 409)
        if not response.is_success:
            raise XiaomiError(f"小米请求失败（HTTP {response.status_code}）")

    async def start_qr(self, owner):
        if self.account():
            raise XiaomiError("请先断开当前小米账号", 409)
        if self.qr_task:
            self.qr_task.cancel()
        self.qr = None
        cookies = {"deviceId": f"wb_{uuid4()}", "sdkVersion": "3.4.1"}
        response = await self.request("GET", ACCOUNT + "/pass/serviceLogin", cookies=cookies,
                                      params={"sid": "i.mi.com", "_json": "true", "_locale": "zh_CN"})
        self.check_http(response)
        cookies.update((cookie.name, cookie.value) for cookie in response.cookies.jar)
        sign = response_json(response)
        if not all(isinstance(sign.get(key), str) and sign[key] for key in ("qs", "callback", "_sign")):
            raise XiaomiError("小米未返回扫码登录参数")
        response = await self.request("GET", ACCOUNT + "/longPolling/loginUrl", cookies=cookies, params={
            "_qrsize": 480, "qs": sign["qs"], "callback": sign["callback"], "_sign": sign["_sign"],
            "serviceParam": sign.get("serviceParam", ""), "sid": "i.mi.com", "_locale": "zh_CN",
            "_dc": milliseconds(), "needTheme": "false", "showActiveX": "false", "bizDeviceType": "",
        })
        self.check_http(response)
        cookies.update((cookie.name, cookie.value) for cookie in response.cookies.jar)
        data = response_json(response)
        qr_url = xiaomi_url(data.get("qr"), (*ACCOUNT_HOSTS, "mi-img.com"))
        poll_url = xiaomi_url(data.get("lp"), ACCOUNT_HOSTS)
        image = await self.request("GET", qr_url)
        self.check_http(image)
        mime = image.headers.get("content-type", "").split(";", 1)[0]
        if mime not in {"image/png", "image/jpeg", "image/gif"} or len(image.content) > 512 * 1024:
            raise XiaomiError("小米未返回可显示的二维码")
        timeout = data.get("timeout")
        now = time.monotonic()
        deadline = now + (min(timeout, 300) if type(timeout) is int and timeout > 0 else 300) + 15
        qr = self.qr = QrLogin(uuid4().hex, owner, image.content, mime, deadline, now)
        self.qr_task = asyncio.create_task(self.poll_qr(qr, poll_url, cookies))
        return {"id": qr.id}

    def qr_session(self, session_id, owner):
        qr = self.qr
        if not qr or qr.id != session_id or qr.owner != owner:
            raise XiaomiError("扫码会话已结束，请重新生成二维码", 404)
        qr.last_poll = time.monotonic()
        return qr

    def cancel_qr(self, session_id, owner):
        self.qr_session(session_id, owner)
        if self.qr_task:
            self.qr_task.cancel()
        self.qr = None

    async def poll_qr(self, qr, url, cookies):
        try:
            while (remaining := qr.deadline - time.monotonic()) > 0 and time.monotonic() - qr.last_poll < 30:
                try:
                    response = await self.request("GET", url, cookies=cookies, timeout=min(75, remaining))
                except XiaomiError as exc:
                    if exc.status != 504:
                        raise
                else:
                    if response.status_code in {408, 504}:
                        await asyncio.sleep(0.5)
                        continue
                    self.check_http(response)
                    cookies.update((cookie.name, cookie.value) for cookie in response.cookies.jar)
                    result = response_json(response)
                    user = str(result.get("userId") or cookies.get("userId", ""))
                    token = result.get("passToken") or cookies.get("passToken")
                    if re.fullmatch(ID_PATTERN, user) and isinstance(token, str) and token:
                        if time.monotonic() - qr.last_poll >= 30 or not self.store.authorized(qr.owner):
                            qr.state = "expired"
                            return
                        qr.state = "verifying"
                        account = {"userId": user, "passToken": token, "connection": uuid4().hex}
                        service = await self.exchange(account)
                        await self.album_page(account, service, 0)
                        if (self.qr is not qr or time.monotonic() - qr.last_poll >= 30
                                or not self.store.authorized(qr.owner)):
                            qr.state = "expired"
                            return
                        self.store.put("xiaomi_account", account)
                        self.ticket = (account["connection"], service, time.monotonic() + 600)
                        qr.state = "connected"
                        return
                await asyncio.sleep(0.5)
            qr.state = "expired"
        except XiaomiError as exc:
            qr.state, qr.error = "failed", str(exc)
        except sqlite3.Error:
            qr.state, qr.error = "failed", "小米账号保存失败，请检查工作台数据目录"
        finally:
            qr.image = b""

    async def exchange(self, account):
        cookies = {"userId": account["userId"], "passToken": account["passToken"], "deviceId": f"wb_{uuid4()}"}
        response = await self.request("GET", CLOUD + "/api/user/login", cookies=cookies,
                                      params={"ts": milliseconds(), "followUp": CLOUD, "_locale": "zh_CN"})
        self.check_http(response)
        data = response_json(response).get("data")
        login = xiaomi_url(data.get("loginUrl") if isinstance(data, dict) else None, ACCOUNT_HOSTS)
        response = await self.request("GET", login, cookies=cookies)
        location = response.headers.get("location")
        if not response.is_redirect or not location:
            self.check_http(response)
            raise XiaomiError("小米账号凭据无法换取云服务会话，请完成安全验证后重新连接", 409)
        callback = xiaomi_url(urljoin(login, location), CLOUD_HOSTS)
        response = await self.request("GET", callback, cookies=cookies)
        if not response.is_redirect:
            self.check_http(response)
        service = next((cookie.value for cookie in response.cookies.jar if cookie.name == "serviceToken"), None)
        if not service:
            raise XiaomiError("小米账号会话已失效，请断开后重新扫码", 409)
        return service

    async def auth(self, connection):
        async with self.token_lock:
            account = self.store.get("xiaomi_account")
            if not account or account["connection"] != connection:
                raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
            if self.ticket and self.ticket[0] == connection and self.ticket[2] > time.monotonic():
                return account, self.ticket[1]
            service = await self.exchange(account)
            current = self.account()
            if not current or current["connection"] != connection:
                raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
            self.ticket = (connection, service, time.monotonic() + 600)
            return account, service

    async def gallery(self, account, service, path, *, query=None, form=None):
        cookies = {"userId": account["userId"], "serviceToken": service}
        if form is None:
            response = await self.request("GET", CLOUD + path, cookies=cookies, params={"ts": milliseconds(), **(query or {})})
        else:
            response = await self.request("POST", CLOUD + path, cookies=cookies,
                                          headers={"Origin": CLOUD, "Referer": CLOUD + "/gallery/h5"},
                                          data={**form, "serviceToken": service})
        if response.status_code == 401:
            self.ticket = None
        self.check_http(response)
        result = response_json(response)
        code = result.get("code")
        if type(code) is not int:
            raise XiaomiError("小米云相册没有返回操作结果")
        if code in {11010, 11001}:
            raise XiaomiError("该账号需要加密上传，请在小米云网页版完成上传", 409)
        if code == 50006:
            raise XiaomiError("小米云空间不足", 409)
        if code != 0:
            raise XiaomiError(f"小米云相册拒绝了操作（错误码 {code}）")
        return result.get("data")

    async def album_page(self, account, service, page):
        data = await self.gallery(account, service, "/gallery/user/album/list", query={
            "pageNum": page, "pageSize": 20, "isShared": "false", "numOfThumbnails": 1,
        })
        return page_data(data, "albums")

    async def albums(self, connection):
        account, service = await self.auth(connection)
        items, page = [], 0
        while True:
            entries, last = await self.album_page(account, service, page)
            for entry in entries:
                album_id = remote_id(entry.get("albumId"))
                album = {"id": album_id, "name": ALBUM_NAMES.get(album_id) or entry.get("name") or album_id}
                thumbnails = entry.get("thumbnails")
                if isinstance(thumbnails, list) and thumbnails and isinstance(thumbnails[0], dict):
                    cover = thumbnails[0]
                    if not cover.get("encryptInfo") and self.cache_thumbnail(connection, "album:" + album_id, cover.get("url")):
                        album["cover"] = f"/api/xiaomi/album-cover/{album_id}?connection={connection}"
                items.append(album)
            if last:
                return items
            if not entries:
                raise XiaomiError("小米云相册未返回完整列表")
            page += 1

    async def timeline(self, connection, album_id):
        account, service = await self.auth(connection)
        for attempt in range(2):
            state = await self.gallery(account, service, "/gallery/user/lite/index/prepare", form={})
            if not isinstance(state, dict) or type(state.get("isReady")) is not bool:
                raise XiaomiError("小米云日期索引格式有变化，请稍后再试")
            if state["isReady"]:
                break
            if attempt == 0 and state.get("isRetriable") is True:
                await asyncio.sleep(1)
            else:
                raise XiaomiError("小米云正在准备日期索引，请稍后点击刷新", 503)
        data = await self.gallery(account, service, "/gallery/user/timeline", query={"albumId": album_id, "isShared": "false"})
        counts = data.get("dayCount", {}) if isinstance(data, dict) else None
        if not isinstance(counts, dict):
            raise XiaomiError("小米云日期索引格式有变化，请稍后再试")
        for day, count in counts.items():
            self.validate_day(day)
            if type(count) is not int or count < 0:
                raise XiaomiError("小米云日期索引数量无效")
        return {"days": [{"date": day, "count": counts[day]} for day in sorted(counts, reverse=True) if counts[day]]}

    @staticmethod
    def validate_day(day):
        try:
            if not isinstance(day, str) or not re.fullmatch(DAY_PATTERN, day):
                raise ValueError
            datetime.strptime(day, "%Y%m%d")
        except ValueError:
            raise XiaomiError("日期必须是有效的 YYYYMMDD", 400) from None

    async def media_page(self, connection, album_id, page, size, day=None, end_day=None):
        account, service = await self.auth(connection)
        query = {"albumId": album_id, "pageNum": page, "pageSize": size, "isShared": "false"}
        if day is not None:
            self.validate_day(day)
            end_day = day if end_day is None else end_day
            self.validate_day(end_day)
            query.update(startDate=day, endDate=end_day)
        data = await self.gallery(account, service, "/gallery/user/galleries", query=query)
        return page_data(data, "galleries")

    async def day_media(self, connection, album_id, day, page):
        async with self.day_slots:
            entries, last = await self.media_page(connection, album_id, page, 30, day)
        if not entries and not last:
            raise XiaomiError("小米云未返回完整的当日列表，请刷新日期索引")
        items = [self.public_media(item, connection) for item in entries if item.get("type") in {"image", "video"}]
        self.remember_media(connection, album_id, items)
        return {"items": items, "last": last}

    def remember_media(self, connection, album, items):
        for media in items:
            key = (connection, album, media["id"])
            self.media_snapshots[key] = media
            self.media_snapshots.move_to_end(key)
            while len(self.media_snapshots) > 8192:
                self.media_snapshots.popitem(last=False)

    def selected_media(self, connection, album, media_id):
        self.local_owner(connection)
        item = self.media_snapshots.get((connection, album, media_id))
        if not item:
            raise XiaomiError("文件预览已过期，请刷新相册或重新匹配文件名", 409)
        return item

    def cache_thumbnail(self, connection, key, source):
        if isinstance(source, str):
            if source.startswith("data:"):
                header, _, encoded = source.partition(",")
                if not (header.removeprefix("data:").removesuffix(";base64") in THUMBNAIL_TYPES
                        and header.endswith(";base64") and len(encoded) <= THUMBNAIL_LIMIT):
                    return False
            elif len(source) <= 4096 and source.startswith(("https://", "/")):
                try:
                    source = xiaomi_url(urljoin(CLOUD, source), THUMBNAIL_HOSTS)
                except XiaomiError:
                    return False
            else:
                return False
            key = (connection, key)
            if self.thumbnail_sources.get(key) != source:
                self.forget_thumbnail(key)
            self.thumbnail_source_size += len(source) - len(self.thumbnail_sources.pop(key, ""))
            self.thumbnail_sources[key] = source
            while len(self.thumbnail_sources) > 4096 or self.thumbnail_source_size > 32 * 1024**2:
                expired_key, expired = self.thumbnail_sources.popitem(last=False)
                self.thumbnail_source_size -= len(expired)
                self.forget_thumbnail(expired_key)
            return True
        return False

    def public_media(self, item, connection=None):
        media_id = remote_id(item.get("id"))
        result = {"id": media_id, "name": item.get("fileName") or "未命名", "kind": item["type"],
                  "size": item.get("size"), "taken_at": item.get("dateTaken"),
                  "sort_time": item.get("sortTime") or item.get("dateTaken") or item.get("dateModified") or item.get("createTime")}
        info = item.get("thumbnailInfo")
        # Thumbnail encryption is independent of the original file's encryption.
        if (connection and isinstance(info, dict) and not info.get("encryptInfo")
                and self.cache_thumbnail(connection, media_id, info.get("data"))):
            result["thumbnail"] = f"/api/xiaomi/thumbnail/{media_id}?connection={connection}"
        return result

    def forget_thumbnail(self, key):
        previous = self.thumbnail_contents.pop(key, None)
        if previous:
            self.thumbnail_content_size -= len(previous[0])

    async def thumbnail(self, connection, media_id):
        self.local_owner(connection)
        key = (connection, media_id)
        cached = self.thumbnail_contents.get(key)
        if cached and cached[3] > time.monotonic():
            self.thumbnail_contents.move_to_end(key)
            self.thumbnail_sources.move_to_end(key)
            return cached[:3]
        self.forget_thumbnail(key)
        task = self.thumbnail_tasks.get(key)
        if task is None:
            task = asyncio.create_task(self.load_thumbnail(connection, media_id))
            self.thumbnail_tasks[key] = task
            def finished(done):
                if self.thumbnail_tasks.get(key) is done:
                    self.thumbnail_tasks.pop(key)
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def load_thumbnail(self, connection, media_id):
        key = (connection, media_id)
        source = self.thumbnail_sources.get(key)
        if not source and re.fullmatch(ID_PATTERN, media_id):
            # Retained album views can outlive the bounded source-address cache.
            async with self.thumbnail_slots:
                account, service = await self.auth(connection)
                data = await self.gallery(account, service, "/gallery/thumbnails", query={"ids": media_id, "type": "small"})
            entries = data.get("idTothumbnails") if isinstance(data, dict) else None
            if not isinstance(entries, list):
                raise XiaomiError("小米未返回可显示的缩略图", 404)
            for entry in entries:
                if not isinstance(entry, dict) or str(entry.get("id")) != media_id:
                    continue
                thumbnails = entry.get("thumbnails")
                info = thumbnails.get("small") if isinstance(thumbnails, dict) else None
                if (isinstance(info, dict) and not entry.get("encryptInfo") and not info.get("encryptInfo")
                        and self.cache_thumbnail(connection, media_id, info.get("data"))):
                    source = self.thumbnail_sources[key]
                    break
        if not source:
            raise XiaomiError("缩略图不可用，请刷新相册", 404)
        data, media_type = await self.fetch_thumbnail(connection, source)
        self.local_owner(connection)
        result = (data, media_type, '"' + uuid4().hex + '"')
        if self.thumbnail_sources.get(key) == source:
            self.forget_thumbnail(key)
            self.thumbnail_contents[key] = (*result, time.monotonic() + THUMBNAIL_CACHE_SECONDS)
            self.thumbnail_content_size += len(data)
            while len(self.thumbnail_contents) > 1024 or self.thumbnail_content_size > THUMBNAIL_CACHE_BYTES:
                self.forget_thumbnail(next(iter(self.thumbnail_contents)))
        return result

    async def fetch_thumbnail(self, connection, url):
        async with self.thumbnail_slots:
            current = self.account()
            if not current or current["connection"] != connection:
                raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
            if url.startswith("data:"):
                header, _, encoded = url.partition(",")
                try:
                    return base64.b64decode(encoded, validate=True), header[5:-7]
                except (ValueError, binascii.Error):
                    raise XiaomiError("小米未返回可显示的缩略图", 404) from None
            if time.monotonic() < self.thumbnail_pause_until:
                raise XiaomiError("小米云暂时限制缩略图请求，请稍后刷新", 429)
            for _ in range(3):
                cookies = None
                if urlsplit(url).hostname == "i.mi.com":
                    account, service = await self.auth(connection)
                    cookies = {"userId": account["userId"], "serviceToken": service}
                response = await self.request("GET", url, cookies=cookies, stream=True,
                                              headers={"Referer": CLOUD + "/gallery/h5", "Accept-Encoding": "identity"})
                try:
                    if response.is_redirect and response.headers.get("location"):
                        url = xiaomi_url(urljoin(url, response.headers["location"]), THUMBNAIL_HOSTS)
                        continue
                    if response.status_code == 429:
                        retry = response.headers.get("retry-after", "")
                        delay = int(retry) if retry.isascii() and retry.isdigit() and len(retry) <= 9 else 30
                        self.thumbnail_pause_until = time.monotonic() + max(30, delay)
                        self.check_http(response)
                    media_type = response.headers.get("content-type", "").partition(";")[0].lower()
                    if (not response.is_success or media_type not in THUMBNAIL_TYPES
                            or response.headers.get("content-encoding", "identity") != "identity"):
                        raise XiaomiError("小米未返回可显示的缩略图", 404)
                    data = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=64 * 1024):
                        data.extend(chunk)
                        if len(data) > THUMBNAIL_LIMIT:
                            raise XiaomiError("缩略图超过大小限制", 413)
                    return bytes(data), media_type
                except httpx.RequestError:
                    raise XiaomiError("缩略图连接中断，请刷新后重试", 503) from None
                finally:
                    await response.aclose()
            raise XiaomiError("缩略图跳转未完成", 404)

    async def media(self, connection, album_id, page, wall=False):
        entries, last = await self.media_page(connection, album_id, page, 20 if wall else 30)
        items = [self.public_media(item, connection if wall else None)
                 for item in entries if item.get("type") in {"image", "video"}]
        self.remember_media(connection, album_id, items)
        return {"items": items, "last": last}

    async def match_media(self, connection, album_id, page, names):
        entries, last = await self.media_page(connection, album_id, page, 200)
        if not entries and not last:
            raise XiaomiError("小米云未返回完整相册列表，请重新匹配")
        matches = [self.public_media(item, connection) for item in entries
                   if item.get("type") == "image" and isinstance(item.get("fileName"), str) and item["fileName"] in names
                   and (item.get("groupId") is None or str(item["groupId"]) == album_id)]
        self.remember_media(connection, album_id, matches)
        return {"items": matches, "last": last, "marker": remote_id(entries[-1].get("id")) if entries else ""}

    async def recycle(self, connection, media_id):
        if self.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)
        async with self.write_lock:
            account, service = await self.auth(connection)
            # The web gallery uses info/delete for trash and separate purge endpoints for permanent deletion.
            await self.gallery(account, service, "/gallery/info/delete", form={"id": media_id})
            key = (connection, media_id)
            self.forget_thumbnail(key)
            self.thumbnail_source_size -= len(self.thumbnail_sources.pop(key, ""))
            for snapshot in list(self.media_snapshots):
                if snapshot[0] == connection and snapshot[2] == media_id:
                    self.media_snapshots.pop(snapshot)

    async def upload(self, connection, album, name, kind, mime, size, file, *, modified_at=None):
        account, service = await self.auth(connection)
        dates = await asyncio.to_thread(upload_dates, file, kind, modified_at)
        digest, blocks = await asyncio.to_thread(upload_blocks, file, size)
        content = {"type": kind, "groupId": album, "mimeType": mime, "fileName": name,
                   "title": PurePath(name).stem, "sha1": digest, "size": size, **dates}
        data = await self.gallery(account, service, "/gallery/user/full", form={
            "data": json.dumps({"content": content, "block_infos": blocks}, ensure_ascii=False),
            "isClientUploadThumbnail": "false",
        })
        if not isinstance(data, dict) or not isinstance(data.get("content"), dict):
            raise XiaomiError("小米未返回上传记录，请先在相册中确认结果")
        media_id = remote_id(data["content"].get("id"))
        if data.get("fileExists") is True:
            record = receipt_record(data["content"])
            return {"id": media_id, "exists": True, "sha1": digest, "record": record, "lookup_time": record_time(record)}
        kss = data.get("kss")
        if (not isinstance(kss, dict) or not isinstance(kss.get("node_urls"), list) or not kss["node_urls"]
                or not isinstance(kss.get("block_metas"), list) or len(kss["block_metas"]) != len(blocks)
                or not isinstance(kss.get("file_meta"), str) or not kss["file_meta"]):
            raise XiaomiError("小米未返回完整的分片上传参数")
        node = xiaomi_url(kss["node_urls"][0], STORAGE_HOSTS).rstrip("/")
        if urlsplit(node).query:
            raise XiaomiError("小米返回了无法使用的存储地址")
        file_meta = kss["file_meta"]
        commits = []
        for block, meta in zip(blocks, kss["block_metas"]):
            if not isinstance(meta, dict):
                raise XiaomiError("小米未返回有效的分片参数")
            chunk = await asyncio.to_thread(file.read, block["size"])
            if len(chunk) != block["size"]:
                raise XiaomiError("上传临时文件读取不完整，请重新选择原文件")
            commit = meta.get("commit_meta")
            if meta.get("is_existed") != 1:
                block_meta = meta.get("block_meta")
                if not isinstance(block_meta, str) or not block_meta:
                    raise XiaomiError("小米未返回有效的分片参数")
                # The storage service supplies URL-ready opaque metadata; keep its percent escapes.
                url = (f"{node}/upload_block_chunk?chunk_pos=0&file_meta={quote(file_meta, safe='%+/=')}"
                       f"&block_meta={quote(block_meta, safe='%+/=')}")
                response = await self.request("POST", url, content=chunk, timeout=120,
                                              headers={"Content-Type": "application/octet-stream", "Origin": CLOUD})
                self.check_http(response)
                commit = response_json(response).get("commit_meta")
            if not isinstance(commit, str) or not commit:
                raise XiaomiError("小米存储未确认分片上传")
            commits.append({"commit_meta": commit})
        account, service = await self.auth(connection)
        committed = await self.gallery(account, service, f"/gallery/user/full/{media_id}/storage", form={
            "data": json.dumps({"kss": {"file_meta": file_meta, "commit_metas": commits}}),
        })
        record = receipt_record(committed.get("content") if isinstance(committed, dict) else None)
        return {"id": media_id, "exists": False, "sha1": digest, "record": record,
                "lookup_time": record_time(record) or record_time(data["content"])}


def upload_blocks(file, size):
    # Xiaomi's upload protocol requires a file SHA-1 and SHA-1/MD5 per 4 MiB block.
    digest = hashlib.sha1(usedforsecurity=False)
    blocks = []
    file.seek(0)
    remaining = size
    while remaining:
        length = min(BLOCK_SIZE, remaining)
        block = file.read(length)
        if len(block) != length:
            raise XiaomiError("文件读取不完整，请重新选择原文件", 400)
        digest.update(block)
        blocks.append({"size": length, "sha1": hashlib.sha1(block, usedforsecurity=False).hexdigest(),
                       "md5": hashlib.md5(block, usedforsecurity=False).hexdigest()})
        remaining -= length
    file.seek(0)
    return digest.hexdigest(), blocks
