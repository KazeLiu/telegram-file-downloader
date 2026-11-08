"""Date-index and bounded thumbnail-cache checks without a cloud account."""
import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram_file_downloader.xiaomi_cloud import XiaomiCloud, XiaomiError


class TimelineChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"connection": "test", "userId": "1234"}
        self.cloud = XiaomiCloud(SimpleNamespace(get=lambda key: self.account))
        self.addAsyncCleanup(self.cloud.close)
        self.cloud.auth = AsyncMock(return_value=(self.account, "session"))

    async def test_index_prepares_then_sorts_nonempty_days(self):
        self.cloud.gallery = AsyncMock(side_effect=[
            {"isReady": False, "isRetriable": True}, {"isReady": True},
            {"dayCount": {"20200102": 31, "20261108": 2, "20200101": 0}},
        ])
        with patch("telegram_file_downloader.xiaomi_cloud.asyncio.sleep", new=AsyncMock()) as sleep:
            self.assertEqual(await self.cloud.timeline("test", "1"), {"days": [
                {"date": "20261108", "count": 2}, {"date": "20200102", "count": 31},
            ]})
            sleep.assert_awaited_once_with(1)
        calls = self.cloud.gallery.call_args_list
        self.assertEqual(calls[0].args[2], "/gallery/user/lite/index/prepare")
        self.assertEqual(calls[0].kwargs["form"], {})
        self.assertEqual(calls[-1].kwargs["query"], {"albumId": "1", "isShared": "false"})

    async def test_bad_index_and_unready_state_are_explicit(self):
        for data in ({"dayCount": {"20260230": 1}}, {"dayCount": {"20260101": True}}, {"dayCount": []}):
            self.cloud.gallery = AsyncMock(side_effect=[{"isReady": True}, data])
            with self.assertRaises(XiaomiError):
                await self.cloud.timeline("test", "1")
        self.cloud.gallery = AsyncMock(return_value={"isReady": False})
        with self.assertRaisesRegex(XiaomiError, "准备日期索引"):
            await self.cloud.timeline("test", "1")

    async def test_day_parameters_and_existing_pagination_contract(self):
        self.cloud.gallery = AsyncMock(return_value={"galleries": [], "isLastPage": True})
        await self.cloud.day_media("test", "1", "20200102", 2)
        self.assertEqual(self.cloud.gallery.call_args.kwargs["query"], {
            "albumId": "1", "pageNum": 2, "pageSize": 30, "isShared": "false", "startDate": "20200102", "endDate": "20200102",
        })
        await self.cloud.media_page("test", "1", 0, 200)
        self.assertNotIn("startDate", self.cloud.gallery.call_args.kwargs["query"])

    async def test_thumbnail_singleflight_reuse_expiry_and_source_change(self):
        self.cloud.cache_thumbnail("test", "1", "data:image/jpeg;base64,YQ==")
        entered, release = asyncio.Event(), asyncio.Event()
        async def fetch(*args):
            entered.set()
            await release.wait()
            return b"image", "image/jpeg"
        self.cloud.fetch_thumbnail = AsyncMock(side_effect=fetch)
        first = asyncio.create_task(self.cloud.thumbnail("test", "1"))
        await entered.wait()
        second = asyncio.create_task(self.cloud.thumbnail("test", "1"))
        await asyncio.sleep(0)
        release.set()
        a, b = await asyncio.gather(first, second)
        self.assertEqual(a, b)
        self.assertEqual(await self.cloud.thumbnail("test", "1"), a)
        self.assertEqual(self.cloud.fetch_thumbnail.await_count, 1)
        self.assertEqual(self.cloud.thumbnail_content_size, 5)
        cached = self.cloud.thumbnail_contents[("test", "1")]
        self.cloud.thumbnail_contents[("test", "1")] = (*cached[:3], time.monotonic() - 1)
        refreshed = await self.cloud.thumbnail("test", "1")
        self.assertNotEqual(a[2], refreshed[2])
        self.cloud.cache_thumbnail("test", "1", "data:image/jpeg;base64,Yg==")
        self.assertEqual(self.cloud.thumbnail_content_size, 0)
        self.assertNotIn(("test", "1"), self.cloud.thumbnail_contents)

    async def test_content_lru_is_bounded_and_account_scoped(self):
        self.cloud.fetch_thumbnail = AsyncMock(return_value=(b"1234", "image/jpeg"))
        with patch("telegram_file_downloader.xiaomi_cloud.THUMBNAIL_CACHE_BYTES", 6):
            for media_id in ("1", "2"):
                self.cloud.cache_thumbnail("test", media_id, "data:image/jpeg;base64,YQ==")
                await self.cloud.thumbnail("test", media_id)
            self.assertEqual(list(self.cloud.thumbnail_contents), [("test", "2")])
            self.assertEqual(self.cloud.thumbnail_content_size, 4)
        self.account = None
        with self.assertRaises(XiaomiError):
            await self.cloud.thumbnail("test", "2")

    async def test_recycle_evicts_content_and_all_matching_snapshots(self):
        self.cloud.cache_thumbnail("test", "1", "data:image/jpeg;base64,YQ==")
        await self.cloud.thumbnail("test", "1")
        self.cloud.remember_media("test", "1", [{"id": "1"}])
        self.cloud.remember_media("test", "2", [{"id": "1"}])
        self.cloud.gallery = AsyncMock(return_value={})
        await self.cloud.recycle("test", "1")
        self.assertEqual(self.cloud.thumbnail_content_size, 0)
        self.assertFalse(self.cloud.media_snapshots)
        self.assertNotIn(("test", "1"), self.cloud.thumbnail_sources)

    async def test_evicted_source_can_be_recovered_without_exposing_cloud_url(self):
        self.cloud.gallery = AsyncMock(return_value={"idTothumbnails": [{"id": "9", "thumbnails": {
            "small": {"data": "data:image/jpeg;base64,YQ=="},
        }}]})
        result = await self.cloud.thumbnail("test", "9")
        self.assertEqual(result[:2], (b"a", "image/jpeg"))
        self.assertEqual(self.cloud.gallery.call_args.kwargs["query"], {"ids": "9", "type": "small"})
        self.cloud.gallery = AsyncMock(return_value={"idTothumbnails": [{"id": "10", "thumbnails": {
            "small": {"data": "data:image/jpeg;base64,YQ==", "encryptInfo": {"key": "not-supported"}},
        }}]})
        with self.assertRaises(XiaomiError):
            await self.cloud.thumbnail("test", "10")
