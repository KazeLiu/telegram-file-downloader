"""Upload a fixed selection of finished files from the download root."""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from pathlib import Path
from stat import S_ISREG
from uuid import uuid4

from .storage import RecycleBin, inside, is_link
from .xiaomi_cloud import UPLOAD_LIMIT, XiaomiError, upload_media


LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 60


def file_version(stat):
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"


def local_media(root):
    items = []
    with os.scandir(root) as entries:
        for entry in entries:
            try:
                if not entry.is_file(follow_symlinks=False) or is_link(entry):
                    continue
                kind, _ = upload_media(entry.name)
                # DirEntry.stat omits file identity on Windows.
                info = os.stat(entry.path, follow_symlinks=False)
            except (XiaomiError, FileNotFoundError):
                continue
            if 0 < info.st_size < UPLOAD_LIMIT[kind]:
                items.append(dict(name=entry.name, kind=kind, size=info.st_size, version=file_version(info)))
    return sorted(items, key=lambda item: (item["name"].casefold(), item["name"]))


def selected_file(root, item):
    name = item["name"]
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("只允许选择下载根目录的媒体文件")
    path = inside(root, name)
    info = path.stat()
    if not S_ISREG(info.st_mode) or file_version(info) != item["version"]:
        raise ValueError("本地文件已变化，请刷新后重新选择")
    return path, info


class XiaomiBatch:
    def __init__(self, cloud, root):
        self.cloud = cloud
        self.root = root
        self.job = None
        self.task = None

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    def account(self, connection):
        account = self.cloud.account()
        if not account or account["connection"] != connection:
            raise XiaomiError("小米账号连接已变化，请刷新页面", 409)

    def idle(self):
        if self.cloud.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)

    async def start(self, connection, album, selected):
        self.account(connection)
        self.idle()
        if album == "1000":
            raise XiaomiError("请在小米云网页版向隐私相册上传", 400)
        if len({item["name"] for item in selected}) != len(selected):
            raise ValueError("上传清单中有重复文件，请重新选择")
        await self.cloud.write_lock.acquire()
        job = self.job = dict(id=uuid4().hex, connection=connection, album=album, state="uploading",
                              current="", error="", done=0, revision=0,
                              items=[dict(item, status="waiting", error="") for item in selected])
        self.task = asyncio.create_task(self.run(job), name="xiaomi-local-upload")

    def view(self, connection, page):
        self.account(connection)
        job = self.job
        if not job or job["connection"] != connection:
            return None
        items = job["items"]
        counts = Counter(item["status"] for item in items)
        eligible = sum(item["status"] == "verified" and item.get("kind") == "image" for item in items)
        offset = (page - 1) * PAGE_SIZE
        return dict(id=job["id"], album=job["album"], state=job["state"], current=job["current"],
                    error=job["error"], done=job["done"], total=len(items), page_size=PAGE_SIZE,
                    counts=counts, eligible=eligible, revision=job["revision"],
                    items=[{key: item[key] for key in ("name", "status", "error")}
                           for item in items[offset:offset + PAGE_SIZE]])

    def completed(self, connection, job_id):
        self.account(connection)
        self.idle()
        job = self.job
        if not job or job["id"] != job_id or job["connection"] != connection or job["state"] != "complete":
            raise XiaomiError("上传批次已变化，请刷新后再操作", 409)
        return job

    async def run(self, job):
        try:
            if not any(album["id"] == job["album"] for album in await self.cloud.albums(job["connection"])):
                raise XiaomiError("目标相册已不存在或不可访问，未上传任何文件", 409)
            for item in job["items"]:
                job["current"] = item["name"]
                try:
                    path, info = selected_file(self.root, item)
                    kind, mime = upload_media(item["name"])
                    if not 0 < info.st_size < UPLOAD_LIMIT[kind]:
                        raise ValueError("文件为空或超过小米云上传大小限制")
                    with path.open("rb") as file:
                        if file_version(os.fstat(file.fileno())) != item["version"]:
                            raise ValueError("本地文件已变化，请刷新后重新选择")
                        result = await self.cloud.upload(job["connection"], job["album"], item["name"],
                                                         kind, mime, info.st_size, file)
                        if file_version(os.fstat(file.fileno())) != item["version"]:
                            raise ValueError("上传期间本地文件已变化，已保留原文件")
                    item.update(kind=kind, status="uploaded", receipt=(result["id"], result["sha1"], str(info.st_size)))
                except XiaomiError as exc:
                    item.update(status="failed", error=str(exc))
                    if exc.status in {409, 429, 503, 504}:
                        job["error"] = "已停止后续上传：" + str(exc)
                        break
                except (OSError, ValueError) as exc:
                    item.update(status="failed", error=str(exc))
                finally:
                    job["done"] += 1
            job.update(state="verifying", current="")
            try:
                await self.verify(job)
            except XiaomiError as exc:
                job["error"] = (job["error"] + "；" if job["error"] else "") + "云端核对未完成：" + str(exc)
        except XiaomiError as exc:
            job["error"] = str(exc)
        except Exception as exc:
            LOGGER.error("Xiaomi batch upload interrupted: %s", type(exc).__name__)
            job["error"] = "批量上传中断，未确认的文件仍保留在本地"
        finally:
            job.update(state="complete", current="")
            self.cloud.write_lock.release()

    async def verify(self, job, candidates=None):
        if candidates is None:
            candidates = [item for item in job["items"] if item["status"] in {"uploaded", "verified"}]
        remaining = {item["receipt"] for item in candidates}
        page, seen = 0, set()
        while remaining:
            entries, last = await self.cloud.media_page(job["connection"], job["album"], page, 200)
            ids = tuple(str(item.get("id")) for item in entries)
            if not last and (not ids or ids in seen):
                raise XiaomiError("小米云未返回完整相册列表，本地文件已保留")
            seen.add(ids)
            remaining.difference_update((str(item.get("id")), str(item.get("sha1", "")).lower(), str(item.get("size")))
                                        for item in entries
                                        if item.get("groupId") is None or str(item["groupId"]) == job["album"])
            if last:
                break
            page += 1
        for item in candidates:
            item["status"] = "uploaded" if item["receipt"] in remaining else "verified"
        job["revision"] += 1

    async def recycle_images(self, candidates):
        moved = 0
        with RecycleBin(self.root) as recycle:
            for item in candidates:
                if item["status"] != "verified":
                    continue
                try:
                    path, _ = selected_file(self.root, item)
                    recycle.move(path, item.setdefault("recycle_id", uuid4().hex), "xiaomi_upload")
                except (FileNotFoundError, ValueError) as exc:
                    item.update(status="kept", error=str(exc))
                except OSError as exc:
                    item["error"] = str(exc)
                else:
                    item.update(status="recycled", error="")
                    moved += 1
                await asyncio.sleep(0)
        return moved
