from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from pathlib import Path

from telethon import errors, types, utils, functions

from .archives import (ARCHIVE_EXTENSIONS, ExtractionError, VolumesPending, extract_archive,
                       multipart, volume_info, resource_name)
from .console_store import now
from .downloader import DownloadQueue
from .files import message_filename
from .organizer import make_plan, execute_plan, upgrade_cleanup_plan
from .transfers import TransferThrottle

LOGGER = logging.getLogger(__name__)
DOWNLOAD_STATES = {"queued", "interrupted"}
FINISHED = {"completed", "extracted", "organized", "manual_extracted"}


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
        candidates = []
        for document in [message.document, *(getattr(message.media, "alt_documents", None) or [])]:
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
    if settings["archives"] and (Path(name).suffix.lower() in ARCHIVE_EXTENSIONS or multipart(name)):
        return message, "archive", ""
    return None


def size_text(value):
    value = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


class ConsoleProcessor:
    """Persist intake before advancing Telegram history; execute independently."""
    def __init__(self, client, directory, history, recorder, store, settings, operation_lock, images_changed, check_images=None):
        self.client, self.directory, self.history = client, directory, history
        self.recorder, self.store, self.settings = recorder, store, settings
        self.operation_lock = operation_lock
        self.images_changed = images_changed
        self.check_images = check_images
        self.receipt_disabled_until = 0.0
        self.receipt_lock = asyncio.Lock()
        self.running = {}
        self.post_tasks = {}
        self.ready = False
        self.closed = False
        self.dispatcher = None
        self.pending_groups = set()
        self.final_receipts = set()
        self.receipt_sender = None
        account = history.scope.split(":", 1)[0] if history else ""
        key = f"transfer_backoff:{account}"
        self.throttle = TransferThrottle(settings["download_parallelism"] * settings["parallel_files"],
            store.get(key), lambda value: store.put(key, value))
        self.server_limits = {}

    async def start(self):
        # This request uses the same account, proxy and persistent flood deadline as downloads.
        while True:
            try:
                async with self.throttle.request():
                    response = await asyncio.wait_for(self.client(functions.help.GetAppConfigRequest(hash=0)), 45)
                break
            except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                continue
        config = getattr(response, "config", None)
        values = {item.key: item.value.value for item in config.value if isinstance(item.value, types.JsonNumber)} if isinstance(config, types.JsonObject) else {}
        for category in ("small", "large"):
            value = values.get(f"{category}_queue_max_active_operations_count")
            if value is not None and value >= 1 and value == int(value):
                self.server_limits[category] = int(value)
            else:
                LOGGER.warning("Telegram did not provide the %s download queue limit; configured file limit remains %s",
                               category, self.settings["parallel_files"])
        LOGGER.info("Telegram parallel file limits per DC: %s; per-file parts=%s", self.server_limits, self.settings["download_parallelism"])
        for task in self.store.tasks(self.history.scope, {"queued", "interrupted", "extraction_failed", "downloaded", "waiting_volumes"}):
            if not task.get("group_id"):
                stage = "extract" if task["path"] and task["kind"] == "archive" and task["status"] in {"interrupted", "extraction_failed", "downloaded"} else "download"
                self.store.update_task(task["id"], group_id=f"file:{task['scope']}:{task['message_id']}", stage=stage)
        self.dispatcher = asyncio.create_task(self._dispatch(), name="download-scheduler")
        self.receipt_sender = asyncio.create_task(self._send_final_receipts(), name="receipt-outbox")

    def begin_scan(self):
        self.ready = False

    def scan_complete(self):
        self.ready = True
        for task in self.store.tasks(self.history.scope, {"downloaded", "waiting_volumes", "interrupted"}):
            if task.get("manual_extract_only"):
                continue
            if task["status"] in {"downloaded", "waiting_volumes"} or (
                    task["status"] == "interrupted" and task.get("stage") != "download"):
                self.pending_groups.add(task.get("group_id") or str(task["id"]))

    async def close(self):
        self.closed = True
        tasks = [self.dispatcher, self.receipt_sender, *self.running.values(), *self.post_tasks.values()]
        for task in tasks:
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task), return_exceptions=True)

    def _group_id(self, message, volume):
        if not volume:
            return f"file:{self.history.scope}:{message.id}"
        forwarded = getattr(message, "fwd_from", None)
        source = getattr(forwarded, "from_id", None)
        origin = str(utils.get_peer_id(source)) if source else "unknown"
        album = getattr(message, "grouped_id", None)
        signature = f"{volume['base'].casefold()}:{volume['scheme']}:{origin}"
        task = self.store.volume_candidate(self.history.scope, signature, str(album or ""))
        if task:
            members = self.store.group(task["group_id"])
            if not any(item.get("volume", {}).get("index") == volume["index"] for item in members if item.get("volume")):
                return task["group_id"]
        return f"volumes:{uuid.uuid4().hex}"

    async def process(self, message):
        self.recorder.append_from_text(message.raw_text)
        selection = select_media(message, self.settings)
        if not selection:
            return True
        selected, kind, quality = selection
        existing = self.store.find(self.history.scope, message.id)
        if existing:
            return True
        task = self.store.create_task(self.history.scope, message.id, message_filename(selected), kind, selected.file.size, quality)
        volume = volume_info(task["filename"]) if kind == "archive" else None
        group_id = self._group_id(message, volume)
        forwarded = getattr(message, "fwd_from", None)
        source = getattr(forwarded, "from_id", None)
        origin = str(utils.get_peer_id(source)) if source else "unknown"
        signature = f"{volume['base'].casefold()}:{volume['scheme']}:{origin}" if volume else ""
        self.store.update_task(task["id"], group_id=group_id, volume=volume, volume_signature=signature,
                               album_id=str(getattr(message, "grouped_id", None) or ""),
                               dc_id=getattr(selected.document or selected.photo, "dc_id", None))
        if volume:
            self.store.refresh_archive_sets(self.history.scope, signature)
        LOGGER.info("task=%s received message=%s group=%s name=%s size=%s", task["id"], message.id, group_id, task["filename"], task["size"])
        return True

    async def _dispatch(self):
        while not self.closed:
            if self.ready:
                if not self.store.get("queue_paused", False):
                    for task in self.store.tasks(self.history.scope, DOWNLOAD_STATES):
                        if len(self.running) >= self.settings["parallel_files"]:
                            break
                        if task["id"] in self.running or task["status"] not in DOWNLOAD_STATES or task.get("stage", "download") != "download":
                            continue
                        if not self._file_slot_available(task):
                            continue
                        self.running[task["id"]] = asyncio.create_task(self._run_download(task), name=f"download-{task['id']}")
                for group in list(self.pending_groups):
                    if group not in self.post_tasks:
                        self.pending_groups.discard(group)
                        self.post_tasks[group] = asyncio.create_task(self._postprocess(group), name="resource-workflow")
            await asyncio.sleep(.5)

    def _file_slot_available(self, task):
        category = "small" if task["size"] < 20 * 1024 * 1024 else "large"
        limit = self.server_limits.get(category, self.settings["parallel_files"])
        active = [self.store.task(task_id) for task_id in self.running]
        count = sum(1 for item in active if ("small" if item["size"] < 20 * 1024 * 1024 else "large") == category
                    and (not task.get("dc_id") or not item.get("dc_id") or task["dc_id"] == item["dc_id"]))
        return count < limit

    async def _send_final_receipts(self):
        while not self.closed:
            if self.final_receipts and time.monotonic() >= self.receipt_disabled_until:
                task_id = min(self.final_receipts)
                self.final_receipts.discard(task_id)
                await self.receipt(self.store.task(task_id))
            await asyncio.sleep(1)

    async def receipt(self, task):
        if not self.client or not self.settings["receipts"] or time.monotonic() < self.receipt_disabled_until:
            return
        async with self.receipt_lock:
            if time.monotonic() < self.receipt_disabled_until:
                return
            task = self.store.task(task["id"])
            labels = {"queued": "等待下载", "downloading": "下载中", "waiting": "Telegram 限流等待",
                      "paused": "已暂停", "retrying": "连接恢复中", "failed": "下载失败，可在页面重试",
                      "downloaded": "下载完成", "waiting_volumes": "等待分卷", "extracting": "正在解压",
                      "organizing": "正在整理文件", "organized": "本地工作流完成", "extracted": "解压完成",
                      "extraction_failed": "解压未完成", "processing_failed": "文件整理未完成", "completed": "下载完成",
                      "manual_extracted": "手动解压"}
            text = f"{labels.get(task['status'], task['status'])}\n{task['filename']}"
            if task["status"] == "downloading":
                percent = task["downloaded"] * 100 / task["size"] if task["size"] else 0
                eta = f"{int(task['eta'])} 秒" if task["eta"] is not None else "计算中"
                text += f"\n{percent:.1f}% · {size_text(task['speed'])}/s · 剩余 {eta}"
            elif task["status"] == "waiting":
                text += f"\n约 {max(0, int((task.get('wait_until') or 0) - time.time()))} 秒后恢复"
            else:
                text += f"\n{size_text(task['downloaded'])} · 平均 {size_text(task['average_speed'])}/s"
            if task["archive_deleted"]:
                text += "\n原压缩包已删除"
            if task.get("recycled_psds") or task.get("recycled_txts"):
                text += f"\n已移入回收站：PSD {task.get('recycled_psds', 0)} 个、TXT {task.get('recycled_txts', 0)} 个"
            if task["error"]:
                text += "\n" + task["error"]
            chat = int(task["scope"].split(":", 1)[1])
            try:
                if task["receipt_id"]:
                    await asyncio.wait_for(self.client.edit_message(chat, task["receipt_id"], text, parse_mode=None), 10)
                else:
                    sent = await asyncio.wait_for(self.client.send_message(chat, text, reply_to=task["message_id"], parse_mode=None), 10)
                    self.store.update_task(task["id"], receipt_id=sent.id)
                if self.store.task(task["id"])["warning"].startswith("群回执"):
                    self.store.update_task(task["id"], warning="")
            except errors.MessageNotModifiedError:
                pass
            except errors.FloodWaitError as exc:
                self.receipt_disabled_until = time.monotonic() + exc.seconds
                self.final_receipts.add(task["id"])
            except (errors.RPCError, OSError, EOFError):
                LOGGER.warning("task=%s receipt unavailable", task["id"], exc_info=True)
                self.store.update_task(task["id"], warning="群回执发送失败；下载继续，请查看页面")

    async def _run_download(self, task):
        task_id = task["id"]
        reporter = None
        start = time.monotonic()
        prior_elapsed = task.get("elapsed", 0)
        last_bytes = task["downloaded"]
        last_time = start
        last_log = start
        file_throttle = TransferThrottle(self.settings["download_parallelism"], parent=self.throttle)
        def effective_parallelism():
            return min(file_throttle.parallelism, self.throttle.parallelism)
        try:
            chat = int(task["scope"].split(":", 1)[1])
            async def initial_wait(until, reason, parallelism):
                self.store.update_task(task_id, status="waiting", wait_until=until, wait_reason=reason,
                                       parallelism=effective_parallelism(), speed=0, eta=None)
            while True:
                try:
                    async with self.throttle.request(initial_wait):
                        message = await asyncio.wait_for(self.client.get_messages(chat, ids=task["message_id"]), 45)
                    break
                except (errors.FloodWaitError, errors.FloodPremiumWaitError):
                    continue
            if not message:
                raise ValueError("原消息已删除或当前账号无法访问")
            selection = select_media(message, {**self.settings, "videos": True, "photos": True, "archives": True})
            if not selection:
                raise ValueError("原消息已没有可下载的附件")
            selected = selection[0]
            self.store.update_task(task_id, status="downloading", started_at=task["started_at"] or now(),
                error="", completed_at=None, wait_until=None, wait_reason="", parallelism=effective_parallelism(),
                dc_id=getattr(selected.document or selected.photo, "dc_id", None),
                steps={"receive": "done", "download": "active"})
            if self.settings["mark_read"]:
                try:
                    await asyncio.wait_for(self.client.send_read_acknowledge(chat, max_id=message.id), 10)
                except (errors.RPCError, OSError):
                    LOGGER.warning("task=%s mark read unavailable", task_id)

            async def progress(current, total):
                nonlocal last_bytes, last_time, last_log
                moment = time.monotonic()
                if moment - last_time < 1 and current != total:
                    return
                speed = max(0, current - last_bytes) / max(moment - last_time, .001)
                wait_until = max(self.throttle.until, file_throttle.until)
                waiting = wait_until > time.time()
                elapsed = prior_elapsed + moment - start
                self.store.update_task(task_id, downloaded=current, size=total or 0, speed=0 if waiting else speed,
                    eta=(total - current) / speed if not waiting and speed and total else None,
                    elapsed=elapsed, average_speed=current / max(elapsed, .001), last_progress_at=now(),
                    status="waiting" if waiting else "downloading", parallelism=effective_parallelism(),
                    wait_until=wait_until if waiting else None)
                if moment - last_log >= 30 or current == total:
                    LOGGER.info("task=%s progress=%s/%s speed=%.0f elapsed=%.1f", task_id, current, total, speed, elapsed)
                    last_log = moment
                last_bytes, last_time = current, moment

            async def waiting(until, reason, parallelism):
                self.store.update_task(task_id, status="waiting", wait_until=until, wait_reason=reason,
                                       parallelism=effective_parallelism(), speed=0, eta=None)

            def retry(attempt, reason):
                self.store.update_task(task_id, status="retrying", attempts=attempt, speed=0,
                                       warning=f"下载请求失败（{reason}），保留分片并重试 {attempt}/3")

            async def report():
                while True:
                    await self.receipt(self.store.task(task_id))
                    await asyncio.sleep(10)

            reporter = asyncio.create_task(report(), name="progress-receipt")
            directory = self.directory
            if task.get("volume") and self.settings["extract"]:
                directory = self.directory / ".tg-work" / task["group_id"].split(":")[-1]
            queue = DownloadQueue(self.client, directory, lambda error: None, history=self.history,
                progress=progress, parallelism=self.settings["download_parallelism"], throttle=file_throttle,
                on_wait=waiting, on_notice=lambda text: self.store.update_task(task_id, warning=text), on_retry=retry)
            path = await queue.download(selected)
            if not path:
                raise RuntimeError("三次下载尝试失败，已保留分片；请检查日志后重试")
            elapsed = prior_elapsed + time.monotonic() - start
            extract = task["kind"] == "archive" and self.settings["extract"]
            self.store.update_task(task_id, status="downloaded" if extract else "completed", stage="extract" if extract else "complete",
                path=str(path), downloaded=path.stat().st_size, elapsed=elapsed,
                average_speed=path.stat().st_size / max(elapsed, .001), speed=0, eta=0, completed_at=now(),
                wait_until=None, steps={"receive": "done", "download": "done"})
            if self.store.task(task_id)["warning"].startswith("下载请求失败"):
                self.store.update_task(task_id, warning="")
            self.pending_groups.add(task.get("group_id") or str(task_id))
            if task["kind"] == "photo":
                self.images_changed()
                if self.check_images:
                    self.check_images([task_id], [Path(path).name])
            LOGGER.info("task=%s download complete path=%s", task_id, path)
        except asyncio.CancelledError:
            current = self.store.task(task_id)
            if current["status"] not in {"paused", "queued"}:
                self.store.update_task(task_id, status="interrupted", speed=0, eta=None)
            LOGGER.info("task=%s stopped; partial checkpoint retained", task_id)
            raise
        except Exception as exc:
            LOGGER.exception("task=%s download failed", task_id)
            self.store.update_task(task_id, status="failed", error=str(exc), completed_at=now(), speed=0, eta=None,
                                   steps={"receive": "done", "download": "failed"})
        finally:
            if reporter:
                reporter.cancel()
                await asyncio.gather(reporter, return_exceptions=True)
            self.final_receipts.add(task_id)
            self.running.pop(task_id, None)

    async def _postprocess(self, group):
        try:
            async with self.operation_lock:
                await self.unpack_group(group)
        except asyncio.CancelledError:
            for task in self.store.group(group):
                if task["status"] in {"extracting", "organizing"}:
                    self.store.update_task(task["id"], status="interrupted", speed=0)
            raise
        except Exception as exc:
            LOGGER.exception("group=%s postprocess failed", group)
            for task in self.store.group(group):
                self.store.update_task(task["id"], status="processing_failed", error=str(exc), speed=0)
        finally:
            self.post_tasks.pop(group, None)

    async def unpack(self, task_id):
        task = self.store.task(task_id)
        group = task.get("group_id") or str(task_id)
        if not task.get("group_id"):
            self.store.update_task(task_id, group_id=group)
        self.pending_groups.add(group)

    async def unpack_group(self, group):
        members = self.store.group(group)
        if any(task.get("manual_extract_only") or task["status"] == "manual_extracted" for task in members):
            return
        saved_plan = self.store.get(f"organize:{group}")
        allowed = {"downloaded", "waiting_volumes", "interrupted", "extraction_failed", "processing_failed"}
        if saved_plan:
            allowed |= FINISHED
        if not members or all(t["status"] in FINISHED for t in members) or any(t["status"] not in allowed for t in members):
            return
        if not saved_plan and any(not t["path"] or not Path(t["path"]).is_file() for t in members):
            return
        signature = [[t["id"], t["downloaded"]] for t in members]
        if all(t["status"] == "waiting_volumes" for t in members) and self.store.get(f"volume_attempt:{group}") == signature:
            return
        self.store.put(f"volume_attempt:{group}", signature)
        split = len(members) > 1 or any((t.get("volume") or {}).get("split") for t in members)
        members.sort(key=lambda t: (t.get("volume") or {}).get("index", 0))
        leader = members[0]
        if split:
            indices = {(t.get("volume") or {}).get("index", 0) for t in members}
            scheme = (leader.get("volume") or {}).get("scheme")
            required_start = 0 if scheme == "zip_old" else 1
            missing = sorted(set(range(required_start, max(indices) + 1)) - indices)
            if missing:
                for task in members:
                    self.store.update_task(task["id"], status="waiting_volumes", error="等待分卷编号：" + ", ".join(map(str, missing)), stage="volumes",
                                           steps={"receive": "done", "download": "done", "volumes": "waiting"})
                    self.final_receipts.add(task["id"])
                return
            if scheme == "zip_old":
                leader = next((t for t in members if t["filename"].lower().endswith(".zip")), leader)
        task_id = leader["id"]
        steps = {"receive": "done", "download": "done", "volumes": "done" if split else "skipped"}
        for task in members:
            self.store.update_task(task["id"], status="extracting", stage="extract", error="", steps={**steps, "extract": "active"})
        LOGGER.info("group=%s extraction starting volumes=%s", group, [t["filename"] for t in members])
        try:
            # Output intent survives interruption of the later move/delete workflow.
            output = Path(leader["output"]) if leader["output"] else None
            plan_key = f"organize:{group}"
            plan = self.store.get_plan(plan_key)
            if not plan and (not output or not output.is_dir()):
                output = await extract_archive(Path(leader["path"]), self.settings["archive_passwords"], leader["filename"], allow_volumes=split or bool(leader.get("volume")))
            for task in members:
                self.store.update_task(task["id"], output=str(output), status="organizing", stage="organize",
                                       steps={**steps, "extract": "done", "organize": "active"})
            if not plan:
                plan = await asyncio.to_thread(make_plan, self.directory, output, resource_name(leader["filename"]), self.settings["delete_psd"], False)
                if not self.settings["flatten"]:
                    plan["moves"] = []
                plan["flatten"] = self.settings["flatten"]
                self.store.put_plan(plan_key, plan)
            if plan.get("cleanup") != "psd_txt":
                plan = await asyncio.to_thread(upgrade_cleanup_plan, self.directory, plan, resource_name(leader["filename"]), self.settings["delete_psd"])
                self.store.put_plan(plan_key, plan)
            if plan.get("legacy_deleted_pdfs"):
                for member in members:
                    self.store.update_task(member["id"], deleted_pdfs=plan["legacy_deleted_pdfs"],
                        warning="旧版曾删除此资源的 PDF；本次已停止 PDF 清理，已删除文件需从原包恢复")
            if not self.settings["delete_psd"]:
                plan["cleanup_files"] = plan["deleted_files"][:]
                self.store.put_plan(plan_key, plan)
            def phase(value):
                current_steps = {**steps, "extract": "done", "organize": "done" if value == "cleanup" else "active"}
                if value == "cleanup":
                    current_steps["cleanup"] = "active" if self.settings["delete_psd"] else "skipped"
                for member in members:
                    self.store.update_task(member["id"], stage=value, steps=current_steps)
            result = await execute_plan(self.directory, plan, lambda value: self.store.put_plan(plan_key, value), phase,
                                        lambda value: self.store.put(f"progress:{plan_key}", value))
            if result["moved"]:
                self.images_changed()
            flattened = plan.get("flatten", self.settings["flatten"])
            final = "organized" if flattened else "extracted"
            steps.update(extract="done", organize="done" if flattened else "skipped",
                         cleanup="done" if self.settings["delete_psd"] else "skipped", cloud="pending")
            if self.settings["delete_archive"]:
                for task in members:
                    Path(task["path"]).unlink(missing_ok=True)
                    self.store.update_task(task["id"], archive_deleted=True)
            for task in members:
                self.store.update_task(task["id"], status=final, stage="complete", error="", completed_at=now(),
                    output=str(self.directory if flattened else output), steps=steps,
                    result_files=result["moved"], deleted_psds=result["deleted_psds"], deleted_txts=result["deleted_txts"],
                    recycled_psds=result["recycled_psds"], recycled_txts=result["recycled_txts"])
                self.final_receipts.add(task["id"])
            if self.check_images:
                self.check_images([task["id"] for task in members],
                    [Path(move["target"]).name for move in plan["moves"] if move["done"]] if flattened else [])
            LOGGER.info("group=%s workflow complete moved=%s recycled_psds=%s recycled_txts=%s", group, result["moved"], result["recycled_psds"], result["recycled_txts"])
            self.store.refresh_archive_sets(leader["scope"], leader.get("volume_signature") or None)
        except (ExtractionError, OSError, ValueError) as exc:
            failure_stage = self.store.task(task_id).get("stage", "extract")
            status = "waiting_volumes" if isinstance(exc, VolumesPending) else (
                "processing_failed" if failure_stage in {"organize", "cleanup"} else "extraction_failed")
            failure_steps = dict(self.store.task(task_id).get("steps") or steps)
            if status == "waiting_volumes":
                failure_stage = "volumes"
                failure_steps.update(volumes="waiting", extract="idle")
            else:
                failure_steps[failure_stage] = "failed"
            LOGGER.warning("group=%s workflow stopped status=%s reason=%s", group, status, exc, exc_info=True)
            for task in members:
                self.store.update_task(task["id"], status=status, error=str(exc), completed_at=now(),
                    stage=failure_stage, steps=failure_steps)
                self.final_receipts.add(task["id"])

    async def control(self, task_id, action):
        task = self.store.task(task_id)
        if not task or task["scope"] != self.history.scope:
            raise ValueError("任务不属于当前登录账号和收集群")
        if action == "pause":
            if task.get("stage", "download") != "download" or task["status"] not in {"queued", "interrupted", "downloading", "waiting", "retrying", "failed"}:
                raise ValueError("只有下载阶段可以暂停；文件整理执行后会完成当前步骤")
            self.store.update_task(task_id, status="paused", speed=0, eta=None)
            worker = self.running.get(task_id)
            if worker:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
        elif action in {"resume", "retry"}:
            if task_id in self.running:
                raise ValueError("任务仍在运行")
            if task["status"] in FINISHED:
                raise ValueError("任务已完成")
            if task["status"] in {"extracting", "organizing", "downloaded"} or task.get("group_id") in self.post_tasks:
                raise ValueError("任务仍在处理，请等待当前步骤结束")
            if task.get("stage", "download") != "download" and task["path"]:
                self.store.put(f"volume_attempt:{task.get('group_id') or str(task_id)}", None)
                members = self.store.group(task.get("group_id") or str(task_id))
                for item in members or [task]:
                    self.store.update_task(item["id"], status="downloaded", error="")
                await self.unpack(task_id)
            else:
                self.store.update_task(task_id, status="queued", stage="download", error="", warning="")
        LOGGER.info("task=%s action=%s", task_id, action)

    async def pause_queue(self, paused):
        self.store.put("queue_paused", paused)
        if paused:
            workers = [(task_id, worker) for task_id, worker in self.running.items()
                       if self.store.task(task_id).get("stage", "download") == "download"]
            for task_id, worker in workers:
                self.store.update_task(task_id, status="queued", speed=0, eta=None)
                worker.cancel()
            await asyncio.gather(*(worker for _, worker in workers), return_exceptions=True)
        LOGGER.info("download queue paused=%s", paused)
