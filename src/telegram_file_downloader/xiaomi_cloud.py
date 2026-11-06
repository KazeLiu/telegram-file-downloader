"""Xiaomi web account and gallery protocol; independent of the Telegram runtime."""
from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import PurePath
from urllib.parse import quote, urljoin, urlsplit
from uuid import uuid4

import httpx

from .console_store import ConsoleStore


CLOUD = "https://i.mi.com"
ACCOUNT = "https://account.xiaomi.com"
ACCOUNT_HOSTS = ("account.xiaomi.com",)
CLOUD_HOSTS = ("i.mi.com",)
STORAGE_HOSTS = ("i.mi.com", "mi-fds.com", "fds.api.xiaomi.com", "mi-img.com", "ksyuncs.com", "ks-cdn.com", "ksyun.com")
ID_PATTERN = r"^[0-9]{1,32}$"
CONNECTION_PATTERN = r"^[a-f0-9]{32}$"
BLOCK_SIZE = 4 * 1024 * 1024
ALBUM_NAMES = {"1": "相机", "2": "屏幕截图", "1000": "隐私相册"}


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


def upload_media(name):
    if not name.strip() or name != name.strip() or re.search(r"[\\/\x00-\x1f\x7f]", name):
        raise XiaomiError("请输入有效的云端文件名", 400)
    suffix = PurePath(name).suffix.lower()
    mime = {".heic": "image/heic", ".heif": "image/heif", ".avci": "image/avci"}.get(suffix)
    mime = mime or mimetypes.guess_type("file" + suffix)[0] or ""
    kind = mime.split("/", 1)[0]
    if kind not in {"image", "video"}:
        raise XiaomiError("只能上传图片和视频，请保留文件扩展名", 400)
    return kind, mime


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

    async def close(self):
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

    def disconnect(self, connection):
        if self.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束后再断开连接", 409)
        account = self.account()
        if not account or account["connection"] != connection:
            raise XiaomiError("小米账号连接已变化，请刷新页面", 409)
        self.store.put("xiaomi_account", None)
        self.ticket = None

    async def request(self, method, url, *, cookies=None, headers=None, timeout=20, **kwargs):
        # Construct the request directly: redirects and the client's cookie jar must not forward credentials.
        try:
            request = httpx.Request(method, url, cookies=cookies, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                **(headers or {}),
            }, extensions={"timeout": httpx.Timeout(timeout, connect=15).as_dict()}, **kwargs)
            return await self.http.send(request)
        except httpx.TimeoutException:
            raise XiaomiError("连接小米超时，请刷新确认结果后再试", 504) from None
        except (httpx.RequestError, httpx.InvalidURL):
            raise XiaomiError("无法连接小米，请检查运行工作台的设备能否访问小米云") from None
        finally:
            self.http.cookies.clear()

    @staticmethod
    def check_http(response):
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
                items.append({"id": album_id, "name": ALBUM_NAMES.get(album_id) or entry.get("name") or album_id})
            if last:
                return items
            if not entries:
                raise XiaomiError("小米云相册未返回完整列表")
            page += 1

    async def media(self, connection, album_id, page):
        account, service = await self.auth(connection)
        data = await self.gallery(account, service, "/gallery/user/galleries", query={
            "albumId": album_id, "pageNum": page, "pageSize": 30, "isShared": "false",
        })
        entries, last = page_data(data, "galleries")
        items = [{"id": remote_id(item.get("id")), "name": item.get("fileName") or "未命名",
                  "kind": item["type"], "size": item.get("size"), "taken_at": item.get("dateTaken")}
                 for item in entries if item.get("type") in {"image", "video"}]
        return {"items": items, "last": last}

    async def recycle(self, connection, media_id):
        if self.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)
        async with self.write_lock:
            account, service = await self.auth(connection)
            # The web gallery uses info/delete for trash and separate purge endpoints for permanent deletion.
            await self.gallery(account, service, "/gallery/info/delete", form={"id": media_id})

    async def upload(self, connection, album, name, kind, mime, size, file):
        account, service = await self.auth(connection)
        digest, blocks = await asyncio.to_thread(upload_blocks, file)
        content = {"type": kind, "groupId": album, "mimeType": mime, "fileName": name,
                   "title": PurePath(name).stem, "sha1": digest, "size": size, "dateModified": milliseconds()}
        data = await self.gallery(account, service, "/gallery/user/full", form={
            "data": json.dumps({"content": content, "block_infos": blocks}, ensure_ascii=False),
            "isClientUploadThumbnail": "false",
        })
        if not isinstance(data, dict) or not isinstance(data.get("content"), dict):
            raise XiaomiError("小米未返回上传记录，请先在相册中确认结果")
        media_id = remote_id(data["content"].get("id"))
        if data.get("fileExists") is True:
            return {"id": media_id, "exists": True}
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
        await self.gallery(account, service, f"/gallery/user/full/{media_id}/storage", form={
            "data": json.dumps({"kss": {"file_meta": file_meta, "commit_metas": commits}}),
        })
        return {"id": media_id, "exists": False}


def upload_blocks(file):
    # Xiaomi's upload protocol requires a file SHA-1 and SHA-1/MD5 per 4 MiB block.
    digest = hashlib.sha1(usedforsecurity=False)
    blocks = []
    file.seek(0)
    while block := file.read(BLOCK_SIZE):
        digest.update(block)
        blocks.append({"size": len(block), "sha1": hashlib.sha1(block, usedforsecurity=False).hexdigest(),
                       "md5": hashlib.md5(block, usedforsecurity=False).hexdigest()})
    file.seek(0)
    return digest.hexdigest(), blocks
