from __future__ import annotations

import asyncio
import copy
import time
from pathlib import Path

from telethon import errors, types

from .archives import ExtractionError, extract_archive, multipart
from .console_store import now
from .downloader import DownloadQueue
from .files import message_filename

def select_media(message, settings):
    file = message.file
    if not file:
        return None
    name = message_filename(message)
    if message.photo or (file.mime_type or "").startswith("image/"):
        return (message, "photo", "最高可用尺寸") if settings["photos"] else None
    if message.video or (file.mime_type or "").startswith("video/"):
        if not settings["videos"]:
            return None
        documents = [message.document, *(getattr(message.media, "alt_documents", None) or [])]
        candidates = []
        for document in documents:
            if not document or not (document.mime_type or "").startswith("video/"):
                continue
            for attr in document.attributes:
                if isinstance(attr, types.DocumentAttributeVideo):
                    candidates.append((attr.w * attr.h, document.size, attr.w, attr.h, document))
                    break
        if candidates:
            _, _, width, height, document = max(candidates, key=lambda item: item[:2])
            selected = copy.copy(message)
            selected.media = copy.copy(message.media)
            selected.media.document = document
            selected._file = None
            return selected, "video", f"{width} × {height}"
        return message, "video", "原始附件"
    if settings["archives"] and (Path(name).suffix.lower() in {".zip", ".rar", ".7z"} or multipart(name)):
        return message, "archive", ""
    return None


def size_text(value):
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


