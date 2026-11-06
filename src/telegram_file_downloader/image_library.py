"""Incremental root-only image index, thumbnails, and conservative sketch candidates."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .storage import inside, is_link

LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}


def sketch_features(image):
    sample = image.copy()
    sample.thumbnail((128, 128), Image.Resampling.LANCZOS)
    pixels = list(sample.getdata())
    colored = white = ink = mid = edges = 0
    luminance = []
    for red, green, blue in pixels:
        high, low = max(red, green, blue), min(red, green, blue)
        value = (299 * red + 587 * green + 114 * blue) / 1000
        colored += high - low > 24 and (high - low) / max(high, 1) > .15 and 25 < value < 245
        white += value > 235 and high - low < 30
        ink += value < 185
        mid += 100 < value < 225
        luminance.append(value)
    width, height = sample.size
    for y in range(height):
        for x in range(width - 1):
            offset = y * width + x
            edges += abs(luminance[offset] - luminance[offset + 1]) > 22
    count = max(len(pixels), 1)
    color_ratio, white_ratio = colored / count, white / count
    edge_ratio = edges / max((width - 1) * height, 1)
    score = 100 * (.50 * (1 - min(color_ratio / .20, 1)) + .30 * min(white_ratio / .55, 1)
                   + .20 * (1 - min(mid / count / .65, 1)))
    if ink / count < .005 or edge_ratio < .008:
        score = 0
    if color_ratio > .20 or white_ratio < .20:
        score = min(score, 49)
    # shortcut: visual features also match some monochrome finished art; candidates always require human review.
    return dict(score=round(score), color=round(color_ratio, 3), light=round(white_ratio, 3), edges=round(edge_ratio, 3))


def inspect_image(root, record, cache):
    file = inside(root, record["name"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(file) as original:
            width, height = original.size
            if original.getexif().get(274) in {5, 6, 7, 8}:
                width, height = height, width
            original.draft("RGB", (640, 640))
            original.thumbnail((640, 640), Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(original)
            rgba = image.convert("RGBA")
            canvas = Image.new("RGBA", rgba.size, "white")
            canvas.alpha_composite(rgba)
            rgb = canvas.convert("RGB")
            features = sketch_features(rgb)
            stat = file.stat()
            if (stat.st_size, stat.st_mtime_ns) != (record["size"], record["mtime_ns"]):
                raise ValueError("扫描期间文件发生变化，请刷新图片")
            target = cache / f"{record['id']}.jpg"
            temporary = cache / f"{record['id']}.tmp"
            rgb.save(temporary, format="JPEG", quality=82)
            os.replace(temporary, target)
    return dict(width=width, height=height, score=features["score"], features=json.dumps(features))


def root_images(root):
    records = []
    with os.scandir(root) as scan:
        for entry in scan:
            try:
                if Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS or is_link(entry) or not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            records.append((entry.name, stat.st_size, stat.st_mtime_ns))
    return records


class ImageLibrary:
    def __init__(self, root, data_dir):
        self.root = root
        self.cache = data_dir / "image-thumbnails"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "images.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL, width INTEGER, height INTEGER, score INTEGER,
                features TEXT, error TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS images_active_name ON images(active,name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS images_active_score ON images(active,score);
        """)
        self.task = None
        self.state = dict(running=False, done=0, total=0, error="", last_scan=None)

    def start_scan(self):
        if not self.task or self.task.done():
            self.state.update(running=True, done=0, total=0, error="")
            self.task = asyncio.create_task(self.scan(), name="image-library-scan")
        return self.state

    async def scan(self):
        started = time.monotonic()
        try:
            records = await asyncio.to_thread(root_images, self.root)
            with self.db:
                self.db.execute("UPDATE images SET active=0")
                self.db.executemany("""INSERT INTO images(name,size,mtime_ns) VALUES (?,?,?)
                    ON CONFLICT(name) DO UPDATE SET active=1,
                    width=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.width END,
                    height=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.height END,
                    score=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.score END,
                    features=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.features END,
                    error=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.error ELSE '' END,
                    size=excluded.size,mtime_ns=excluded.mtime_ns""", records)
            cached = await asyncio.to_thread(lambda: {file.name for file in self.cache.iterdir()})
            active = self.db.execute("SELECT * FROM images WHERE active=1").fetchall()
            pending = [dict(row) for row in active if row["width"] is None or row["error"] or f"{row['id']}.jpg" not in cached]
            self.state.update(total=len(active), done=len(active) - len(pending))
            iterator = iter(pending)
            async def worker():
                for record in iterator:
                    try:
                        result = await asyncio.to_thread(inspect_image, self.root, record, self.cache)
                    except FileNotFoundError:
                        with self.db:
                            self.db.execute("UPDATE images SET active=0 WHERE id=?", (record["id"],))
                    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                        LOGGER.warning("image analysis failed name=%s reason=%s", record["name"], exc)
                        with self.db:
                            self.db.execute("UPDATE images SET error=?,score=NULL WHERE id=?", (str(exc), record["id"]))
                    else:
                        with self.db:
                            self.db.execute("UPDATE images SET width=?,height=?,score=?,features=?,error='' WHERE id=? AND active=1 AND size=? AND mtime_ns=?",
                                (result["width"], result["height"], result["score"], result["features"], record["id"], record["size"], record["mtime_ns"]))
                    self.state["done"] += 1
            await worker()
            self.state["last_scan"] = time.time()
            LOGGER.info("image scan complete count=%s analyzed=%s elapsed=%.3fs", len(active), len(pending), time.monotonic() - started)
        except Exception as exc:
            LOGGER.exception("image scan failed")
            self.state["error"] = str(exc)
        finally:
            self.state["running"] = False

    def listing(self, page=1, candidate=False, threshold=80, search=""):
        condition = "active=1 AND instr(lower(name),lower(?))>0 AND (?=0 OR score>=?)"
        args = (search, candidate, threshold)
        total = self.db.execute(f"SELECT COUNT(*) FROM images WHERE {condition}", args).fetchone()[0]
        rows = self.db.execute(f"SELECT * FROM images WHERE {condition} ORDER BY name COLLATE NOCASE,id LIMIT 60 OFFSET ?",
                               (*args, (page - 1) * 60)).fetchall()
        items = [self.public(dict(row)) for row in rows]
        counts = self.db.execute("SELECT COUNT(*) AS total,SUM(score>=?) AS candidates,SUM(error<>'') AS errors FROM images WHERE active=1", (threshold,)).fetchone()
        return dict(items=items, total=total, page=page, page_size=60, counts=dict(counts), scan=self.state)

    @staticmethod
    def public(record):
        record["version"] = f"{record['mtime_ns']}:{record['size']}"
        record["features"] = json.loads(record["features"]) if record["features"] else None
        return record

    def selected(self, image_id, version):
        row = self.db.execute("SELECT * FROM images WHERE id=? AND active=1", (image_id,)).fetchone()
        if not row:
            raise ValueError("图片已移走或不存在，请刷新")
        record = self.public(dict(row))
        file = inside(self.root, record["name"])
        stat = file.stat()
        if version != record["version"] or (stat.st_size, stat.st_mtime_ns) != (record["size"], record["mtime_ns"]):
            raise ValueError("图片已发生变化，请刷新后重新选择")
        return record, file

    def remove(self, image_id):
        with self.db:
            self.db.execute("UPDATE images SET active=0 WHERE id=?", (image_id,))

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.db.close()
