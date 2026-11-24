"""Group the local image wall by a numbered filename or visual similarity."""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from pathlib import Path

from .image_dedup import IMAGE_ERRORS
from .image_similarity import PerceptualIndex, verify_file
from .storage import file_version, inside

LOGGER = logging.getLogger(__name__)
TERMINAL_DATE = re.compile(r"(?:^|[-_ ])\d{4}[-_]\d{2}[-_]\d{2}$")
SERIAL = re.compile(r"^(.+?)[-_ ]\s*[0-9]+$")
PHASH_DISTANCE = 16
MIN_SSIM = .75
MAX_CANDIDATES = 12


def filename_series(name):
    stem = re.sub(r" \(\d+\)$", "", Path(name).stem)
    match = SERIAL.fullmatch(stem)
    return match[1].rstrip() if match and not TERMINAL_DATE.search(stem) else ""


class ImageGroups:
    def __init__(self, library, dedup):
        self.library, self.dedup = library, dedup
        self.source = dict(id="downloads", path=str(library.root))
        self.task = None
        self.closing = False
        self.revision = None
        self.members = {}
        self.state = dict(phase="waiting", done=0, total=0, skipped=0, error="")

    def listing(self, mode, search):
        if mode == "similarity":
            revision = self.library.state["last_scan"]
            running = self.task and not self.task.done()
            if not running and (self.state["phase"] == "waiting" or self.revision != revision):
                if self.library.state["running"]:
                    return dict(groups=None, grouping=dict(phase="waiting", done=0, total=0, skipped=0, error=""))
                records = self.library.group_records()
                self.revision = revision
                self.state.update(phase="running", done=0, total=len(records), skipped=0, error="")
                self.task = asyncio.create_task(self.compute(records), name="local-image-groups")
            if self.state["phase"] != "ready":
                return dict(groups=None, grouping=self.state)

        groups, singles = {}, []
        scope = self.library.saved_scope()
        for row in self.library.group_records():
            item = self.library.public(dict(row), scope)
            if mode == "filename":
                label = filename_series(item["name"])
                key = f"filename:{label}" if label else ""
            else:
                member = self.members.get(item["id"])
                key = f"similarity:{member[1]}" if member and member[0] == item["version"] else ""
                label = ""
            if key:
                groups.setdefault(key, dict(key=key, label=label, items=[]))["items"].append(item)
            else:
                singles.append(item)

        result = []
        needle = search.casefold()
        for group in groups.values():
            items = group["items"]
            if len(items) == 1:
                singles.extend(items)
            elif not needle or any(needle in item["name"].casefold() for item in items):
                group["label"] = group["label"] or items[0]["name"]
                result.append(group)
        singles = [item for item in singles if needle in item["name"].casefold()]
        if singles:
            singles.sort(key=lambda item: (item["sort_time"], item["id"]), reverse=True)
            result.append(dict(key="ungrouped", label="未分组", items=singles))
        return dict(groups=result, grouping=self.state if mode == "similarity" else None)

    async def compute(self, records):
        index, anchors, exact, members = PerceptualIndex(), {}, {}, {}
        try:
            # Assign against fixed representatives so a chain of near matches cannot merge unrelated ends.
            ordered = sorted(records, key=lambda row: (-(row["width"] or 0) * (row["height"] or 0), -row["size"], row["id"]))
            for row in ordered:
                if self.closing:
                    return
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
                            if self.closing:
                                return
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
                    members[row["id"]] = (f"{row['mtime_ns']}:{row['size']}", group)
                except IMAGE_ERRORS:
                    self.state["skipped"] += 1
                self.state["done"] += 1
                await asyncio.sleep(0)
            self.members = members
            self.state["phase"] = "ready"
        except (sqlite3.Error, OSError, ValueError) as exc:
            LOGGER.exception("local image grouping failed")
            self.state.update(phase="error", error=str(exc))

    async def close(self):
        self.closing = True
        if self.task:
            await self.task
