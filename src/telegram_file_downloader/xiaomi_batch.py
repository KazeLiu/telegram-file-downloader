"""Upload a fixed selection of finished files from the download root."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from stat import S_ISREG
from uuid import uuid4

from .storage import RecycleBin, file_version, inside, is_link
from .xiaomi_cloud import UPLOAD_LIMIT, XiaomiError, receipt_record, record_time, remote_id, upload_media
from .xiaomi_upload_journal import UploadJournal


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


def local_digest(root, item):
    path, _ = selected_file(root, item)
    with path.open("rb") as file:
        if file_version(os.fstat(file.fileno())) != item["version"]:
            raise ValueError("本地文件已变化，请刷新后重试")
        digest = hashlib.file_digest(file, "sha1").hexdigest()
        if file_version(os.fstat(file.fileno())) != item["version"]:
            raise ValueError("核对期间本地文件已变化，已保留原文件")
    return digest


class XiaomiBatch:
    def __init__(self, cloud, root):
        self.cloud = cloud
        self.root = root
        self.journal = UploadJournal(cloud.store)
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
        return self.cloud.local_owner(connection)

    def files(self, owner, album, items):
        known = self.journal.confirmed(owner, album, str(self.root.resolve()))
        return [dict(item, uploaded=(item["name"], item["version"]) in known) for item in items]

    def get_job(self, connection, job_id="", album=""):
        owner = self.account(connection)
        job = self.job
        active = job and (job["state"] not in {"complete", "stopped"}
                          or bool(job["verification"] and job["verification"]["active"]))
        if not (job and job["owner"] == owner and (job_id or active)
                and (not job_id or job["id"] == job_id)
                and (not album or job["album"] == album)):
            job = self.journal.load(owner, job_id, album)
        if job:
            job["connection"] = connection
            if "gate" not in job:
                job["gate"] = asyncio.Event()
                job["gate"].set()
        return job

    def idle(self):
        if self.cloud.write_lock.locked():
            raise XiaomiError("请等待当前云端操作结束", 409)

    async def start(self, connection, album, selected, *, recover=False):
        owner = self.account(connection)
        self.idle()
        if album == "1000":
            raise XiaomiError("请在小米云网页版向隐私相册上传", 400)
        if len({item["name"] for item in selected}) != len(selected):
            raise ValueError("上传清单中有重复文件，请重新选择")
        await self.cloud.write_lock.acquire()
        job = dict(id=uuid4().hex, connection=connection, album=album, state="verifying" if recover else "uploading",
                              owner=owner, root=str(self.root.resolve()), created=time.time(), mode="recover" if recover else "upload",
                              error="", done=0, revision=0,
                              verification=None,
                              gate=asyncio.Event(),
                              items=[dict(item, status="waiting", error="") for item in selected])
        job["gate"].set()
        try:
            self.journal.save(job, initial=True)
        except sqlite3.Error:
            self.cloud.write_lock.release()
            raise
        self.job = job
        LOGGER.info("Xiaomi batch started batch=%s album=%s files=%s concurrency=%s", job["id"], album, len(selected), UPLOAD_CONCURRENCY)
        self.task = asyncio.create_task(self.recover(job) if recover else self.run(job), name="xiaomi-local-upload")
        return job["id"]

    async def recover(self, job):
        """Rebuild lost receipts from current album contents, without uploading anything."""
        progress = job["verification"] = dict(active=True, phase="recovery", done=0, total=len(job["items"]),
                                               pages=0, page=0, start=None, end=None, error="")
        remaining = {item["name"]: item for item in job["items"]}
        digests, seen = {}, set()
        self.journal.save(job)
        try:
            page = 0
            while remaining and job["state"] != "stopping":
                progress["page"] = page + 1
                entries, last = await self.cloud.media_page(job["connection"], job["album"], page, 200)
                progress["pages"] += 1
                ids = tuple(str(entry.get("id")) for entry in entries)
                if not last and (not ids or ids in seen):
                    raise XiaomiError("小米云未返回完整相册列表，未确认的文件已保留")
                seen.add(ids)
                for entry in entries:
                    if job["state"] == "stopping":
                        break
                    name = entry.get("fileName")
                    item = remaining.get(name) if isinstance(name, str) else None
                    if not item or entry.get("type") != item["kind"] or str(entry.get("size")) != str(item["size"]):
                        continue
                    if item["name"] not in digests:
                        try:
                            digests[item["name"]] = await asyncio.to_thread(local_digest, self.root, item)
                        except (OSError, ValueError) as exc:
                            item.update(status="failed", error=str(exc))
                            remaining.pop(item["name"])
                            job["done"] += 1
                            self.journal.save(job, item)
                            continue
                    receipt = (remote_id(entry.get("id")), digests[item["name"]], str(item["size"]))
                    if matches_receipt(entry, receipt, job["album"], scoped=True):
                        record = receipt_record(entry)
                        item.update(status="verified", error="", receipt=receipt, record=record, lookup_time=record_time(record))
                        remaining.pop(item["name"])
                        progress["done"] += 1
                        job["done"] += 1
                        self.journal.save(job, item)
                self.journal.save(job)
                if job["state"] == "stopping":
                    break
                if last:
                    for item in remaining.values():
                        item["error"] = "目标相册未找到同名、同大小且内容一致的文件；保留本地，可另选上传"
                        self.journal.save(job, item)
                    job["done"] = len(job["items"])
                    break
                page += 1
        except asyncio.CancelledError:
            job.update(state="stopping", error="程序关闭中断了找回；已确认记录已保存，其余文件仍保留")
            raise
        except XiaomiError as exc:
            job["error"] = "找回未完成：" + str(exc)
        except OSError:
            job["error"] = "本地读取中断，未确认的文件已保留"
        except sqlite3.Error:
            job["error"] = "上传记录无法保存，请检查数据卷可用空间；未确认的本地文件已保留"
        finally:
            progress["active"] = False
            job.update(state="stopped" if job["state"] == "stopping" else "complete", revision=job["revision"] + 1)
            self.cloud.write_lock.release()
            self.journal.save(job)

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
        self.journal.save(job)

    def view(self, connection, page, job_id="", album=""):
        job = self.get_job(connection, job_id, album)
        if not job:
            return None
        items = job["items"]
        counts = Counter(item["status"] for item in items)
        eligible = sum(item["status"] == "verified" and item.get("kind") == "image" for item in items)
        offset = (page - 1) * PAGE_SIZE
        active_files = [item["name"] for item in items if item["status"] == "uploading"]
        current = "、".join(active_files)
        check_error = job["verification"]["error"] if job["verification"] else ""
        return dict(id=job["id"], album=job["album"], state=job["state"], current=current,
                    mode=job["mode"], created=job["created"],
                    error="；".join(error for error in (job["error"], check_error) if error), done=job["done"], total=len(items), page_size=PAGE_SIZE,
                    counts=counts, eligible=eligible, revision=job["revision"],
                    active_files=active_files,
                    verification=job["verification"],
                    items=[{key: item[key] for key in ("name", "status", "error")}
                           for item in items[offset:offset + PAGE_SIZE]])

    def completed(self, connection, job_id):
        self.account(connection)
        self.idle()
        job = self.get_job(connection, job_id)
        if not job or job["state"] not in {"complete", "stopped"}:
            raise XiaomiError("上传批次已变化，请刷新后再操作", 409)
        if job["root"] != str(self.root.resolve()):
            raise XiaomiError("本批次的本地目录与当前目录不同，已停止操作", 409)
        self.job = job
        return job

    async def retry(self, connection, job_id):
        job = self.completed(connection, job_id)
        if job["mode"] == "recover":
            raise XiaomiError("请重新找回上传记录，或选择下一批上传未确认文件", 409)
        candidates = [item for item in job["items"] if item["status"] in {"failed", "waiting"}]
        if not candidates:
            raise XiaomiError("没有失败或未上传的文件，请刷新批次结果", 409)
        await self.cloud.write_lock.acquire()
        for item in candidates:
            item.update(status="waiting", error="")
        job.update(state="uploading", error="", verification=None, done=len(job["items"]) - len(candidates),
                   revision=job["revision"] + 1)
        job["gate"].set()
        try:
            self.journal.save(job, initial=True)
        except sqlite3.Error:
            job["state"] = "stopped"
            self.cloud.write_lock.release()
            raise
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
        except asyncio.CancelledError:
            job.update(state="stopping", error="程序关闭中断了上传；已保存回执，可重新核对或找回上传记录")
            raise
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
            self.journal.save(job)

    async def upload_item(self, job, item):
        item["status"] = "uploading"
        self.journal.save(job, item)
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
            self.journal.save(job, item)

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
            self.journal.save(job, item)
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
                            self.journal.save(job, item)
                    remaining.difference_update(found)
                    if last:
                        break
                    page += 1
                for item in selected:
                    if item["receipt"] in remaining:
                        item["error"] = "未在目标相册的日期范围找到一致记录，本地文件已保留" if start else "未在目标相册找到一致记录，本地文件已保留"
                        self.journal.save(job, item)
        except XiaomiError as exc:
            progress["error"] = "云端核对未完成：" + str(exc)
            raise
        finally:
            progress["active"] = False
            job["revision"] += 1
            self.journal.save(job)

    async def recycle_images(self, job, candidates):
        candidates = [item for item in candidates if item["status"] == "verified"]
        progress = job["verification"] = dict(active=True, phase="local", done=0, total=len(candidates), pages=0, page=0, start=None, end=None, error="")
        moved = 0
        try:
            with RecycleBin(self.root) as recycle:
                for item in candidates:
                    try:
                        record = recycle.db.execute("SELECT state FROM items WHERE id=?", (item.get("recycle_id", ""),)).fetchone()
                        if record and record["state"] in {"trashed", "purged", "restored"}:
                            item.update(status="kept" if record["state"] == "restored" else "recycled",
                                        error="图片已被还原，不再继续旧回收操作" if record["state"] == "restored" else "")
                        else:
                            path, _ = selected_file(self.root, item)
                            item.setdefault("recycle_id", uuid4().hex)
                            self.journal.save(job, item)
                            recycle.move(path, item["recycle_id"], "xiaomi_upload")
                            item.update(status="recycled", error="")
                            moved += 1
                    except (FileNotFoundError, ValueError) as exc:
                        item.update(status="kept", error=str(exc))
                    except OSError as exc:
                        item["error"] = str(exc)
                    progress["done"] += 1
                    self.journal.save(job, item)
                    await asyncio.sleep(0)
        finally:
            progress["active"] = False
            self.journal.save(job)
            LOGGER.log(logging.WARNING if progress["done"] != moved else logging.INFO,
                       "Xiaomi batch recycle finished batch=%s processed=%s total=%s moved=%s retained=%s",
                       job["id"], progress["done"], len(candidates), moved, progress["done"] - moved)
        return moved
