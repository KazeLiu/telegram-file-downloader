"""Isolated photo-time/index checks; no cloud account or original files."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from telegram_file_downloader.image_library import ImageLibrary, image_time


class PhotoOrderTests(unittest.TestCase):
    def test_exif_offset_and_filesystem_fallback(self):
        image = Mock()
        exif = Mock()
        exif.get.return_value = None
        image.getexif.return_value = exif
        exif.get_ifd.return_value = {36867: "2026:11:01 08:30:00", 36881: "+08:00", 37521: "125"}
        fallback = {"created_ms": 1234, "mtime_ns": 5678000000}
        expected = round(datetime(2026, 11, 1, 0, 30, 0, 125000, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(image_time(image, fallback), (expected, "taken"))
        exif.get_ifd.return_value = {36867: "0000:00:00 00:00:00"}
        self.assertEqual(image_time(image, fallback), (5678, "modified"))
        self.assertEqual(image_time(image, {**fallback, "created_ms": None}), (5678, "modified"))

    def test_cached_creation_time_fallback_is_migrated_without_changing_exif_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = ImageLibrary(root, root)
            library.db.executemany("INSERT INTO images(name,size,mtime_ns,sort_time,time_source) VALUES (?,?,?,?,?)", [
                ("extracted.jpg", 1, 1742883900000000000, 1794081180000, "created"),
                ("camera.jpg", 1, 1742883900000000000, 1609502400000, "taken"),
            ])
            library.db.commit(); library.db.close()
            library = ImageLibrary(root, root)
            try:
                rows = library.db.execute("SELECT sort_time,time_source FROM images ORDER BY id").fetchall()
                self.assertEqual(tuple(rows[0]), (1742883900000, "modified"))
                self.assertEqual(tuple(rows[1]), (1609502400000, "taken"))
            finally:
                library.db.close()

    def test_old_index_migration_time_order_and_removed_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = sqlite3.connect(root / "images.sqlite3")
            db.execute("""CREATE TABLE images (id INTEGER PRIMARY KEY, name TEXT UNIQUE,
                size INTEGER, mtime_ns INTEGER, width INTEGER, height INTEGER, score INTEGER,
                features TEXT, monochrome INTEGER, error TEXT DEFAULT '', active INTEGER DEFAULT 1)""")
            db.executemany("INSERT INTO images(name,size,mtime_ns,monochrome) VALUES (?,?,?,?)",
                           [(f"{100 - i}.jpg", 1, (i // 2) * 1000000, 1) for i in range(65)])
            db.commit(); db.close()
            library = ImageLibrary(root, root)
            try:
                library.db.execute("UPDATE images SET time_source='modified'")
                library.db.commit()
                first = library.listing(candidate=True)
                self.assertEqual([item["id"] for item in first["items"]], list(range(65, 5, -1)))
                cursor = first["next_cursor"]
                library.remove(cursor)
                second = library.listing(candidate=True, after=cursor)
                self.assertEqual([item["id"] for item in second["items"]], [5, 4, 3, 2, 1])
                self.assertIsNone(second["next_cursor"])
            finally:
                library.db.close()


if __name__ == "__main__":
    unittest.main()
