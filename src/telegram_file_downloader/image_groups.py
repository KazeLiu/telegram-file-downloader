"""Group the local image wall by a numbered filename or visual similarity."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
from pathlib import Path

from .image_dedup import IMAGE_ERRORS
from .image_library import IMAGE_EXTENSIONS
from .image_similarity import ALGORITHM, PerceptualIndex, verify_file
from .storage import file_version, inside

LOGGER = logging.getLogger(__name__)
TERMINAL_DATE = re.compile(r"(?:^|[-_ ])\d{4}[-_]\d{2}[-_]\d{2}$")
SERIAL = re.compile(r"^(.+?)[-_ ]\s*[0-9]+$")
PHASH_DISTANCE = 16
MIN_SSIM = .75
MAX_CANDIDATES = 12
PROFILE = f"local-groups-v1:{ALGORITHM}:{PHASH_DISTANCE}:{MIN_SSIM}:{MAX_CANDIDATES}"


def filename_series(name):
    stem = re.sub(r" \(\d+\)$", "", Path(name).stem)
    match = SERIAL.fullmatch(stem)
    return match[1].rstrip() if match and not TERMINAL_DATE.search(stem) else ""


def partition_groups(items, keys, mode):
    buckets = {}
    for item in items:
        key = keys[item["id"]][mode]
        if key:
            buckets.setdefault(key, []).append(item)
    groups = [dict(key=f"{mode}:{key}", label=key if mode == "filename" else members[0]["name"],
                   mode=mode, primary_count=len(members), items=members)
              for key, members in buckets.items() if len(members) > 1]
    assigned = {item["id"] for group in groups for item in group["items"]}
    return groups, [item for item in items if item["id"] not in assigned]


class ImageGroups:
    def __init__(self, library, dedup, store, busy):
        self.library, self.dedup = library, dedup
        self.store, self.busy = store, busy
        self.source = dict(id="downloads", path=str(library.root))
        self.task = None
        self.closing = False
        self.wake = asyncio.Event()
        self.library.db.execute("""CREATE TABLE IF NOT EXISTS similarity_groups (
            image_id INTEGER PRIMARY KEY, version TEXT NOT NULL, group_id INTEGER NOT NULL, profile TEXT NOT NULL)""")
        self.library.db.commit()
        self.members = {row["image_id"]: (row["version"], row["group_id"]) for row in
                        self.library.db.execute("SELECT * FROM similarity_groups WHERE profile=?", (PROFILE,))}
        self.processing = {}
        self.state = dict(phase="waiting", done=0, total=0, skipped=0, error="", last_check=None)

    def request(self):
        if not self.closing:
            if self.state["phase"] != "running":
                self.state.update(phase="waiting", error="")
            self.wake.set()

    def queue_batch(self, task_ids, names):
        names = list(dict.fromkeys(name for name in names if Path(name).suffix.lower() in IMAGE_EXTENSIONS))
        for task_id in task_ids:
            task = self.store.task(task_id)
            steps = dict(task.get("steps") or {})
            steps["image_group"] = "waiting" if names else "skipped"
            self.store.update_task(task_id, steps=steps, image_group_names=names,
                image_group_total=len(names), image_group_done=0, image_group_error="",
                image_group_reason="" if names else "本批没有下载根目录图片")
        self.request()

    def update_tasks(self):
        tasks = self.store.db.execute("""SELECT id,data FROM tasks WHERE
            json_extract(data,'$.steps.image_group') IN ('waiting','active','failed')""").fetchall()
        for row in tasks:
            task = json.loads(row["data"])
            names = task["image_group_names"]
            done, errors = 0, []
            for offset in range(0, len(names), 200):
                batch = names[offset:offset + 200]
                placeholders = ",".join("?" for _ in batch)
                for image in self.library.db.execute(f"SELECT id,active,size,mtime_ns,error FROM images WHERE name IN ({placeholders})", batch):
                    member = (self.processing.get(image["id"]) if self.state["phase"] == "running" else None) or self.members.get(image["id"])
                    if not image["active"]:
                        done += 1
                    elif member and member[0] == f"{image['mtime_ns']}:{image['size']}":
                        done += 1
                        if not member[1]:
                            errors.append(image["error"] or "图片未能参与相似分组，请刷新图片重试")
            error = self.state["error"] or self.library.state["error"] or "；".join(dict.fromkeys(errors))
            steps = dict(task["steps"])
            steps["image_group"] = "failed" if error else "done" if done == len(names) and self.state["phase"] == "ready" else (
                "active" if self.state["phase"] == "running" else "waiting")
            self.store.update_task(row["id"], steps=steps, image_group_done=done, image_group_error=error)

    def start(self):
        self.task = asyncio.create_task(self.run(), name="local-image-groups")
        self.request()

    async def run(self):
        while not self.closing:
            await self.wake.wait()
            self.wake.clear()
            while self.busy() and not self.closing:
                await asyncio.sleep(1)
            if self.closing:
                return
            self.wake.clear()
            try:
                if self.library.state["error"]:
                    raise ValueError("图片索引失败：" + self.library.state["error"])
                records = self.library.group_records()
                versions = {row["id"]: f"{row['mtime_ns']}:{row['size']}" for row in records}
                cached = versions == {image_id: member[0] for image_id, member in self.members.items()}
                retry = any((row["error"] and self.members.get(row["id"], ("", 0))[1]) or
                            (not row["error"] and not self.members.get(row["id"], ("", 0))[1]) for row in records)
                if cached and not retry:
                    self.state.update(phase="ready", done=len(records), total=len(records), error="",
                        skipped=sum(not member[1] for member in self.members.values()),
                        last_check=self.state["last_check"] or time.time())
                else:
                    self.processing = {}
                    self.state.update(phase="running", done=0, total=len(records), skipped=0, error="")
                    self.update_tasks()
                    if not await self.compute(records):
                        self.state["phase"] = "waiting"
                self.update_tasks()
            except (sqlite3.Error, OSError, ValueError) as exc:
                LOGGER.exception("local image grouping failed")
                self.state.update(phase="error", error=str(exc))
                self.update_tasks()

    def listing(self, mode, search, related=False):
        items, keys = [], {}
        scope = self.library.saved_scope()
        for row in self.library.group_records():
            item = self.library.public(dict(row), scope)
            member = self.members.get(item["id"])
            similarity = member[1] if member and member[0] == item["version"] and not item["error"] else 0
            keys[item["id"]] = dict(filename=filename_series(item["name"]), similarity=similarity)
            items.append(item)

        secondary = "similarity" if mode == "filename" else "filename"
        groups, remaining = partition_groups(items, keys, mode)
        if related:
            owners = {}
            # Only original primary members define associations; existing groups never merge or form chains.
            for group in groups:
                for item in group["items"]:
                    key = keys[item["id"]][secondary]
                    if key:
                        owners.setdefault(key, group)
            unassigned = []
            for item in remaining:
                owner = owners.get(keys[item["id"]][secondary])
                if owner is None:
                    unassigned.append(item)
                else:
                    owner["items"].append(item)
                    owner["related_by"] = secondary
            remaining = unassigned
        secondary_groups, singles = partition_groups(remaining, keys, secondary)
        needle = search.casefold()
        result = [group for group in groups + secondary_groups
                  if not needle or any(needle in item["name"].casefold() for item in group["items"])]
        singles = [item for item in singles if needle in item["name"].casefold()]
        if singles:
            result.append(dict(key="ungrouped", label="未分组", primary_count=len(singles), items=singles))
        return dict(groups=result, grouping=self.state)

    async def compute(self, records):
        index, anchors, exact, members = PerceptualIndex(), {}, {}, {}
        self.processing = members
        # Assign against fixed representatives so a chain of near matches cannot merge unrelated ends.
        ordered = sorted(records, key=lambda row: (-(row["width"] or 0) * (row["height"] or 0), -row["size"], row["id"]))
        for row in ordered:
            while self.busy() and not self.closing:
                await asyncio.sleep(1)
            if self.closing or self.wake.is_set():
                return False
            group = 0
            try:
                if row["error"]:
                    raise ValueError(row["error"])
                file = inside(self.library.root, row["name"])
                stat = file.stat()
                if (stat.st_size, stat.st_mtime_ns) != (row["size"], row["mtime_ns"]):
                    raise ValueError("图片已变化，请刷新图片")
                feature = await self.dedup.index_file(self.source, (row["name"], row["size"], row["name"], file_version(stat)))
                if feature["error"]:
                    raise ValueError(feature["error"])
                group = exact.get(feature["digest"])
                if group is None:
                    value = int(feature["phash"], 16)
                    aspect = feature["width"] / feature["height"]
                    candidates = [candidate for neighbour in index.neighbours(value, PHASH_DISTANCE)
                                  for candidate in anchors[neighbour]
                                  if abs(aspect - candidate[3]) / max(aspect, candidate[3]) <= .005]
                    candidates.sort(key=lambda candidate: ((value ^ candidate[4]).bit_count(), candidate[0]))
                    best = MIN_SSIM
                    comparison_failed = False
                    # shortcut: bound SSIM work per image; widen the shortlist if real series are missed.
                    for anchor, anchor_file, reference, _, _ in candidates[:MAX_CANDIDATES]:
                        if self.closing or self.wake.is_set():
                            return False
                        try:
                            score = await self.dedup.pair_score(anchor_file, reference, file, feature)
                        except IMAGE_ERRORS as exc:
                            LOGGER.debug("image group pair unavailable: %s / %s: %s", anchor_file.name, file.name, exc)
                            comparison_failed = True
                            continue
                        if score > best or (group is None and score == best):
                            best, group = score, anchor
                    if comparison_failed:
                        verify_file(file, feature["version"])
                    if group is None:
                        group = row["id"]
                        index.add(value)
                        anchors.setdefault(value, []).append((group, file, feature, aspect, value))
                    exact[feature["digest"]] = group
            except IMAGE_ERRORS as exc:
                LOGGER.debug("image group unavailable name=%s: %s", row["name"], exc)
                group = 0
                self.state["skipped"] += 1
            members[row["id"]] = (f"{row['mtime_ns']}:{row['size']}", group)
            self.state["done"] += 1
            if self.state["done"] % 20 == 0:
                self.update_tasks()
            await asyncio.sleep(0)
        if self.closing or self.wake.is_set() or self.library.state["running"]:
            return False
        with self.library.db:
            self.library.db.execute("DELETE FROM similarity_groups")
            self.library.db.executemany("INSERT INTO similarity_groups VALUES (?,?,?,?)",
                ((image_id, *member, PROFILE) for image_id, member in members.items()))
        self.members = members
        self.state.update(phase="ready", last_check=time.time())
        LOGGER.info("local image grouping complete count=%s skipped=%s", len(records), self.state["skipped"])
        return True

    async def close(self):
        self.closing = True
        self.wake.set()
        if self.task:
            await self.task
