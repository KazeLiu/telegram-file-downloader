"""Batch controls with temporary files and a fake cloud; no real uploads."""
import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from telegram_file_downloader.storage import file_version
from telegram_file_downloader.xiaomi_batch import XiaomiBatch, verification_ranges
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
        self.active = 0
        self.peak = 0
        self.failures = {}
        self.complete_receipts = False
        self.page_calls = []

    def account(self):
        return {"connection": "account"}

    async def albums(self, connection):
        return [{"id": "1"}]

    async def upload(self, connection, album, name, kind, mime, size, file):
        self.uploads.append(name)
        self.entered.put_nowait(name)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await self.release.get()
            if name in self.failures:
                raise self.failures[name]
            record = dict(id=str(len(self.records) + 1), sha1="receipt", size=size, groupId=album)
            self.records.append(record)
            return {"id": record["id"], "sha1": record["sha1"], "record": dict(record) if self.complete_receipts else {}, "lookup_time": None}
        finally:
            self.active -= 1

    async def media_page(self, connection, album, page, size, day=None, end_day=None):
        self.page_calls.append((page, size, day, end_day))
        self.verify_started.set()
        await self.verify_gate.wait()
        if self.verify_error:
            raise XiaomiError("verification unavailable")
        return self.records, True


class BatchControlChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.selected = []
        for name in ("first.jpg", "second.jpg", "third.jpg", "fourth.jpg", "fifth.jpg"):
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
        selected = self.selected if selected is None else selected
        await self.batch.start("account", "1", selected)
        for item in selected[:3]:
            self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), item["name"])

    def release(self, count):
        for _ in range(count):
            self.cloud.release.put_nowait(True)

    async def wait_state(self, state):
        async def wait():
            while self.batch.job["state"] != state:
                await asyncio.sleep(0)
        await asyncio.wait_for(wait(), 1)

    async def test_pause_finishes_current_then_resume_skips_completed_files(self):
        await self.start()
        self.control("pause")
        self.assertEqual(self.batch.job["state"], "pausing")
        self.release(3)
        await self.wait_state("paused")
        self.assertEqual(self.batch.job["done"], 3)
        self.assertEqual(self.cloud.uploads, [item["name"] for item in self.selected[:3]])
        with self.assertRaises(XiaomiError):
            await self.batch.start("account", "1", self.selected)
        self.control("resume")
        for name in ("fourth.jpg", "fifth.jpg"):
            self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), name)
        self.release(2)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "complete")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 5)
        self.assertFalse(self.cloud.write_lock.locked())

    async def test_stop_keeps_waiting_files_and_all_local_originals(self):
        await self.start()
        self.control("stop")
        self.release(3)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "stopped")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 3)
        self.assertEqual(self.batch.job["items"][3]["status"], "waiting")
        self.assertEqual(self.cloud.uploads, [item["name"] for item in self.selected[:3]])
        self.assertIs(self.batch.completed("account", self.batch.job["id"]), self.batch.job)
        self.assertTrue(all((self.root / item["name"]).is_file() for item in self.selected))
        self.assertFalse(self.cloud.write_lock.locked())

    async def test_stop_wakes_paused_worker(self):
        await self.start()
        self.control("pause")
        self.release(3)
        await self.wait_state("paused")
        self.control("stop")
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "stopped")
        self.assertEqual(self.cloud.uploads, [item["name"] for item in self.selected[:3]])

    async def test_stop_during_verification_preserves_receipt_check(self):
        self.cloud.verify_gate.clear()
        await self.start(self.selected[:1])
        self.release(1)
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
        self.release(3)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 0)
        self.assertEqual(self.batch.job["items"][0]["status"], "uploaded")
        self.assertTrue((self.root / "first.jpg").is_file())
        self.assertIn("核对未完成", self.batch.view("account", 1)["error"])
        self.cloud.verify_error = False
        await self.batch.verify(self.batch.job, fresh=True)
        self.assertEqual(self.batch.view("account", 1)["error"], "")
        self.assertEqual(self.batch.view("account", 1)["eligible"], 3)

    async def test_stale_batch_control_does_not_change_current_job(self):
        await self.start()
        with self.assertRaises(XiaomiError):
            self.batch.control("account", "old-job", "stop")
        self.assertEqual(self.batch.job["state"], "uploading")

    async def test_three_slots_refill_without_waiting_for_all_three(self):
        await self.start()
        view = self.batch.view("account", 1)
        self.assertEqual(view["counts"]["uploading"], 3)
        self.assertIn("third.jpg", view["current"])
        self.release(1)
        self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), "fourth.jpg")
        self.release(4)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.cloud.peak, 3)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 5)

    async def test_complete_receipts_confirm_three_uploads_without_album_scan(self):
        self.cloud.complete_receipts = True
        await self.start(self.selected[:3])
        self.release(3)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 3)
        self.assertEqual(self.cloud.page_calls, [])
        self.assertIsNone(self.batch.view("account", 1)["verification"])

    async def test_receipt_is_confirmed_while_other_files_are_still_uploading(self):
        self.cloud.complete_receipts = True
        await self.start()
        self.release(1)
        self.assertEqual(await asyncio.wait_for(self.cloud.entered.get(), 1), "fourth.jpg")
        view = self.batch.view("account", 1)
        self.assertEqual(view["state"], "uploading")
        self.assertEqual(view["counts"]["verified"], 1)
        self.assertEqual(view["counts"]["uploading"], 3)
        self.assertEqual(view["items"][0]["status"], "verified")
        self.assertEqual(self.cloud.page_calls, [])
        self.release(4)
        await asyncio.wait_for(self.batch.task, 1)

    async def test_only_missing_or_inconsistent_receipts_are_checked_after_upload(self):
        self.cloud.complete_receipts = True
        upload = self.cloud.upload
        async def incomplete_upload(connection, album, name, *args):
            result = await upload(connection, album, name, *args)
            if name == "second.jpg":
                result["record"] = {}
            if name == "third.jpg":
                result["record"]["groupId"] = "other-album"
            return result
        self.cloud.upload = incomplete_upload
        self.cloud.verify_gate.clear()
        await self.start()
        self.release(5)
        await asyncio.wait_for(self.cloud.verify_started.wait(), 1)
        view = self.batch.view("account", 1)
        self.assertEqual(view["state"], "verifying")
        self.assertEqual(view["counts"]["verified"], 3)
        self.assertEqual(view["counts"]["uploaded"], 2)
        self.assertEqual(view["verification"]["total"], 2)
        self.cloud.verify_gate.set()
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 5)
        self.assertEqual(self.batch.view("account", 1)["verification"]["done"], 2)
        self.assertEqual(len(self.cloud.page_calls), 1)

    async def test_pause_on_last_files_does_not_leave_batch_stuck(self):
        await self.start(self.selected[:3])
        self.control("pause")
        self.release(3)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.batch.job["state"], "complete")

    async def test_rate_limit_stops_new_files_and_drains_inflight_while_pausing(self):
        await self.start()
        self.cloud.failures["first.jpg"] = XiaomiError("rate limited", 429)
        self.control("pause")
        self.release(3)
        await asyncio.wait_for(self.batch.task, 1)
        self.assertIn("rate limited", self.batch.job["error"])
        self.assertEqual(len(self.cloud.uploads), 3)
        self.assertEqual(self.batch.view("account", 1)["eligible"], 2)
        self.assertEqual(self.batch.job["items"][3]["status"], "waiting")

    async def test_close_waits_for_all_upload_workers_and_releases_lock(self):
        await self.start()
        await self.batch.close()
        self.assertEqual(self.cloud.active, 0)
        self.assertFalse(self.cloud.write_lock.locked())
        self.assertTrue(all(item["status"] == "failed" for item in self.batch.job["items"][:3]))

    async def test_unexpected_worker_error_cancels_siblings_before_unlocking(self):
        await self.start()
        self.cloud.failures["first.jpg"] = RuntimeError("unexpected upload failure")
        self.release(1)
        with self.assertLogs("telegram_file_downloader.xiaomi_batch", level="ERROR"):
            await asyncio.wait_for(self.batch.task, 1)
        self.assertEqual(self.cloud.active, 0)
        self.assertFalse(self.cloud.write_lock.locked())
        self.assertTrue(self.batch.job["error"])
        self.assertEqual(len(self.cloud.uploads), 3)


class BatchVerificationChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.cloud = Cloud()
        self.batch = XiaomiBatch(self.cloud, self.root)
        self.items = []
        for index in range(3):
            name = f"{index}.jpg"
            path = self.root / name
            path.write_bytes(b"photo")
            record = dict(id=str(index + 1), sha1="receipt", size=5, groupId="1", dateTaken=1700000000000)
            self.cloud.records.append(record)
            self.items.append(dict(name=name, kind="image", version=file_version(path.stat()), status="verified", error="",
                                   receipt=(record["id"], "receipt", "5"), record=dict(record), lookup_time=record["dateTaken"]))
        self.job = dict(connection="account", album="1", items=self.items, revision=0, verification=None)

    async def asyncTearDown(self):
        await self.batch.close()
        self.temp.cleanup()

    async def test_fresh_check_queries_only_old_date_window_once(self):
        await self.batch.verify(self.job, fresh=True)
        self.assertEqual(self.cloud.page_calls, [(0, 200, "20231113", "20231115")])
        self.assertTrue(all(item["status"] == "verified" for item in self.items))
        self.assertEqual(self.job["verification"]["done"], 3)
        self.assertEqual(self.job["verification"]["pages"], 1)
        self.assertFalse(self.job["verification"]["active"])

    async def test_incomplete_receipt_uses_server_date_to_read_back(self):
        for item in self.items:
            item["record"].pop("groupId")
        await self.batch.verify(self.job)
        self.assertEqual(len(self.cloud.page_calls), 1)
        self.assertEqual(self.cloud.page_calls[0][2:], ("20231113", "20231115"))
        self.assertEqual(self.job["verification"]["done"], 3)

    async def test_unknown_date_explicitly_uses_legacy_album_scope(self):
        for item in self.items:
            item["lookup_time"] = None
        await self.batch.verify(self.job, fresh=True)
        self.assertEqual(self.cloud.page_calls, [(0, 200, None, None)])
        self.assertEqual(self.job["verification"]["phase"], "album")

    async def test_fresh_missing_or_changed_record_is_not_eligible(self):
        for patch in ({"sha1": "other"}, {"size": 6}, {"groupId": "2"}, {"status": "deleted"}):
            self.cloud.records[0] = {**self.items[0]["record"], **patch}
            await self.batch.verify(self.job, fresh=True)
            self.assertEqual(self.items[0]["status"], "uploaded")
            self.assertIn("本地文件已保留", self.items[0]["error"])
            self.assertTrue((self.root / self.items[0]["name"]).exists())

    async def test_pages_stop_as_soon_as_expected_ids_are_found(self):
        self.cloud.media_page = AsyncMock(side_effect=[([], False)])
        with self.assertRaises(XiaomiError):
            await self.batch.verify(self.job, fresh=True)
        self.cloud.media_page = AsyncMock(side_effect=[([{"id": "90"}], False), (self.cloud.records, False)])
        await self.batch.verify(self.job, fresh=True)
        self.assertEqual(self.cloud.media_page.await_count, 2)
        self.assertEqual(self.job["verification"]["pages"], 2)
        self.assertEqual(self.job["verification"]["done"], 3)

    async def test_network_failure_revokes_unchecked_cached_confirmations(self):
        self.cloud.media_page = AsyncMock(side_effect=[([self.cloud.records[0]], False), XiaomiError("network unavailable", 503)])
        with self.assertRaises(XiaomiError):
            await self.batch.verify(self.job, fresh=True)
        self.assertEqual([item["status"] for item in self.items], ["verified", "uploaded", "uploaded"])
        self.assertFalse(self.job["verification"]["active"])
        self.assertEqual(self.job["revision"], 1)
        self.assertTrue(all((self.root / item["name"]).exists() for item in self.items))

    async def test_only_freshly_verified_unchanged_local_images_are_recycled(self):
        self.cloud.records = self.cloud.records[:2]
        await self.batch.verify(self.job, fresh=True)
        (self.root / self.items[1]["name"]).write_bytes(b"changed")
        moved = await self.batch.recycle_images(self.job, self.items)
        self.assertEqual(moved, 1)
        self.assertEqual([item["status"] for item in self.items], ["recycled", "kept", "uploaded"])
        self.assertFalse((self.root / self.items[0]["name"]).exists())
        self.assertTrue((self.root / self.items[1]["name"]).exists())
        self.assertTrue((self.root / self.items[2]["name"]).exists())
        self.assertEqual(self.job["verification"]["phase"], "local")
        self.assertFalse(self.job["verification"]["active"])

    def test_adjacent_server_dates_share_one_window_and_unknown_dates_stay_separate(self):
        items = [{"lookup_time": int(datetime(2023, 11, day, tzinfo=timezone.utc).timestamp() * 1000)} for day in (14, 15, 30)]
        items.append({"lookup_time": None})
        ranges = verification_ranges(items)
        self.assertEqual([(start, end) for start, end, _ in ranges], [
            ("20231113", "20231116"), ("20231129", "20231201"), (None, None),
        ])
        self.assertEqual(len(ranges[0][2]), 2)


if __name__ == "__main__":
    unittest.main()
