"""Background, read-only comparison of incoming images with bound backup folders."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

from .image_dedup import IMAGE_ERRORS
from .image_library import IMAGE_EXTENSIONS
from .image_similarity import ALGORITHM, PerceptualIndex, verify_file
from .storage import file_version, inside

LOGGER = logging.getLogger(__name__)
PROFILE = "saved-compressed-v1:" + ALGORITHM


class SavedImageCheck:
    def __init__(self, library, dedup, local, cloud, store, busy):
        self.library, self.dedup, self.local = library, dedup, local
        self.cloud, self.store, self.busy = cloud, store, busy
        self.state = dict(running=False, phase="waiting", done=0, total=0, baselines=0, errors=0,
                          error="", current="", last_check=None)
        self.wake = asyncio.Event()
        self.task = None
        self.closing = False
        self.generations = None
        self.index = PerceptualIndex()
        self.by_hash = {}
        self.baseline_errors = 0
        self.retry_errors = False

    def sources(self):
        account = self.cloud.account()
        if not account:
            return "", []
        owner = self.cloud.local_owner(account["connection"])
        roots = {}
        for row in self.local.db.execute("""SELECT roots.*,bindings.album FROM roots JOIN bindings
                ON bindings.root_id=roots.id WHERE bindings.owner=? ORDER BY roots.id,bindings.album""", (owner,)):
            root = roots.setdefault(row["id"], {**dict(row), "albums": []})
            root["albums"].append(row["album"])
        return owner, list(roots.values())

    @staticmethod
    def signature(owner, roots):
        return (owner, tuple((root["id"], root["generation"], tuple(root["albums"])) for root in roots))

    @staticmethod
    def scope_key(owner, roots):
        return json.dumps([PROFILE, owner, [(root["id"], root["path"], root["albums"]) for root in roots]])

    def ready(self, roots):
        return all(root["generation"] and not root["error"] and root["id"] not in self.local.progress
                   and not self.local.scan_errors.get(root["id"])
                   and root["id"] not in self.local.requested for root in roots)

    def scope(self):
        owner, roots = self.sources()
        if not roots or not self.ready(roots) or self.generations != self.signature(owner, roots):
            return ""
        return self.scope_key(owner, roots)

    def request(self, *, refresh=True, force=False):
        self.retry_errors = True
        if force:
            with self.library.db:
                self.library.db.execute("UPDATE images SET saved_scope='' WHERE active=1")
        if refresh:
            _, roots = self.sources()
            self.local.requested.update(root["id"] for root in roots)
            self.local.wake.set()
        self.wake.set()

    def queue_batch(self, task_ids, names):
        names = list(dict.fromkeys(name for name in names if Path(name).suffix.lower() in IMAGE_EXTENSIONS))
        _, roots = self.sources()
        for task_id in task_ids:
            task = self.store.task(task_id)
            steps = dict(task.get("steps") or {})
            steps["image_check"] = "waiting" if names and roots else "skipped"
            self.store.update_task(task_id, steps=steps, image_check_names=names,
                image_check_total=len(names), image_check_done=0, image_check_compressed=0,
                image_check_error="", image_check_reason="" if names and roots else
                "本批没有下载根目录图片" if not names else "尚未绑定小米相册本地目录")
        self.request(refresh=False)

    def update_tasks(self):
        rows = self.store.db.execute("""SELECT id,data FROM tasks WHERE
            json_extract(data,'$.steps.image_check') IN ('waiting','active','failed')""").fetchall()
        scope = self.scope()
        for row in rows:
            task = json.loads(row["data"])
            names = task.get("image_check_names", [])
            done = candidates = errors = 0
            details = []
            for offset in range(0, len(names), 200):
                batch = names[offset:offset + 200]
                placeholders = ",".join("?" for _ in batch)
                for image in self.library.db.execute(f"SELECT active,saved_scope,saved_match,saved_error,error FROM images WHERE name IN ({placeholders})", batch):
                    if not image["active"]:
                        done += 1
                    elif image["error"]:
                        done += 1
                        errors += 1
                        details.append("本批有图片无法解码，请在全部图片查看")
                    elif scope and image["saved_scope"] == scope:
                        done += 1
                        candidates += bool(image["saved_match"])
                        errors += bool(image["saved_error"])
                        if image["saved_error"]:
                            details.append(image["saved_error"])
            steps = dict(task.get("steps") or {})
            steps["image_check"] = ("failed" if errors else "done") if done == len(names) else "active" if self.state["running"] else "waiting"
            self.store.update_task(row["id"], steps=steps, image_check_done=done,
                image_check_compressed=candidates, image_check_error="；".join(dict.fromkeys(details)))

    async def build_baselines(self, owner, roots):
        index, by_hash, versions = PerceptualIndex(), {}, {}
        seen = set()
        errors = 0
        self.state.update(running=True, phase="indexing", baselines=0, error="")
        for root in roots:
            rows = self.local.db.execute("SELECT name,size,path,version FROM files WHERE root_id=? AND generation=? ORDER BY path",
                                         (root["id"], root["generation"])).fetchall()
            for row in rows:
                if self.closing:
                    return False
                while self.busy() and not self.closing:
                    await asyncio.sleep(1)
                if Path(row["name"]).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                file = inside(Path(root["path"]), row["path"])
                if file in seen:
                    continue
                seen.add(file)
                self.state["current"] = row["name"]
                try:
                    record = await self.dedup.index_file(root, (row["name"], row["size"], row["path"], row["version"]))
                    if record["error"]:
                        errors += 1
                        continue
                except (FileNotFoundError, ValueError):
                    self.local.requested.add(root["id"])
                    self.local.wake.set()
                    self.state.update(phase="waiting", error="备份目录已变化，正在更新目录索引")
                    return False
                except IMAGE_ERRORS:
                    errors += 1
                    continue
                record.update(source=root, file=file)
                value = int(record["phash"], 16)
                if value not in by_hash:
                    index.add(value)
                by_hash.setdefault(value, []).append(record)
                versions[(root["id"], row["path"])] = row["version"]
                self.state["baselines"] += 1
        current_owner, current_roots = self.sources()
        if self.signature(owner, roots) != self.signature(current_owner, current_roots) or not self.ready(current_roots):
            return False
        self.index, self.by_hash = index, by_hash
        self.baseline_errors = errors
        self.generations = self.signature(owner, roots)
        # Recheck a previous positive when its particular reference changes or disappears.
        scope = self.scope_key(owner, roots)
        with self.library.db:
            for image in self.library.db.execute("SELECT id,saved_match FROM images WHERE active=1 AND saved_scope=? AND saved_match<>''", (scope,)).fetchall():
                match = json.loads(image["saved_match"])
                if versions.get((match["root_id"], match["path"])) != match["version"]:
                    self.library.db.execute("UPDATE images SET saved_scope='',saved_match='' WHERE id=?", (image["id"],))
        return True

    async def find_match(self, record, file):
        value = int(record["phash"], 16)
        candidates = []
        for neighbour in self.index.neighbours(value, 10):
            for candidate in self.by_hash[neighbour]:
                if (candidate["file"] == file or candidate["width"] <= record["width"]
                        or candidate["height"] <= record["height"] or candidate["size"] <= record["size"]):
                    continue
                a = candidate["width"] / candidate["height"]
                b = record["width"] / record["height"]
                if abs(a - b) / max(a, b) <= .005:
                    candidates.append(candidate)
        candidates.sort(key=lambda item: ((value ^ int(item["phash"], 16)).bit_count(), -item["width"] * item["height"], -item["size"]))
        for candidate in candidates:
            if self.closing:
                raise ValueError("检查已停止")
            score = await self.dedup.pair_score(file, record, candidate["file"], candidate)
            if score >= .995:
                return dict(root_id=candidate["root_id"], path=candidate["path"], version=candidate["version"],
                    feature_id=candidate["id"], width=candidate["width"], height=candidate["height"], size=candidate["size"],
                    root=candidate["source"]["path"], albums=candidate["source"]["albums"], ssim=score)
        verify_file(file, record["version"])
        return None

    async def check(self):
        owner, roots = self.sources()
        if not roots:
            self.state.update(phase="unbound", error="", running=False)
            return
        if self.busy() or not self.ready(roots):
            failed = [self.local.scan_errors.get(root["id"]) or root["error"] for root in roots
                      if self.local.scan_errors.get(root["id"]) or root["error"]]
            self.state.update(phase="waiting", error="；".join(failed), running=False)
            return
        baseline_changed = self.generations != self.signature(owner, roots)
        if baseline_changed:
            if not await self.build_baselines(owner, roots):
                self.state.update(running=False, phase="waiting", current="")
                return
        scope = self.scope()
        if not scope:
            return
        rows = self.library.db.execute("""SELECT * FROM images WHERE active=1 AND error=''
            AND monochrome IS NOT NULL AND time_source IS NOT NULL
            AND (saved_scope<>? OR (? AND saved_error<>'')) ORDER BY id""", (scope, self.retry_errors)).fetchall()
        self.retry_errors = False
        if not rows:
            self.state.update(phase="completed", running=False, error="", current="")
            if baseline_changed:
                self.state["last_check"] = time.time()
            self.update_tasks()
            return
        self.state.update(running=True, phase="comparing", done=0, total=len(rows), errors=0, error="")
        self.update_tasks()
        source = next((root for root in roots if Path(root["path"]) == self.library.root),
                      dict(id="downloads", path=str(self.library.root)))
        try:
            for row in rows:
                if self.closing or self.scope() != scope:
                    return
                while self.busy() and not self.closing:
                    await asyncio.sleep(1)
                error, match = "", None
                self.state["current"] = row["name"]
                try:
                    _, file = self.library.selected(row["id"], f"{row['mtime_ns']}:{row['size']}")
                    entry = (row["name"], row["size"], row["name"], file_version(file.stat()))
                    record = await self.dedup.index_file(source, entry)
                    if record["error"]:
                        raise ValueError(record["error"])
                    match = await self.find_match(record, file)
                    if not match and self.baseline_errors:
                        error = f"有 {self.baseline_errors} 张备份图片读取失败，未命中结果尚未确认"
                except IMAGE_ERRORS as exc:
                    error = str(exc)
                if self.scope() != scope:
                    return
                with self.library.db:
                    self.library.db.execute("""UPDATE images SET saved_scope=?,saved_match=?,saved_error=?
                        WHERE id=? AND active=1 AND size=? AND mtime_ns=?""",
                        (scope, json.dumps(match) if match else "", error, row["id"], row["size"], row["mtime_ns"]))
                self.state["done"] += 1
                self.state["errors"] += bool(error)
                if self.state["done"] % 20 == 0:
                    self.update_tasks()
            self.state.update(phase="completed", last_check=time.time())
        finally:
            if self.state["phase"] == "comparing" and self.state["done"] < self.state["total"]:
                self.state["phase"] = "waiting"
            self.state.update(running=False, current="")
            self.update_tasks()

    def selected_reference(self, image_id, version):
        image, _ = self.library.selected(image_id, version)
        match = image["saved_match"]
        if not match:
            raise ValueError("对比结果已变化，请刷新图片列表")
        _, roots = self.sources()
        root = next((root for root in roots if root["id"] == match["root_id"] and root["path"] == match["root"]), None)
        if not root:
            raise ValueError("原图目录已解除绑定，请重新检查")
        file = inside(Path(root["path"]), match["path"])
        verify_file(file, match["version"])
        return match, file

    def start(self):
        self.task = asyncio.create_task(self.run(), name="saved-image-check")

    async def run(self):
        while not self.closing:
            self.wake.clear()
            try:
                await self.check()
            except (OSError, ValueError, sqlite3.Error) as exc:
                LOGGER.exception("saved image check failed")
                self.state.update(running=False, phase="failed", error=f"{exc}；修复后点击刷新图片重试")
                await self.wake.wait()
                continue
            if not self.closing and not self.wake.is_set():
                try:
                    await asyncio.wait_for(self.wake.wait(), 15)
                except TimeoutError:
                    pass

    async def close(self):
        self.closing = True
        self.wake.set()
        if self.task:
            await self.task
