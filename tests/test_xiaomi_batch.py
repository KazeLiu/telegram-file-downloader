"""Batch controls with temporary files and a fake cloud; no real uploads."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from telegram_file_downloader.storage import file_version
from telegram_file_downloader.xiaomi_batch import XiaomiBatch
from telegram_file_downloader.xiaomi_cloud import XiaomiError


class Cloud:
    def __init__(self):
        self.write_lock = asyncio.Lock()
        self.entered = asyncio.Queue()
        self.release = asyncio.Queue()
        self.verify_started = asyncio.Event()
        self.verify_gate = asyncio.Event()
        self.verify_gate.set()
        self.verify_error = False
        self.uploads = []
        self.records = []

    def account(self):
        return {"connection": "account"}

    async def albums(self, connection):
        return [{"id": "1"}]

    async def upload(self, connection, album, name, kind, mime, size, file):
        self.uploads.append(name)
        self.entered.put_nowait(name)
        await self.release.get()
        record = dict(id=str(len(self.records) + 1), sha1="receipt", size=size, groupId=album)
        self.records.append(record)
        return record

    async def media_page(self, connection, album, page, size):
        self.verify_started.set()
        await self.verify_gate.wait()
        if self.verify_error:
            raise XiaomiError("verification unavailable")
        return self.records, True


class BatchControlChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.selected = []
        for name in ("first.jpg", "second.jpg"):
            path = self.root / name
            path.write_bytes(b"photo")
            self.selected.append(dict(name=name, version=file_version(path.stat())))
        self.cloud = Cloud()
        self.batch = XiaomiBatch(self.cloud, self.root)

    async def asyncTearDown(self):
        await self.batch.close()
        self.temp.cleanup()

    def control(self, action):
        self.batch.control("account", self.batch.job["id"], action)

    async def start(self, selected=None):
        await self.batch.start("account", "1", self.selected if selected is None else selected)
        self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), "first.jpg")

    async def test_pause_finishes_current_then_resume_skips_completed_files(self):
        await self.start()
        self.control("pause")
        self.assertEqual(self.batch.job["state"], "pausing")
        self.cloud.release.put_nowait(True)
        await asyncio.sleep(0)
        self.assertEqual(self.batch.job["state"], "paused")
        self.assertEqual(self.batch.job["done"], 1)
        self.assertEqual(self.cloud.uploads, ["first.jpg"])
        with self.assertRaises(XiaomiError):
            await self.batch.start("account", "1", self.selected)
        self.control("resume")
        self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), "second.jpg")
        self.cloud.release.put_nowait(True)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "complete")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 2)
        self.assertFalse(self.cloud.write_lock.locked())

    async def test_stop_keeps_waiting_files_and_all_local_originals(self):
        await self.start()
        self.control("stop")
        self.cloud.release.put_nowait(True)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "stopped")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 1)
        self.assertEqual(self.batch.job["items"][1]["status"], "waiting")
        self.assertEqual(self.cloud.uploads, ["first.jpg"])
        self.assertIs(self.batch.completed("account", self.batch.job["id"]), self.batch.job)
        self.assertTrue(all((self.root / item["name"]).is_file() for item in self.selected))
        self.assertFalse(self.cloud.write_lock.locked())

    async def test_stop_wakes_paused_worker(self):
        await self.start()
        self.control("pause")
        self.cloud.release.put_nowait(True)
        await asyncio.sleep(0)
        self.assertEqual(self.batch.job["state"], "paused")
        self.control("stop")
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "stopped")
        self.assertEqual(self.cloud.uploads, ["first.jpg"])

    async def test_stop_during_verification_preserves_receipt_check(self):
        self.cloud.verify_gate.clear()
        await self.start(self.selected[:1])
        self.cloud.release.put_nowait(True)
        await asyncio.wait_for(self.cloud.verify_started.wait(), 1)
        self.control("stop")
        self.assertEqual(self.batch.job["state"], "stopping")
        self.cloud.verify_gate.set()
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "stopped")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 1)

    async def test_unconfirmed_upload_is_not_eligible_after_stop(self):
        self.cloud.verify_error = True
        await self.start()
        self.control("stop")
        self.cloud.release.put_nowait(True)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 0)
        self.assertEqual(self.batch.job["items"][0]["status"], "uploaded")
        self.assertTrue((self.root / "first.jpg").is_file())

    async def test_stale_batch_control_does_not_change_current_job(self):
        await self.start()
        with self.assertRaises(XiaomiError):
            self.batch.control("account", "old-job", "stop")
        self.assertEqual(self.batch.job["state"], "uploading")


if __name__ == "__main__":
    unittest.main()
