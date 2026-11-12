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
PROFILE = "saved-compressed-v2:" + ALGORITHM


class SavedImageCheck:
    def __init__(self, library, dedup, local, cloud, store, busy):
        self.library, self.dedup, self.local = library, dedup, local
        self.cloud, self.store, self.busy = cloud, store, busy
        self.state = dict(running=False, phase="waiting", done=0, total=0, baselines=0, errors=0,
                          cached=0, prepared=0, error="", current="", last_check=None)
        self.wake = asyncio.Event()
        self.task = None
        self.closing = False
        self.generations = None
        self.index = PerceptualIndex()
        self.by_hash = {}
        self.records = {}
        self.rebuild_index = False
        self.index_owner = ""
        self.reference_revision = 0
        self.baseline_errors = 0
        self.retry_errors = False
        self.retry_baselines = False
        self.dedup.db.execute("ATTACH DATABASE ? AS inventory", (str(local.database),))
        self.dedup.db.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_baselines (
                owner TEXT NOT NULL, root_id TEXT NOT NULL, path TEXT NOT NULL,
                version TEXT NOT NULL, error TEXT NOT NULL,
                PRIMARY KEY(owner,root_id,path));
            CREATE TABLE IF NOT EXISTS workflow_index (
                owner TEXT PRIMARY KEY, profile TEXT NOT NULL, roots TEXT NOT NULL, revision INTEGER NOT NULL);
        """)

    def configuration(self, owner):
        return self.store.get("workflow_image_check:" + owner, dict(enabled=False, roots=[]))

    def settings(self, connection):
        owner = self.cloud.local_owner(connection)
        return {**self.configuration(owner), "cache": self.status()}

    def status(self):
        owner, roots = self.sources()
        enabled = bool(owner and self.configuration(owner)["enabled"])
        state = dict(self.state)
        if not roots or self.index_owner != owner:
            state.update(running=False, phase="disabled" if not enabled else "unbound" if not roots else "waiting",
                         baselines=0, cached=0, prepared=0, done=0, total=0, error="", current="")
        return state

    def save_settings(self, connection, enabled, root_ids):
        owner = self.cloud.local_owner(connection)
        roots = list(dict.fromkeys(root_ids))
        known = {row["id"]: row["path"] for row in self.local.db.execute("""SELECT roots.id,roots.path
            FROM roots JOIN bindings ON bindings.root_id=roots.id WHERE bindings.owner=?""", (owner,))}
        if any(root not in known for root in roots):
            raise ValueError("所选目录已解除绑定，请刷新目录列表")
        if enabled and not roots:
            raise ValueError("请至少选择一个工作流检查目录")
        if enabled and any(not Path(known[root]).is_dir() for root in roots):
            raise ValueError("所选目录不可访问，请检查挂载和读取权限")
        self.store.put("workflow_image_check:" + owner, dict(enabled=enabled, roots=roots))
        self.local.priority = set(roots) if enabled else set()
        if enabled:
            _, sources = self.sources()
            self.local.requested.update(root["id"] for root in sources if not root["generation"] or root["error"])
            self.local.wake.set()
        self.state.update(running=False, phase="waiting" if enabled else "disabled", error="", current="")
        self.request()
        self.update_tasks()
        return self.settings(connection)

    def sources(self):
        account = self.cloud.account()
        if not account:
            return "", []
        owner = self.cloud.local_owner(account["connection"])
        config = self.configuration(owner)
        if not config["enabled"] or not config["roots"]:
            return owner, []
        roots = {}
        placeholders = ",".join("?" for _ in config["roots"])
        for row in self.local.db.execute(f"""SELECT roots.*,bindings.album FROM roots JOIN bindings
                ON bindings.root_id=roots.id WHERE bindings.owner=? AND roots.id IN ({placeholders})
                ORDER BY roots.id,bindings.album""", (owner, *config["roots"])):
            root = roots.setdefault(row["id"], {**dict(row), "albums": []})
            root["albums"].append(row["album"])
        return owner, list(roots.values())

    @staticmethod
    def signature(owner, roots):
        return (owner, tuple((root["id"], root["generation"], tuple(root["albums"])) for root in roots))

    def ready(self, roots):
        return all(root["generation"] and not root["error"] and root["id"] not in self.local.progress
                   and not self.local.scan_errors.get(root["id"])
                   and root["id"] not in self.local.requested for root in roots)

    def scope(self):
        owner, roots = self.sources()
        if not roots or not self.ready(roots) or self.generations != self.signature(owner, roots):
            return ""
        return json.dumps([PROFILE, owner, self.reference_revision])

    def request(self, *, refresh=False, force=False):
        if force:
            self.retry_errors = self.retry_baselines = True
            with self.library.db:
                self.library.db.execute("UPDATE images SET saved_scope='' WHERE active=1")
        if refresh:
            _, roots = self.sources()
            self.local.requested.update(root["id"] for root in roots)
            self.local.wake.set()
        self.wake.set()

    def queue_batch(self, task_ids, names):
        names = list(dict.fromkeys(name for name in names if Path(name).suffix.lower() in IMAGE_EXTENSIONS))
        owner, roots = self.sources()
        config = self.configuration(owner) if owner else dict(enabled=False)
        for task_id in task_ids:
            task = self.store.task(task_id)
            steps = dict(task.get("steps") or {})
            steps["image_check"] = "waiting" if names and roots else "skipped"
            self.store.update_task(task_id, steps=steps, image_check_names=names,
                image_check_total=len(names), image_check_done=0, image_check_compressed=0,
                image_check_error="", image_check_reason="" if names and roots else
                "本批没有下载根目录图片" if not names else "工作流自动检查已关闭" if not config["enabled"]
                else "请在图片去重页选择工作流检查目录")
        self.request(refresh=False)

    def update_tasks(self):
        rows = self.store.db.execute("""SELECT id,data FROM tasks WHERE
            json_extract(data,'$.steps.image_check') IN ('waiting','active','failed')""").fetchall()
        scope = self.scope()
        _, sources = self.sources()
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
            if not sources:
                steps["image_check"] = "skipped"
                self.store.update_task(row["id"], steps=steps, image_check_reason="工作流自动检查已关闭或未选择有效目录")
                continue
            steps["image_check"] = ("failed" if errors else "done") if done == len(names) else "active" if self.state["running"] else "waiting"
            self.store.update_task(row["id"], steps=steps, image_check_done=done,
                image_check_compressed=candidates, image_check_error="；".join(dict.fromkeys(details)))

    def forget(self, key):
        record = self.records.pop(key)
        if not record["error"]:
            value = int(record["phash"], 16)
            self.by_hash[value].pop(key)
            if not self.by_hash[value]:
                del self.by_hash[value]
                self.rebuild_index = True

    async def build_baselines(self, owner, roots):
        expected = self.signature(owner, roots)
        previous = {(row["root_id"], row["path"]): (row["version"], row["error"])
                    for row in self.dedup.db.execute("SELECT * FROM workflow_baselines WHERE owner=?", (owner,))}
        if self.index_owner != owner:
            self.index, self.by_hash, self.records = PerceptualIndex(), {}, {}
            self.rebuild_index = False
            self.index_owner = owner
        seen, seen_files, manifest = set(), set(), {}
        self.state.update(running=True, phase="indexing", baselines=0, cached=0, prepared=0, error="")
        retry_errors = self.retry_baselines
        for root in roots:
            # Join the persisted inventory and features, without stat/decode for unchanged files.
            cursor = self.dedup.db.execute("""SELECT i.name,i.size AS inventory_size,i.path AS relative,
                i.version AS inventory_version,f.* FROM inventory.files i LEFT JOIN features f
                ON f.root_id=i.root_id AND f.path=i.path AND f.version=i.version AND f.algorithm=?
                WHERE i.root_id=? AND i.generation=? ORDER BY i.path""", (ALGORITHM, root["id"], root["generation"]))
            while True:
                batch = cursor.fetchmany(256)
                if not batch:
                    break
                if self.closing or expected != self.signature(*self.sources()):
                    return False
                while self.busy() and not self.closing:
                    await asyncio.sleep(1)
                if self.closing:
                    return False
                for row in batch:
                    if Path(row["name"]).suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    file = Path(root["path"]) / row["relative"]
                    if file in seen_files:
                        continue
                    seen_files.add(file)
                    key = (root["id"], row["relative"])
                    seen.add(key)
                    version = row["inventory_version"]
                    record = self.records.get(key)
                    if record and record["version"] == version and not (retry_errors and record["error"]):
                        record["source"] = root
                        self.state["cached"] += 1
                    else:
                        cached = row["id"] is not None and (row["error"] or
                            row["phash"] and row["digest"] and row["width"] and row["height"])
                        if cached and not (retry_errors and row["error"]):
                            record = {name: row[name] for name in
                                      ("id", "root_id", "path", "version", "width", "height", "size", "digest", "phash", "error")}
                            self.state["cached"] += 1
                        else:
                            if self.closing or expected != self.signature(*self.sources()):
                                return False
                            while self.busy() and not self.closing:
                                await asyncio.sleep(1)
                            if self.closing:
                                return False
                            self.state["current"] = row["name"]
                            try:
                                record = await self.dedup.index_file(root,
                                    (row["name"], row["inventory_size"], row["relative"], version))
                            except (FileNotFoundError, ValueError):
                                self.local.requested.add(root["id"])
                                self.local.wake.set()
                                self.state.update(error="备份目录已变化，正在更新目录索引")
                                return False
                            except IMAGE_ERRORS as exc:
                                record = dict(root_id=root["id"], path=row["relative"], version=version, error=str(exc))
                            self.state["prepared"] += 1
                        if key in self.records:
                            self.forget(key)
                        record.update(source=root, file=file)
                        self.records[key] = record
                        if not record["error"]:
                            value = int(record["phash"], 16)
                            if value not in self.by_hash:
                                self.index.add(value)
                            self.by_hash.setdefault(value, {})[key] = record
                    manifest[key] = (record["version"], record["error"])
                    self.state["baselines"] += not bool(record["error"])
                await asyncio.sleep(0)
        current_owner, current_roots = self.sources()
        if expected != self.signature(current_owner, current_roots) or not self.ready(current_roots):
            return False
        for key in self.records.keys() - seen:
            self.forget(key)
        if self.rebuild_index:
            # Rebuild keys once, rather than reinserting a BK subtree for every removed image.
            index = PerceptualIndex()
            for number, value in enumerate(self.by_hash):
                index.add(value)
                if number % 256 == 0:
                    await asyncio.sleep(0)
            if self.closing or expected != self.signature(*self.sources()):
                return False
            self.index, self.rebuild_index = index, False
        row = self.dedup.db.execute("SELECT * FROM workflow_index WHERE owner=?", (owner,)).fetchone()
        metadata = dict(row) if row else dict(profile="", roots="[]", revision=0)
        root_ids = [root["id"] for root in roots]
        changed = (manifest != previous or metadata["profile"] != PROFILE or json.loads(metadata["roots"]) != root_ids)
        revision = metadata["revision"] + int(changed)
        with self.dedup.db:
            self.dedup.db.executemany("DELETE FROM workflow_baselines WHERE owner=? AND root_id=? AND path=?",
                ((owner, *key) for key in previous.keys() - manifest.keys()))
            self.dedup.db.executemany("INSERT OR REPLACE INTO workflow_baselines VALUES (?,?,?,?,?)",
                ((owner, *key, *value) for key, value in manifest.items() if previous.get(key) != value))
            self.dedup.db.execute("INSERT OR REPLACE INTO workflow_index VALUES (?,?,?,?)",
                                  (owner, PROFILE, json.dumps(root_ids), revision))
        self.reference_revision = revision
        self.baseline_errors = sum(bool(record["error"]) for record in self.records.values())
        self.retry_baselines = False
        self.generations = expected
        return True

    async def find_match(self, record, file):
        value = int(record["phash"], 16)
        candidates = []
        for neighbour in self.index.neighbours(value, 10):
            for candidate in self.by_hash[neighbour].values():
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
        self.local.priority = {root["id"] for root in roots}
        if not roots:
            config = self.configuration(owner) if owner else dict(enabled=False)
            self.state.update(phase="unbound" if config["enabled"] else "disabled", error="", running=False)
            self.index, self.by_hash, self.records = PerceptualIndex(), {}, {}
            self.rebuild_index = False
            self.generations = None
            self.update_tasks()
            return
        if self.busy() or not self.ready(roots):
            failed = [self.local.scan_errors.get(root["id"]) or root["error"] for root in roots
                      if self.local.scan_errors.get(root["id"]) or root["error"]]
            self.state.update(phase="waiting", error="；".join(failed), running=False)
            return
        baseline_changed = self.generations != self.signature(owner, roots) or self.retry_baselines
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
        _, roots = self.sources()
        self.local.priority = {root["id"] for root in roots}
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