class ConsoleProcessor:
    def __init__(self, client, directory, history, recorder, store, settings, operation_lock):
        self.client, self.directory, self.history = client, directory, history
        self.recorder, self.store, self.settings = recorder, store, settings
        self.operation_lock = operation_lock
        self.receipt_disabled_until = 0.0

    async def receipt(self, task):
        if not self.settings["receipts"] or time.monotonic() < self.receipt_disabled_until:
            return
        labels = {"queued": "已接收", "downloading": "下载中", "extracting": "下载完成，正在解压",
                  "completed": "下载完成", "extracted": "下载、解压完成", "failed": "下载失败",
                  "extraction_failed": "下载完成，解压未完成"}
        text = f"{labels.get(task['status'], task['status'])}\n{task['filename']}"
        if task["status"] == "downloading":
            percent = task["downloaded"] * 100 / task["size"] if task["size"] else 0
            eta = f"{int(task['eta'])} 秒" if task["eta"] is not None else "计算中"
            text += f"\n{percent:.1f}% · {size_text(task['speed'])}/s · 剩余 {eta}"
        else:
            text += f"\n{size_text(task['downloaded'])} · 平均 {size_text(task['average_speed'])}/s"
        if task["archive_deleted"]:
            text += "\n原压缩包已删除"
        if task["error"]:
            text += "\n" + task["error"]
        if task["warning"] and not task["warning"].startswith("群回执"):
            text += "\n" + task["warning"]
        chat = int(task["scope"].split(":", 1)[1])
        try:
            if task["receipt_id"]:
                await self.client.edit_message(chat, task["receipt_id"], text, parse_mode=None)
            else:
                sent = await self.client.send_message(chat, text, reply_to=task["message_id"], parse_mode=None)
                self.store.update_task(task["id"], receipt_id=sent.id)
            if self.store.task(task["id"])["warning"].startswith("群回执"):
                self.store.update_task(task["id"], warning="")
        except errors.MessageNotModifiedError:
            pass
        except errors.FloodWaitError as exc:
            self.receipt_disabled_until = time.monotonic() + exc.seconds
            self.store.update_task(task["id"], warning=f"群回执暂时限流，{exc.seconds} 秒后恢复")
        except (errors.RPCError, OSError, ConnectionError):
            self.store.update_task(task["id"], warning="群回执发送失败，请检查群发言权限；下载继续")

    async def process(self, message):
        async with self.operation_lock:
            self.recorder.append_from_text(message.raw_text)
            selection = select_media(message, self.settings)
            if not selection:
                return True
            selected, kind, quality = selection
            task = self.store.create_task(self.history.scope, message.id, message_filename(selected),
                                          kind, selected.file.size, quality)
            # A deleted archive is intentionally absent; the durable task journal is authoritative.
            if task["status"] == "extracted":
                if self.settings["delete_archive"] and not task["archive_deleted"]:
                    await self.unpack(task["id"])
                await self.receipt(self.store.task(task["id"]))
                return True
            if task["status"] in {"completed", "extraction_failed"}:
                return True
            if self.settings["mark_read"]:
                try:
                    await self.client.send_read_acknowledge(message.chat_id, max_id=message.id)
                except (errors.RPCError, OSError, ConnectionError):
                    self.store.update_task(task["id"], warning="已接收任务，但标记已读失败")
            start = time.monotonic()
            last_write, last_receipt = 0.0, 0.0
            last_bytes, last_time = 0, start
            self.store.update_task(task["id"], status="downloading", started_at=task["started_at"] or now(), error="", completed_at=None)

            async def progress(current, total):
                nonlocal last_write, last_receipt, last_bytes, last_time
                moment = time.monotonic()
                if moment - last_write < 1 and current != total:
                    return
                speed = max(0, current - last_bytes) / max(moment - last_time, .001)
                task = self.store.update_task(task_id, downloaded=current, size=total or 0, speed=speed,
                    eta=max(0, (total - current) / speed) if total and speed else None,
                    elapsed=moment - start, average_speed=current / max(moment - start, .001))
                last_write, last_bytes, last_time = moment, current, moment
                if moment - last_receipt >= 10:
                    await self.receipt(task)
                    last_receipt = moment

            task_id = task["id"]
            recovered = self.history.download(message.id)
            recovered_complete = recovered and recovered["ready"] and Path(recovered["path"]).is_file()
            await self.receipt(self.store.task(task_id))
            queue = DownloadQueue(self.client, self.directory, lambda _: None, history=self.history, progress=progress)
            path = await queue.download(selected)
            elapsed = time.monotonic() - start
            if not path:
                task = self.store.update_task(task_id, status="failed", completed_at=now(), speed=0,
                                              eta=None, error="下载失败；保留进度，稍后自动重试")
                await self.receipt(task)
                return False
            should_extract = kind == "archive" and self.settings["extract"]
            task = self.store.update_task(task_id, status="downloaded" if should_extract else "completed", path=str(path),
                downloaded=path.stat().st_size,
                average_speed=task["average_speed"] if recovered_complete else path.stat().st_size / max(elapsed, .001),
                elapsed=task["elapsed"] if recovered_complete else elapsed, speed=0, eta=0, completed_at=now())
            if should_extract:
                await self.unpack(task_id)
            await self.receipt(self.store.task(task_id))
            return True

    async def unpack(self, task_id):
        task = self.store.task(task_id)
        archive = Path(task["path"])
        # Publish intent is saved before deletion; after a crash an already extracted output is reused.
        output = Path(task["output"]) if task["output"] else None
        if not output or not output.is_dir():
            self.store.update_task(task_id, status="extracting", error="", completed_at=None)
            await self.receipt(self.store.task(task_id))
            try:
                output = await extract_archive(archive, self.settings["archive_passwords"])
            except (ExtractionError, OSError) as exc:
                self.store.update_task(task_id, status="extraction_failed", error=str(exc), completed_at=now())
                return
            self.store.update_task(task_id, output=str(output), status="extracted", completed_at=now())
        else:
            self.store.update_task(task_id, status="extracted", completed_at=now())
        if self.settings["delete_archive"] and not task["archive_deleted"]:
            try:
                archive.unlink(missing_ok=True)
                self.store.update_task(task_id, archive_deleted=True)
            except OSError:
                self.store.update_task(task_id, warning="解压完成，但原包删除失败；请检查目录权限")
