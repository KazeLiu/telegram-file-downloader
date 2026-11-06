"""Isolated recycle checks; never use a live cloud account or the system Recycle Bin."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_file_downloader.console_store import ConsoleStore
from telegram_file_downloader.linked_recycle import LinkedRecycle
from telegram_file_downloader.storage import RETENTION_SECONDS, RecycleBin
from telegram_file_downloader.xiaomi_local import XiaomiLocalIndex


class Cloud:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.after = lambda: None

    def local_owner(self, connection):
        return "owner"

    def selected_media(self, connection, album, media_id):
        return {"id": media_id, "name": "photo.jpg", "size": 3}

    async def recycle(self, connection, media_id):
        self.calls += 1
        if self.fail:
            raise OSError("cloud offline")
        self.after()


class LinkedRecycleChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root, self.data = base / "files", base / "data"
        self.root.mkdir()
        self.file = self.root / "photo.jpg"
        self.file.write_bytes(b"123")
        self.store = ConsoleStore(self.data)
        self.index = XiaomiLocalIndex(self.data, lambda: False)
        self.index.bind("owner", "1", str(self.root))
        asyncio.run(self.index.scan(self.index.source("owner", "1")))
        self.cloud = Cloud()
        self.recycle = LinkedRecycle(self.store, self.cloud, self.index)

    def tearDown(self):
        self.index.db.close()
        self.store.close()
        self.temp.cleanup()

    def preview(self):
        return self.recycle.preview("connection", "1", ["2"])["items"][0]

    def execute(self, preview):
        return asyncio.run(self.recycle.execute("connection", "2", preview["token"]))

    def test_cloud_first_local_retry_and_idempotent_restore(self):
        preview = self.preview()
        self.cloud.fail = True
        with self.assertRaises(OSError):
            self.execute(preview)
        self.assertTrue(self.file.is_file())
        self.cloud.fail = False
        with patch.object(RecycleBin, "move", side_effect=OSError("read-only mount")):
            result = self.execute(preview)
        self.assertTrue(result["cloud_done"])
        self.assertFalse(result["local_done"])
        self.assertEqual(len(self.recycle.pending("connection")), 1)
        self.assertTrue(self.execute(preview)["local_done"])
        self.assertEqual(self.cloud.calls, 2)
        with RecycleBin(self.root) as recycle:
            recycle.restore(preview["token"])
        self.execute(preview)
        self.assertTrue(self.file.is_file())

    def test_duplicate_and_changed_files_are_kept(self):
        (self.root / "other").mkdir()
        (self.root / "other" / "photo.jpg").write_bytes(b"123")
        asyncio.run(self.index.scan(self.index.source("owner", "1")))
        self.assertEqual(self.preview()["status"], "kept")
        (self.root / "other" / "photo.jpg").unlink()
        asyncio.run(self.index.scan(self.index.source("owner", "1")))
        preview = self.preview()
        self.file.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.execute(preview)
        self.assertEqual(self.cloud.calls, 0)

    def test_file_changed_during_cloud_request_is_kept(self):
        preview = self.preview()
        self.cloud.after = lambda: self.file.write_bytes(b"changed")
        result = self.execute(preview)
        self.assertTrue(result["cloud_done"])
        self.assertFalse(result["local_done"])
        self.assertEqual(self.file.read_bytes(), b"changed")

    def test_retention_purge_and_replay(self):
        record_id = "a" * 32
        with RecycleBin(self.root) as recycle:
            recycle.move(self.file, record_id, "image")
            self.assertEqual(recycle.purge_expired()["removed"], 0)
            old = time.time() - RETENTION_SECONDS - 5
            with recycle.db:
                recycle.db.execute("UPDATE items SET created=? WHERE id=?", (old, record_id))
            hidden = recycle.files / record_id
            self.assertEqual(recycle.purge_expired()["removed"], 0)
            os.utime(hidden, (old, old))
            self.file.write_bytes(b"keep")
            with self.assertRaises(ValueError):
                recycle.restore(record_id)
            self.file.unlink()
            self.assertEqual(recycle.purge_expired()["removed"], 1)
            self.assertFalse(hidden.exists())
            self.assertEqual(recycle.listing()["total"], 0)
            with self.assertRaises(ValueError):
                recycle.restore(record_id)
            self.file.write_bytes(b"new")
            recycle.move(self.file, record_id, "image")
            self.assertEqual(self.file.read_bytes(), b"new")

    def test_purge_boundary_and_interruption_recovery(self):
        record_id = "b" * 32
        now = 2_000_000_000
        cutoff = now - RETENTION_SECONDS
        with RecycleBin(self.root) as recycle:
            recycle.move(self.file, record_id, "image")
            hidden = recycle.files / record_id
            with recycle.db:
                recycle.db.execute("UPDATE items SET created=? WHERE id=?", (cutoff + 1, record_id))
            os.utime(hidden, (cutoff, cutoff))
            with patch("telegram_file_downloader.storage.time.time", return_value=now):
                self.assertEqual(recycle.purge_expired()["removed"], 0)
                with recycle.db:
                    recycle.db.execute("UPDATE items SET created=? WHERE id=?", (cutoff, record_id))
                with patch.object(Path, "unlink", side_effect=OSError("busy")):
                    result = recycle.purge_expired()
                self.assertEqual(len(result["errors"]), 1)
                self.assertTrue(hidden.exists())
            hidden.unlink()
        with RecycleBin(self.root) as recycle:
            state = recycle.db.execute("SELECT state FROM items WHERE id=?", (record_id,)).fetchone()[0]
            self.assertEqual(state, "purged")


if __name__ == "__main__":
    unittest.main()
