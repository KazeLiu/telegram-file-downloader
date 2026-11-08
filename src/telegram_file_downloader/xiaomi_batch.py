"""Upload a fixed selection of finished files from the download root."""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from stat import S_ISREG
from uuid import uuid4

from .storage import RecycleBin, file_version, inside, is_link
from .xiaomi_cloud import UPLOAD_LIMIT, XiaomiError, receipt_record, record_time, upload_media


LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 60
UPLOAD_CONCURRENCY = 3


def matches_receipt(record, receipt, album, *, scoped=False):
    identity = (str(record.get("id")), str(record.get("sha1", "")).lower(), str(record.get("size")))
    return (identity == receipt and record.get("status") != "deleted"
            and (str(record.get("groupId")) == album or scoped and record.get("groupId") is None))


def verification_ranges(items):
    dated, undated = [], []
    for index, item in enumerate(items):
        try:
            day = datetime.fromtimestamp(item["lookup_time"] / 1000, timezone.utc).date()
            start, end = day - timedelta(days=1), day + timedelta(days=1)
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            undated.append(item)
        else:
            dated.append((start, end, index, item))
    ranges = []
    for start, end, _, item in sorted(dated):
        # Adjacent windows share one scan; the one-day margin covers timezone boundaries.
        if ranges and start.toordinal() <= ranges[-1][1].toordinal() + 1:
            ranges[-1][1] = max(ranges[-1][1], end)
            ranges[-1][2].append(item)
        else:
            ranges.append([start, end, [item]])
    result = [(start.isoformat().replace("-", ""), end.isoformat().replace("-", ""), selected) for start, end, selected in ranges]
    if undated:
        result.append((None, None, undated))
    return result


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
                              error="", done=0, revision=0,
                              verification=None,
                              gate=asyncio.Event(),
                              items=[dict(item, status="waiting", error="") for item in selected])
        job["gate"].set()
        LOGGER.info("Xiaomi batch started batch=%s album=%s files=%s concurrency=%s", job["id"], album, len(selected), UPLOAD_CONCURRENCY)
        self.task = asyncio.create_task(self.run(job), name="xiaomi-local-upload")

    def control(self, connection, job_id, action):
        self.account(connection)
        job = self.job
        if not job or job["id"] != job_id or job["connection"] != connection:
            raise XiaomiError("上传批次已变化，请刷新后再操作", 409)
        state = job["state"]
        if action == "pause" and state == "uploading":
            job["state"] = "pausing"
            job["gate"].clear()
        elif action == "resume" and state in {"pausing", "paused"}:
            job["state"] = "uploading"
            job["gate"].set()
        elif action == "stop" and state in {"uploading", "pausing", "paused", "verifying"}:
            job["state"] = "stopping"
            job["gate"].set()
        else:
            raise XiaomiError("当前批次状态不支持此操作，请刷新后重试", 409)

    def view(self, connection, page):
        self.account(connection)
        job = self.job
        if not job or job["connection"] != connection:
            return None
        items = job["items"]
        counts = Counter(item["status"] for item in items)
        eligible = sum(item["status"] == "verified" and item.get("kind") == "image" for item in items)
        offset = (page - 1) * PAGE_SIZE
        active_files = [item["name"] for item in items if item["status"] == "uploading"]
        current = "、".join(active_files)
        check_error = job["verification"]["error"] if job["verification"] else ""
        return dict(id=job["id"], album=job["album"], state=job["state"], current=current,
                    error="；".join(error for error in (job["error"], check_error) if error), done=job["done"], total=len(items), page_size=PAGE_SIZE,
                    counts=counts, eligible=eligible, revision=job["revision"],
                    active_files=active_files,
                    verification=job["verification"],
                    items=[{key: item[key] for key in ("name", "status", "error")}
                           for item in items[offset:offset + PAGE_SIZE]])

    def completed(self, connection, job_id):
        self.account(connection)
        self.idle()
        job = self.job
        if not job or job["id"] != job_id or job["connection"] != connection or job["state"] not in {"complete", "stopped"}:
            raise XiaomiError("上传批次已变化，请刷新后再操作", 409)
        return job

    async def retry(self, connection, job_id):
        job = self.completed(connection, job_id)
        candidates = [item for item in job["items"] if item["status"] in {"failed", "waiting"}]
        if not candidates:
            raise XiaomiError("没有失败或未上传的文件，请刷新批次结果", 409)
        await self.cloud.write_lock.acquire()
        for item in candidates:
            item.update(status="waiting", error="")
        job.update(state="uploading", error="", verification=None, done=len(job["items"]) - len(candidates),
                   revision=job["revision"] + 1)
        job["gate"].set()
        LOGGER.info("Xiaomi batch retry batch=%s files=%s concurrency=%s", job["id"], len(candidates), UPLOAD_CONCURRENCY)
        self.task = asyncio.create_task(self.run(job), name="xiaomi-local-upload")

    async def run(self, job):
        pending = deque(item for item in job["items"] if item["status"] == "waiting")

        async def worker():
            while pending:
                await job["gate"].wait()
                if job["state"] == "stopping" or job["error"] or not pending:
                    return
                await self.upload_item(job, pending.popleft())
                if (job["state"] == "pausing" and pending
                        and not any(item["status"] == "uploading" for item in job["items"])):
                    job["state"] = "paused"

        try:
            if not any(album["id"] == job["album"] for album in await self.cloud.albums(job["connection"])):
                raise XiaomiError("目标相册已不存在或不可访问，未上传任何文件", 409)
            async with asyncio.TaskGroup() as workers:
                for _ in range(UPLOAD_CONCURRENCY):
                    workers.create_task(worker())
            unconfirmed = [item for item in job["items"] if item["status"] == "uploaded"]
            if unconfirmed:
                job["state"] = "stopping" if job["state"] == "stopping" else "verifying"
                await self.verify(job, unconfirmed)
        except XiaomiError as exc:
            if job["verification"] is None:
                job["error"] = str(exc)
        except Exception as exc:
            LOGGER.error("Xiaomi batch upload interrupted: %s", type(exc).__name__)
            job["error"] = "批量上传中断，未确认的文件仍保留在本地"
        finally:
            job["state"] = "stopped" if job["state"] == "stopping" else "complete"
            LOGGER.info("Xiaomi batch finished batch=%s state=%s processed=%s counts=%s", job["id"], job["state"], job["done"], dict(Counter(item["status"] for item in job["items"])))
            self.cloud.write_lock.release()

    async def upload_item(self, job, item):
        item["status"] = "uploading"
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
            item.update(kind=kind, status="uploaded", receipt=(result["id"], result["sha1"], str(info.st_size)),
                        record=result["record"], lookup_time=result["lookup_time"])
            if matches_receipt(item["record"], item["receipt"], job["album"]):
                item["status"] = "verified"
            LOGGER.debug("Xiaomi upload completed batch=%s name=%r state=%s server_time=%s", job["id"], item["name"], item["status"], item["lookup_time"])
        except XiaomiError as exc:
            item.update(status="failed", error=str(exc))
            LOGGER.warning("Xiaomi upload failed batch=%s name=%r processed=%s status=%s detail=%s", job["id"], item["name"], job["done"], exc.status, exc)
            if exc.status in {409, 429, 503, 504}:
                job["error"] = "已停止后续上传：" + str(exc)
                job["gate"].set()
        except (OSError, ValueError) as exc:
            item.update(status="failed", error=str(exc))
        finally:
            if item["status"] == "uploading":
                item.update(status="failed", error="上传中断，请核对云端后再试")
            job["done"] += 1

    async def verify(self, job, candidates=None, *, fresh=False):
        if candidates is None:
            candidates = [item for item in job["items"] if item["status"] in {"uploaded", "verified"}]
        progress = job["verification"] = dict(active=True, phase="receipt", done=0, total=len(candidates), pages=0, page=0, start=None, end=None, error="")
        pending = []
        for item in candidates:
            item.update(status="uploaded", error="")
            if not fresh and matches_receipt(item["record"], item["receipt"], job["album"]):
                item["status"] = "verified"
                progress["done"] += 1
            else:
                pending.append(item)
        try:
            for start, end, selected in verification_ranges(pending):
                remaining = {item["receipt"] for item in selected}
                progress.update(phase="date" if start else "album", start=start, end=end, page=0)
                page, seen = 0, set()
                while remaining:
                    progress["page"] = page + 1
                    if start:
                        entries, last = await self.cloud.media_page(job["connection"], job["album"], page, 200, day=start, end_day=end)
                    else:
                        entries, last = await self.cloud.media_page(job["connection"], job["album"], page, 200)
                    progress["pages"] += 1
                    ids = tuple(str(entry.get("id")) for entry in entries)
                    if not last and (not ids or ids in seen):
                        raise XiaomiError("小米云未返回完整相册列表，本地文件已保留")
                    seen.add(ids)
                    found = {}
                    for entry in entries:
                        receipt = (str(entry.get("id")), str(entry.get("sha1", "")).lower(), str(entry.get("size")))
                        if receipt in remaining and matches_receipt(entry, receipt, job["album"], scoped=True):
                            found[receipt] = receipt_record(entry)
                    for item in selected:
                        if item["receipt"] in found and item["status"] != "verified":
                            item.update(status="verified", record=found[item["receipt"]])
                            item["lookup_time"] = record_time(item["record"]) or item["lookup_time"]
                            progress["done"] += 1
                    remaining.difference_update(found)
                    if last:
                        break
                    page += 1
                for item in selected:
                    if item["receipt"] in remaining:
                        item["error"] = "未在目标相册的日期范围找到一致记录，本地文件已保留" if start else "未在目标相册找到一致记录，本地文件已保留"
        except XiaomiError as exc:
            progress["error"] = "云端核对未完成：" + str(exc)
            raise
        finally:
            progress["active"] = False
            job["revision"] += 1

    async def recycle_images(self, job, candidates):
        candidates = [item for item in candidates if item["status"] == "verified"]
        progress = job["verification"] = dict(active=True, phase="local", done=0, total=len(candidates), pages=0, page=0, start=None, end=None, error="")
        moved = 0
        try:
            with RecycleBin(self.root) as recycle:
                for item in candidates:
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
                    progress["done"] += 1
                    await asyncio.sleep(0)
        finally:
            progress["active"] = False
            LOGGER.log(logging.WARNING if progress["done"] != moved else logging.INFO,
                       "Xiaomi batch recycle finished batch=%s processed=%s total=%s moved=%s retained=%s",
                       job["id"], progress["done"], len(candidates), moved, progress["done"] - moved)
        return moved
