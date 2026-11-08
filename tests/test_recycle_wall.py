"""Recycle previews and partial batch restore use temporary files only."""
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from telegram_file_downloader.image_library import recycle_thumbnail
from telegram_file_downloader.storage import RecycleBin, restore_batch


class RecycleWallChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.ids = [f"{i:032x}" for i in range(1, 4)]
        self.stamp = 1742883900
        with RecycleBin(self.root) as recycle:
            for i, record_id in enumerate(self.ids):
                file = self.root / f"photo-{i}.jpg"
                Image.new("RGB", (40, 20), "blue").save(file)
                os.utime(file, (self.stamp, self.stamp))
                recycle.move(file, record_id, "xiaomi_upload")

    def test_thumbnail_uses_recycled_bytes_and_keeps_original_date(self):
        with RecycleBin(self.root) as recycle:
            record, file = recycle.preview(self.ids[0])
            data = recycle_thumbnail(file)
            with Image.open(BytesIO(data)) as image:
                self.assertEqual(image.size, (40, 20))
                self.assertEqual(image.format, "JPEG")
            self.assertEqual(file.stat().st_mtime, self.stamp)
            self.assertEqual(record["original"], "photo-0.jpg")
            with patch("telegram_file_downloader.image_library.Image.MAX_IMAGE_PIXELS", 1), self.assertRaisesRegex(ValueError, "安全像素"):
                recycle_thumbnail(file)

    def test_batch_restore_reports_conflict_and_keeps_failed_copy(self):
        conflict = self.root / "photo-1.jpg"
        conflict.write_bytes(b"keep this new file")
        result = restore_batch(self.root, [*self.ids, self.ids[0]])
        self.assertEqual(result["restored"], [self.ids[0], self.ids[2]])
        self.assertEqual(result["failures"][0]["id"], self.ids[1])
        self.assertIn("不会覆盖", result["failures"][0]["error"])
        self.assertEqual(conflict.read_bytes(), b"keep this new file")
        self.assertEqual((self.root / "photo-0.jpg").stat().st_mtime, self.stamp)
        with RecycleBin(self.root) as recycle:
            self.assertEqual(recycle.listing()["total"], 1)
            with self.assertRaises(ValueError): recycle.preview(self.ids[0])
            self.assertTrue(recycle.preview(self.ids[1])[1].is_file())

    def test_preview_rejects_missing_and_changed_files(self):
        with RecycleBin(self.root) as recycle:
            _, file = recycle.preview(self.ids[0])
            file.write_bytes(b"changed")
            with self.assertRaises(ValueError): recycle.preview(self.ids[0])
            with self.assertRaises(ValueError): recycle.preview("f" * 32)
