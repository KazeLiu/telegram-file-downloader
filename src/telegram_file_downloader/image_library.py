"""Incremental root-only image index, thumbnails, and monochrome candidates."""
from __future__ import annotations

import asyncio
import logging
import json
import os
import sqlite3
import time
import warnings
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps, UnidentifiedImageError

from .storage import inside, is_link

LOGGER = logging.getLogger(__name__)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
IMAGE_FIELDS = "id,name,size,mtime_ns,width,height,monochrome,error,created_ms,sort_time,time_source,saved_scope,saved_match,saved_error"
PAGE_SIZE = 60
READY_IMAGES = "active=1 AND ((time_source IS NOT NULL AND monochrome IS NOT NULL) OR error<>'')"


def image_time(image, record):
    exif = image.getexif()
    details = exif.get_ifd(34665)
    for tag, offset_tag, fraction_tag, source in (
        (36867, 36881, 37521, "taken"),
        (36868, 36882, 37522, "digitized"),
        (306, 36880, 37520, "image"),
    ):
        value = details.get(tag) or exif.get(tag)
        if not isinstance(value, (str, bytes)) or not value:
            continue
        try:
            value = value.decode("ascii").strip("\x00 ") if isinstance(value, bytes) else value.strip("\x00 ")
            offset = details.get(offset_tag) or exif.get(offset_tag) or ""
            if isinstance(offset, bytes):
                offset = offset.decode("ascii").strip("\x00 ")
            stamp = datetime.strptime(value + (offset or ""), "%Y:%m:%d %H:%M:%S" + ("%z" if offset else ""))
            fraction = details.get(fraction_tag) or exif.get(fraction_tag)
            if isinstance(fraction, bytes):
                fraction = fraction.decode("ascii").strip("\x00 ")
            if isinstance(fraction, str) and fraction.isascii() and fraction.isdigit():
                stamp = stamp.replace(microsecond=int((fraction + "000000")[:6]))
            # EXIF without an offset uses the container's configured local timezone.
            return round(stamp.timestamp() * 1000), source
        except (UnicodeError, TypeError, ValueError, OverflowError, OSError):
            continue
    # Extraction and copying create a new filesystem birth time, not a new photo date.
    return record["mtime_ns"] // 1_000_000, "modified"


def recycle_thumbnail(file):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as image:
                image.draft("RGB", (320, 320))
                image.thumbnail((320, 320), Image.Resampling.LANCZOS)
                image = ImageOps.exif_transpose(image).convert("RGBA")
                canvas = Image.new("RGBA", image.size, "white")
                canvas.alpha_composite(image)
                output = BytesIO()
                canvas.convert("RGB").save(output, format="JPEG", quality=82)
                return output.getvalue()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError("图片超过安全像素限制，无法预览") from None


def is_monochrome(image):
    sample = image.copy()
    sample.thumbnail((256, 256), Image.Resampling.LANCZOS)
    red, green, blue = sample.split()
    lightest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
    chroma = ImageChops.subtract(lightest, darkest)
    # Ignore isolated color noise without letting a large white background dilute colored details.
    return chroma.filter(ImageFilter.MedianFilter(3)).getextrema()[1] <= 12


