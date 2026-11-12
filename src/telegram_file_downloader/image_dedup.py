"""Bound-folder image review and explicitly confirmed local-first cloud recycling."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from itertools import count, islice
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from .image_library import IMAGE_EXTENSIONS
from .image_similarity import ALGORITHM, features, group_images, similarity, verify_file
from .storage import RecycleBin, inside
from .xiaomi_cloud import XiaomiError, remote_id
from .xiaomi_local import folder_entries

LOGGER = logging.getLogger(__name__)
IMAGE_ERRORS = (OSError, ValueError, SyntaxError, UnidentifiedImageError,
                Image.DecompressionBombError, Image.DecompressionBombWarning)
FIELDS = "f.*,m.version AS scanned_version,m.group_id,m.removed"


class ImageDedup:
    def __init__(self, data_dir, store, cloud, local):
        self.store, self.cloud, self.local = store, cloud, local
        self.cache = data_dir / "dedup-thumbnails"
        self.cache.mkdir(parents=True, exist_ok=True)
        database = data_dir / "image-dedup.sqlite3"
        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY, root_id TEXT NOT NULL, path TEXT NOT NULL,
                version TEXT NOT NULL, algorithm TEXT NOT NULL, size INTEGER NOT NULL,
                width INTEGER, height INTEGER, digest TEXT, phash TEXT, error TEXT NOT NULL DEFAULT '',
                UNIQUE(root_id,path));
            CREATE TABLE IF NOT EXISTS jobs (owner TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members (
                run TEXT NOT NULL, file_id INTEGER NOT NULL, version TEXT NOT NULL,
                group_id INTEGER NOT NULL DEFAULT 0, removed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(run,file_id));
            CREATE INDEX IF NOT EXISTS dedup_group ON members(run,group_id,removed);
            CREATE TABLE IF NOT EXISTS scores (
                left_id INTEGER NOT NULL, right_id INTEGER NOT NULL,
                left_version TEXT NOT NULL, right_version TEXT NOT NULL,
                algorithm TEXT NOT NULL, value REAL NOT NULL,
                PRIMARY KEY(left_id,right_id));
        """)
        if os.name != "nt":
            database.chmod(0o600)
        for row in self.db.execute("SELECT owner,data FROM jobs").fetchall():
            job = json.loads(row["data"])
            if job["running"]:
                job.update(running=False, phase="interrupted", error="扫描被中断，请重新扫描；未变化的图片会复用缓存")
                self.save_job(job)
        for row in self.store.db.execute("SELECT key,value FROM kv WHERE key LIKE 'dedup_preview:%'").fetchall():
            preview = json.loads(row["value"])
            if preview["state"] == "matching":
                preview.update(state="failed", error="云端匹配被中断，请重新核对回收清单")
                self.store.put(row["key"], preview)
        self.task = self.preview_task = None
        self.cancelled = threading.Event()
        self.preview_cancelled = False
        self.score_slots = asyncio.Semaphore(1)
        self.feature_lock = asyncio.Lock()
        self.job = None

    def save_job(self, job):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["owner"], json.dumps(job)))

    def status(self, connection):
        owner = self.cloud.local_owner(connection)
        row = self.db.execute("SELECT data FROM jobs WHERE owner=?", (owner,)).fetchone()
        job = self.job if self.job and self.job["owner"] == owner else json.loads(row[0]) if row else None
        return {key: value for key, value in job.items() if key != "owner"} if job else None

    def current(self, connection, run, *, complete=True):
        job = self.status(connection)
        if not job or job["id"] != run:
            raise ValueError("扫描任务已变化，请刷新结果")
        if complete and job["phase"] != "completed":
            raise ValueError("请等待扫描完成")
        return job

    async def sources(self, connection):
        owner = self.cloud.local_owner(connection)
        albums = {item["id"]: item for item in await self.cloud.albums(connection)}
        roots = {}
        rows = self.local.db.execute("""SELECT roots.id,roots.path,bindings.album FROM bindings
            JOIN roots ON roots.id=bindings.root_id WHERE bindings.owner=? ORDER BY roots.path,bindings.album""", (owner,))
        for row in rows:
            root = roots.setdefault(row["id"], dict(id=row["id"], path=row["path"], albums=[], available=Path(row["path"]).is_dir()))
            root["albums"].append(dict(id=row["album"], name=albums.get(row["album"], {}).get("name", row["album"])))
        return list(roots.values())

    def check_bindings(self, owner, sources):
        for source in sources:
            for album in source["albums"]:
                bound = self.local.source(owner, album["id"])
                if not bound or bound["id"] != source["id"] or bound["path"] != source["path"]:
                    raise ValueError("相册绑定已变化，请重新扫描后选择图片")

    async def start(self, connection, root_ids, distance):
        if self.task and not self.task.done():
            raise ValueError("已有图片扫描正在进行，请等待完成或停止扫描")
        if self.preview_task and not self.preview_task.done():
            raise ValueError("请先完成或取消云端匹配")
        owner = self.cloud.local_owner(connection)
        known = {root["id"]: root for root in await self.sources(connection)}
        if any(root_id not in known for root_id in root_ids):
            raise ValueError("所选目录已解除绑定，请刷新目录")
        sources = [known[root_id] for root_id in dict.fromkeys(root_ids)]
        if not all(root["available"] for root in sources):
            raise ValueError("所选目录不可访问，请检查挂载和读取权限")
        # Recheck after the album request, before replacing any previous result.
        self.cloud.local_owner(connection)
        self.check_bindings(owner, sources)
        if self.task and not self.task.done():
            raise ValueError("已有图片扫描正在进行")
        if self.preview_task and not self.preview_task.done():
            raise ValueError("请先完成或取消云端匹配")
        previous = self.status(connection)
        self.job = dict(id=uuid4().hex, owner=owner, roots=sources, distance=distance, algorithm=ALGORITHM,
                        running=True, phase="scanning", done=0, total=0, errors=0, groups=0, matched=0,
                        error="", current="", created=time.time())
        with self.db:
            if previous:
                self.db.execute("DELETE FROM members WHERE run=?", (previous["id"],))
        self.save_job(self.job)
        self.cancelled = threading.Event()
        self.task = asyncio.create_task(self.scan(self.job), name="image-dedup-scan")
        return self.status(connection)

    def cancel(self, connection):
        owner = self.cloud.local_owner(connection)
        if self.job and self.job["owner"] == owner:
            self.cancelled.set()

    async def index_file(self, source, entry):
        _, size, relative, version = entry
        file = inside(Path(source["path"]), relative)
        async with self.feature_lock:
            row = self.db.execute("SELECT * FROM features WHERE root_id=? AND path=?", (source["id"], relative)).fetchone()
            cached = bool(row and row["version"] == version and row["algorithm"] == ALGORITHM
                          and not row["error"] and (self.cache / f"{row['id']}.jpg").is_file())
            if cached:
                verify_file(file, version)
                return dict(row)
            with self.db:
                self.db.execute("""INSERT INTO features(root_id,path,version,algorithm,size) VALUES (?,?,?,?,?)
                    ON CONFLICT(root_id,path) DO UPDATE SET version=excluded.version,algorithm=excluded.algorithm,
                    size=excluded.size,width=NULL,height=NULL,digest=NULL,phash=NULL,error=''""",
                    (source["id"], relative, version, ALGORITHM, size))
            row = self.db.execute("SELECT * FROM features WHERE root_id=? AND path=?", (source["id"], relative)).fetchone()
            try:
                result = await asyncio.to_thread(features, file, version, self.cache / f"{row['id']}.jpg")
            except IMAGE_ERRORS as exc:
                with self.db:
                    self.db.execute("UPDATE features SET error=? WHERE id=?", (str(exc), row["id"]))
            else:
                with self.db:
                    self.db.execute("UPDATE features SET width=?,height=?,digest=?,phash=? WHERE id=?",
                        (result["width"], result["height"], result["digest"], result["phash"], row["id"]))
            return dict(self.db.execute("SELECT * FROM features WHERE id=?", (row["id"],)).fetchone())

    async def scan(self, job):
        seen = set()
        try:
            for source in sorted(job["roots"], key=lambda source: len(source["path"]), reverse=True):
                root = Path(source["path"])
                iterator = folder_entries(root)
                try:
                    while not self.cancelled.is_set():
                        batch = await asyncio.to_thread(lambda: list(islice(iterator, 128)))
                        if not batch:
                            break
                        for entry in batch:
                            if entry is None or Path(entry[0]).suffix.lower() not in IMAGE_EXTENSIONS:
                                continue
                            name, size, relative, version = entry
                            file = inside(root, relative)
                            if file in seen:
                                continue
                            seen.add(file)
                            if self.cancelled.is_set():
                                break
                            job.update(total=job["total"] + 1, current=name)
                            row = await self.index_file(source, entry)
                            job["errors"] += bool(row["error"])
                            with self.db:
                                self.db.execute("INSERT INTO members(run,file_id,version) VALUES (?,?,?)", (job["id"], row["id"], version))
                            job["done"] += 1
                        self.save_job(job)
                finally:
                    iterator.close()
                if self.cancelled.is_set():
                    break
            if not self.cancelled.is_set():
                job.update(phase="grouping", current="")
                self.save_job(job)
                records = [dict(row) for row in self.db.execute("""SELECT f.id,f.digest,f.phash FROM features f
                    JOIN members m ON m.file_id=f.id WHERE m.run=? AND f.error=''""", (job["id"],))]
                groups = await asyncio.to_thread(group_images, records, job["distance"], self.cancelled)
                if groups is not None:
                    with self.db:
                        self.db.executemany("UPDATE members SET group_id=? WHERE run=? AND file_id=?",
                                            ((number, job["id"], item) for number, members in enumerate(groups, 1) for item in members))
                    job.update(groups=len(groups), matched=sum(map(len, groups)))
            job["phase"] = "cancelled" if self.cancelled.is_set() else "completed"
        except (OSError, ValueError, sqlite3.Error) as exc:
            LOGGER.exception("image dedup scan failed")
            job.update(phase="failed", error=str(exc))
        finally:
            job.update(running=False, current="")
            self.save_job(job)

    def record(self, connection, run, file_id):
        job = self.current(connection, run)
        row = self.db.execute(f"SELECT {FIELDS} FROM features f JOIN members m ON m.file_id=f.id WHERE m.run=? AND f.id=?",
                              (run, file_id)).fetchone()
        if not row or row["removed"] or row["version"] != row["scanned_version"]:
            raise ValueError("图片已移走或缓存已变化，请重新扫描")
        source = next(root for root in job["roots"] if root["id"] == row["root_id"])
        return dict(row), source

    @staticmethod
    def public(row):
        return dict({key: row[key] for key in ("id", "root_id", "path", "size", "width", "height", "error", "group_id")},
                    removed=bool(row["removed"]))

    def groups(self, connection, run, page):
        self.current(connection, run)
        condition = "m.run=? AND m.group_id>0 AND m.removed=0 AND m.version=f.version"
        grouped = f"SELECT m.group_id AS id,COUNT(*) AS count,COUNT(DISTINCT f.digest)=1 AS exact FROM members m JOIN features f ON f.id=m.file_id WHERE {condition} GROUP BY m.group_id HAVING COUNT(*)>1"
        total = self.db.execute(f"SELECT COUNT(*) FROM ({grouped})", (run,)).fetchone()[0]
        rows = self.db.execute(grouped + " ORDER BY m.group_id LIMIT 20 OFFSET ?", (run, (page - 1) * 20)).fetchall()
        items = []
        for row in rows:
            cover = self.db.execute("""SELECT f.id FROM features f JOIN members m ON m.file_id=f.id
                WHERE m.run=? AND m.group_id=? AND m.removed=0 AND m.version=f.version
                ORDER BY f.width*f.height DESC,f.size DESC,f.id LIMIT 3""", (run, row["id"])).fetchall()
            items.append(dict(row, exact=bool(row["exact"]), covers=[entry[0] for entry in cover]))
        return dict(items=items, total=total, page=page, page_size=20)

    def pictures(self, connection, run, group_id, page):
        self.current(connection, run)
        condition = "m.run=? AND m.group_id=? AND m.removed=0 AND m.version=f.version"
        total = self.db.execute(f"SELECT COUNT(*) FROM members m JOIN features f ON f.id=m.file_id WHERE {condition}", (run, group_id)).fetchone()[0]
        rows = self.db.execute(f"SELECT {FIELDS} FROM features f JOIN members m ON m.file_id=f.id WHERE {condition} ORDER BY f.width*f.height DESC,f.size DESC,f.id LIMIT 40 OFFSET ?",
                              (run, group_id, (page - 1) * 40)).fetchall()
        return dict(items=[self.public(row) for row in rows], total=total, page=page, page_size=40)

    def errors(self, connection, run, page):
        self.current(connection, run, complete=False)
        rows = self.db.execute("""SELECT f.path,f.error FROM features f JOIN members m ON m.file_id=f.id
            WHERE m.run=? AND f.error<>'' ORDER BY f.id LIMIT 40 OFFSET ?""", (run, (page - 1) * 40)).fetchall()
        return [dict(row) for row in rows]

    def file(self, connection, run, file_id):
        row, source = self.record(connection, run, file_id)
        self.check_bindings(self.cloud.local_owner(connection), [source])
        file = inside(Path(source["path"]), row["path"])
        verify_file(file, row["version"])
        return file

    async def scores(self, connection, run, reference, ids, disconnected):
        left, left_root = self.record(connection, run, reference)
        result = {}
        for file_id in dict.fromkeys(ids):
            if await disconnected():
                break
            try:
                right, right_root = self.record(connection, run, file_id)
                if right["group_id"] != left["group_id"]:
                    raise ValueError("请选择当前分组内的参考图")
                left_file = inside(Path(left_root["path"]), left["path"])
                right_file = inside(Path(right_root["path"]), right["path"])
                score = await self.pair_score(left_file, left, right_file, right)
                result[str(file_id)] = dict(ssim=score, distance=(int(left["phash"], 16) ^ int(right["phash"], 16)).bit_count(),
                                            exact=left["digest"] == right["digest"], error="")
            except IMAGE_ERRORS as exc:
                result[str(file_id)] = dict(error=str(exc))
        return result

    async def pair_score(self, left_file, left, right_file, right):
        async with self.score_slots:
            verify_file(left_file, left["version"])
            verify_file(right_file, right["version"])
            cached = self.db.execute("""SELECT value FROM scores WHERE left_id=? AND right_id=?
                AND left_version=? AND right_version=? AND algorithm=?""",
                (left["id"], right["id"], left["version"], right["version"], ALGORITHM)).fetchone()
            if cached:
                return cached[0]
            score = await asyncio.to_thread(similarity, left_file, left, right_file, right)
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?)",
                    (left["id"], right["id"], left["version"], right["version"], ALGORITHM, score))
            return score

    def preview(self, connection):
        owner = self.cloud.local_owner(connection)
        return self.store.get("dedup_preview:" + owner)

    async def prepare(self, connection, run, ids):
        if self.preview_task and not self.preview_task.done():
            raise ValueError("已有云端匹配正在进行")
        owner = self.cloud.local_owner(connection)
        job = self.current(connection, run)
        self.check_bindings(owner, job["roots"])
        with self.store.db:
            self.store.db.execute("""DELETE FROM kv WHERE key LIKE 'dedup_recycle:%' AND
                ((json_extract(value,'$.done')=1 AND json_extract(value,'$.created')<?) OR
                 (json_extract(value,'$.attempted')=0 AND json_extract(value,'$.created')<?))""",
                (time.time() - 15 * 86400, time.time() - 86400))
            # Receipts are only needed while a plan from their batch still exists.
            self.store.db.execute("""DELETE FROM kv WHERE key LIKE 'dedup_cloud:%' AND substr(key,13,32) NOT IN
                (SELECT json_extract(value,'$.batch') FROM kv WHERE key LIKE 'dedup_recycle:%')""")
        plans = []
        batch_id = uuid4().hex
        for file_id in dict.fromkeys(ids):
            row, root = self.record(connection, run, file_id)
            if not row["group_id"]:
                raise ValueError("只能回收分组中明确勾选的图片")
            file = self.file(connection, run, file_id)
            sources = [source for source in job["roots"] if file.is_relative_to(Path(source["path"]))]
            plans.append(dict(token=uuid4().hex, batch=batch_id, owner=owner, run=run, file_id=file_id, name=file.name,
                              path=row["path"], size=row["size"], version=row["version"], root=root,
                              sources=sources, cloud=[], local_done=False, attempted=False, done=False,
                              error="", created=time.time()))
        preview = dict(state="matching", items=plans, pages=0, album="", error="")
        self.store.put("dedup_preview:" + owner, preview)
        self.preview_cancelled = False
        self.preview_task = asyncio.create_task(self.match_cloud(connection, owner, preview), name="image-dedup-cloud-match")
        return preview

    async def match_cloud(self, connection, owner, preview):
        try:
            albums = {}
            for plan in preview["items"]:
                for source in plan["sources"]:
                    for album in source["albums"]:
                        albums.setdefault(album["id"], dict(name=album["name"], plans=[]))["plans"].append(plan)
            for album_id, album in albums.items():
                preview["album"] = album["name"]
                matches = {}
                for plan in album["plans"]:
                    matches.setdefault((plan["name"], plan["size"]), []).append(plan)
                markers = set()
                for page in count():
                    if self.preview_cancelled:
                        preview["state"] = "cancelled"
                        return
                    entries, last = await self.cloud.media_page(connection, album_id, page, 200)
                    if not entries and not last:
                        raise XiaomiError("小米云未返回完整相册列表，请重新核对")
                    marker = remote_id(entries[-1].get("id")) if entries else ""
                    if marker and marker in markers:
                        raise XiaomiError("小米云返回重复的相册页，请重新核对")
                    if marker:
                        markers.add(marker)
                    for entry in entries:
                        if (entry.get("type") != "image" or not isinstance(entry.get("fileName"), str)
                                or (entry.get("groupId") is not None and str(entry["groupId"]) != album_id)):
                            continue
                        for plan in matches.get((entry["fileName"], entry.get("size")), []):
                            media_id = remote_id(entry.get("id"))
                            if not any(item["id"] == media_id for item in plan["cloud"]):
                                plan["cloud"].append(dict(id=media_id, album=album_id, album_name=album["name"], done=False, error=""))
                    preview["pages"] += 1
                    self.store.put("dedup_preview:" + owner, preview)
                    if last:
                        break
            if self.preview_cancelled:
                preview["state"] = "cancelled"
                return
            for plan in preview["items"]:
                self.store.put("dedup_recycle:" + plan["token"], plan)
            preview["state"] = "ready"
        except (XiaomiError, OSError, ValueError) as exc:
            preview.update(state="failed", error=str(exc))
        finally:
            self.store.put("dedup_preview:" + owner, preview)

    def cancel_preview(self, connection):
        preview = self.preview(connection)
        if preview and preview["state"] == "matching":
            self.preview_cancelled = True

    def pending(self, connection):
        owner = self.cloud.local_owner(connection)
        rows = self.store.db.execute("""SELECT value FROM kv WHERE key LIKE 'dedup_recycle:%'
            AND json_extract(value,'$.owner')=? AND json_extract(value,'$.attempted')=1
            AND json_extract(value,'$.done')=0""", (owner,))
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def recycle_local(plan):
        root = Path(plan["root"]["path"])
        if not root.is_dir():
            raise ValueError("本地目录不可访问，请检查挂载")
        with RecycleBin(root) as recycle:
            record = recycle.db.execute("SELECT * FROM items WHERE id=?", (plan["token"],)).fetchone()
            if record:
                if record["original"] != plan["path"]:
                    raise ValueError("回收记录与图片不一致")
                if record["state"] == "restored":
                    raise ValueError("本地图片已还原，已停止旧的云端清理；需要删除时请重新扫描")
                if record["state"] in {"trashed", "purged"}:
                    return
                if record["state"] != "pending":
                    raise ValueError("本地回收站正在处理此图片，请稍后再试")
            elif plan["local_done"]:
                raise ValueError("本地回收记录已丢失，已停止云端清理")
            file = inside(root, plan["path"])
            verify_file(file, plan["version"])
            recycle.move(file, plan["token"], "image_dedup")

    async def execute(self, connection, token):
        owner = self.cloud.local_owner(connection)
        plan = self.store.get("dedup_recycle:" + token)
        if not plan or plan["owner"] != owner:
            raise ValueError("回收清单不存在，请重新核对")
        if plan["done"]:
            return plan
        plan["attempted"] = True
        self.store.put("dedup_recycle:" + token, plan)
        try:
            if not plan["local_done"]:
                if plan["created"] < time.time() - 86400:
                    raise ValueError("回收清单已过期，请重新核对")
                self.check_bindings(owner, plan["sources"])
            await asyncio.to_thread(self.recycle_local, plan)
            plan.update(local_done=True, error="")
            self.store.put("dedup_recycle:" + token, plan)
            with self.db:
                self.db.execute("UPDATE members SET removed=1 WHERE run=? AND file_id=?", (plan["run"], plan["file_id"]))
            file = Path(plan["root"]["path"]) / plan["path"]
            with self.local.db:
                for source in plan["sources"]:
                    self.local.db.execute("DELETE FROM files WHERE root_id=? AND path=?",
                                          (source["id"], file.relative_to(source["path"]).as_posix()))
            # An inventory batch already in flight may still publish the old file list.
            self.local.requested.update(source["id"] for source in plan["sources"])
            self.local.wake.set()
            for item in plan["cloud"]:
                if item["done"]:
                    continue
                try:
                    receipt = "dedup_cloud:" + plan["batch"] + ":" + item["id"]
                    if not self.store.get(receipt):
                        await self.cloud.recycle(connection, item["id"])
                        self.store.put(receipt, True)
                except (XiaomiError, OSError) as exc:
                    item["error"] = str(exc)
                else:
                    item.update(done=True, error="")
                self.store.put("dedup_recycle:" + token, plan)
            plan["done"] = all(item["done"] for item in plan["cloud"])
            if not plan["done"]:
                plan["error"] = "本地已回收，部分云端图片未完成；可手动重试"
        except (OSError, ValueError, sqlite3.Error) as exc:
            plan["error"] = str(exc)
        self.store.put("dedup_recycle:" + token, plan)
        self.update_preview(plan)
        LOGGER.info("image dedup recycle token=%s local_done=%s cloud_done=%s cloud_total=%s", token,
                    plan["local_done"], sum(item["done"] for item in plan["cloud"]), len(plan["cloud"]))
        return plan

    def update_preview(self, plan):
        key = "dedup_preview:" + plan["owner"]
        preview = self.store.get(key)
        if preview and preview["state"] in {"ready", "completed"}:
            for index, item in enumerate(preview["items"]):
                if item["token"] == plan["token"]:
                    preview["items"][index] = plan
            if all(item["done"] for item in preview["items"]):
                preview["state"] = "completed"
            self.store.put(key, preview)

    def dismiss(self, connection, token):
        owner = self.cloud.local_owner(connection)
        plan = self.store.get("dedup_recycle:" + token)
        if not plan or plan["owner"] != owner:
            raise ValueError("回收清单不存在")
        plan.update(done=True, error="已放弃未完成操作")
        self.store.put("dedup_recycle:" + token, plan)
        self.update_preview(plan)

    async def close(self):
        self.cancelled.set()
        self.preview_cancelled = True
        for task in (self.task, self.preview_task):
            if task:
                await task
        self.db.close()