def inspect_image(root, record, cache):
    file = inside(root, record["name"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(file) as original:
            width, height = original.size
            sort_time, time_source = image_time(original, record)
            if original.getexif().get(274) in {5, 6, 7, 8}:
                width, height = height, width
            original.draft("RGB", (640, 640))
            original.thumbnail((640, 640), Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(original)
            rgba = image.convert("RGBA")
            canvas = Image.new("RGBA", rgba.size, "white")
            canvas.alpha_composite(rgba)
            rgb = canvas.convert("RGB")
            monochrome = is_monochrome(rgb)
            stat = file.stat()
            if (stat.st_size, stat.st_mtime_ns) != (record["size"], record["mtime_ns"]):
                raise ValueError("扫描期间文件发生变化，请刷新图片")
            target = cache / f"{record['id']}.jpg"
            temporary = cache / f"{record['id']}.tmp"
            rgb.save(temporary, format="JPEG", quality=82)
            os.replace(temporary, target)
    return dict(width=width, height=height, monochrome=monochrome, sort_time=sort_time, time_source=time_source)


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
            created = getattr(stat, "st_birthtime", None)
            created_ms = round(created * 1000) if created else None
            records.append((entry.name, stat.st_size, stat.st_mtime_ns, created_ms, stat.st_mtime_ns // 1_000_000))
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
                features TEXT, monochrome INTEGER, error TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
        """)
        # NULL distinguishes unclassified images from cached color results, including indexes from older releases.
        if not any(column["name"] == "monochrome" for column in self.db.execute("PRAGMA table_info(images)")):
            self.db.execute("ALTER TABLE images ADD COLUMN monochrome INTEGER")
        columns = {column["name"] for column in self.db.execute("PRAGMA table_info(images)")}
        for name, kind in (("created_ms", "INTEGER"), ("sort_time", "INTEGER"), ("time_source", "TEXT")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE images ADD COLUMN {name} {kind}")
        for name in ("saved_scope", "saved_match", "saved_error"):
            if name not in columns:
                self.db.execute(f"ALTER TABLE images ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        self.db.execute("UPDATE images SET sort_time=mtime_ns / 1000000 WHERE sort_time IS NULL")
        self.db.execute("UPDATE images SET sort_time=mtime_ns / 1000000,time_source='modified' WHERE time_source='created'")
        self.db.execute("CREATE INDEX IF NOT EXISTS images_active_time ON images(active,sort_time DESC,id DESC)")
        self.db.execute("DROP INDEX IF EXISTS images_active_name")
        self.db.commit()
        self.task = None
        self.scan_requested = False
        self.saved_check = None
        self.state = dict(running=False, done=0, total=0, error="", last_scan=None)

    def start_scan(self):
        self.scan_requested = True
        if not self.task or self.task.done():
            self.state.update(running=True, done=0, total=0, error="")
            self.task = asyncio.create_task(self.scan(), name="image-library-scan")
        return self.state

    async def scan(self):
        try:
            while self.scan_requested:
                self.scan_requested = False
                await self._scan()
        finally:
            self.state["running"] = False

    async def _scan(self):
        started = time.monotonic()
        self.state.update(done=0, total=0, error="")
        try:
            records = await asyncio.to_thread(root_images, self.root)
            with self.db:
                self.db.execute("UPDATE images SET active=0")
                self.db.executemany("""INSERT INTO images(name,size,mtime_ns,created_ms,sort_time) VALUES (?,?,?,?,?)
                    ON CONFLICT(name) DO UPDATE SET active=1,
                    width=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.width END,
                    height=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.height END,
                    score=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.score END,
                    features=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.features END,
                    saved_scope=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.saved_scope ELSE '' END,
                    saved_match=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.saved_match ELSE '' END,
                    saved_error=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.saved_error ELSE '' END,
                    monochrome=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.monochrome END,
                    error=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns THEN images.error ELSE '' END,
                    sort_time=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns AND images.time_source IS NOT NULL THEN images.sort_time ELSE excluded.sort_time END,
                    time_source=CASE WHEN images.size=excluded.size AND images.mtime_ns=excluded.mtime_ns AND images.created_ms IS excluded.created_ms THEN images.time_source END,
                    created_ms=excluded.created_ms,size=excluded.size,mtime_ns=excluded.mtime_ns""", records)
            cached = await asyncio.to_thread(lambda: {file.name for file in self.cache.iterdir()})
            active = self.db.execute(f"SELECT {IMAGE_FIELDS} FROM images WHERE active=1").fetchall()
            pending = [dict(row) for row in active if row["time_source"] is None or row["monochrome"] is None or row["error"] or f"{row['id']}.jpg" not in cached]
            self.state.update(total=len(active), done=len(active) - len(pending))
            LOGGER.info("image scan starting count=%s pending=%s", len(active), len(pending))
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
                            self.db.execute("UPDATE images SET error=?,monochrome=NULL WHERE id=?", (str(exc), record["id"]))
                    else:
                        with self.db:
                            self.db.execute("UPDATE images SET width=?,height=?,monochrome=?,sort_time=?,time_source=?,error='' WHERE id=? AND active=1 AND size=? AND mtime_ns=?",
                                (result["width"], result["height"], result["monochrome"], result["sort_time"], result["time_source"], record["id"], record["size"], record["mtime_ns"]))
                    self.state["done"] += 1
            await worker()
            self.state["last_scan"] = time.time()
            if self.saved_check:
                self.saved_check.request()
            LOGGER.info("image scan complete count=%s analyzed=%s elapsed=%.3fs", len(active), len(pending), time.monotonic() - started)
        except Exception as exc:
            LOGGER.exception("image scan failed")
            self.state["error"] = str(exc)

    def saved_scope(self):
        return (self.saved_check.scope() if self.saved_check else "") or "unavailable"

    def status(self, candidate=False, search="", compressed=False):
        scope = self.saved_scope()
        condition = READY_IMAGES + " AND instr(lower(name),lower(?))>0" + (" AND monochrome=1" if candidate else "")
        args = (search,)
        if compressed:
            condition += " AND saved_scope=? AND saved_match<>''"
            args += (scope,)
        total = self.db.execute(f"SELECT COUNT(*) FROM images WHERE {condition}", args).fetchone()[0]
        counts = self.db.execute(f"""SELECT COUNT(*) AS total,SUM(monochrome=1) AS candidates,
            SUM(error<>'') AS errors,SUM(({READY_IMAGES})) AS ready,
            SUM(saved_scope=? AND saved_match<>'') AS compressed,
            SUM(saved_scope=? AND saved_error<>'') AS comparison_errors FROM images WHERE active=1""", (scope, scope)).fetchone()
        return dict(total=total, counts=dict(counts), scan=self.state,
                    comparison=self.saved_check.status() if self.saved_check else None)

    def listing(self, page=1, candidate=False, search="", after=None, compressed=False):
        condition = READY_IMAGES + " AND instr(lower(name),lower(?))>0" + (" AND monochrome=1" if candidate else "")
        args = (search,)
        if compressed:
            condition += " AND saved_scope=? AND saved_match<>''"
            args += (self.saved_scope(),)
        offset = (page - 1) * PAGE_SIZE
        if after is not None:
            # Recycled images keep their index row, so removing one never shifts the next batch.
            anchor = self.db.execute("SELECT sort_time FROM images WHERE id=?", (after,)).fetchone()
            if not anchor:
                raise ValueError("图片列表已变化，请重新加载")
            condition += " AND (sort_time,id) < (?,?)"
            args = (*args, anchor["sort_time"], after)
            offset = 0
        rows = self.db.execute(f"SELECT {IMAGE_FIELDS} FROM images WHERE {condition} ORDER BY sort_time DESC,id DESC LIMIT ? OFFSET ?",
                               (*args, PAGE_SIZE + 1, offset)).fetchall()
        scope = self.saved_scope()
        items = [self.public(dict(row), scope) for row in rows[:PAGE_SIZE]]
        return dict(items=items, **self.status(candidate, search, compressed), page=page, page_size=PAGE_SIZE,
                    next_cursor=items[-1]["id"] if len(rows) > PAGE_SIZE else None)

    @staticmethod
    def public(record, saved_scope=""):
        scope = record.pop("saved_scope", "")
        match = record.pop("saved_match", "")
        error = record.pop("saved_error", "")
        record["saved_match"] = json.loads(match) if match and saved_scope and scope == saved_scope else None
        record["saved_error"] = error if saved_scope and scope == saved_scope else ""
        record["version"] = f"{record['mtime_ns']}:{record['size']}"
        if record["monochrome"] is not None:
            record["monochrome"] = bool(record["monochrome"])
        return record

    def selected(self, image_id, version):
        row = self.db.execute(f"SELECT {IMAGE_FIELDS} FROM images WHERE id=? AND active=1", (image_id,)).fetchone()
        if not row:
            raise ValueError("图片已移走或不存在，请刷新")
        record = self.public(dict(row), self.saved_scope())
        file = inside(self.root, record["name"])
        stat = file.stat()
        if version != record["version"] or (stat.st_size, stat.st_mtime_ns) != (record["size"], record["mtime_ns"]):
            raise ValueError("图片已发生变化，请刷新后重新选择")
        return record, file

    def picture(self, image_id):
        row = self.db.execute(f"SELECT {IMAGE_FIELDS} FROM images WHERE id=? AND active=1", (image_id,)).fetchone()
        if not row:
            raise ValueError("图片已移走或不存在，请刷新")
        record = self.public(dict(row), self.saved_scope())
        return self.selected(image_id, record["version"])[0]

    def remove(self, image_id):
        with self.db:
            self.db.execute("UPDATE images SET active=0 WHERE id=?", (image_id,))

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.db.close()
