"""Upload timestamp and storage-boundary checks; no cloud requests or original files."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

from telegram_file_downloader.storage import file_version
from telegram_file_downloader.xiaomi_cloud import BLOCK_SIZE, STORAGE_HOSTS, XiaomiCloud, XiaomiError, upload_dates, xiaomi_url


class UploadDatesChecks(unittest.TestCase):
    def setUp(self):
        self.file = tempfile.TemporaryFile()
        self.addCleanup(self.file.close)
        Image.new("RGB", (2, 2)).save(self.file, format="PNG")
        self.info = SimpleNamespace(st_birthtime=1790152905.215, st_mtime_ns=1789887737000000000)

    def test_original_file_times_and_browser_time_ignore_temporary_birth(self):
        with patch("telegram_file_downloader.xiaomi_cloud.os.fstat", return_value=self.info):
            dates = upload_dates(self.file, "image")
            self.assertEqual(dates, {"dateTaken": 1789887737000, "dateModified": 1789887737000})
            self.assertEqual(self.file.tell(), 0)
            self.assertFalse(self.file.closed)
            self.assertEqual(upload_dates(self.file, "image", 1609502400000),
                             {"dateTaken": 1609502400000, "dateModified": 1609502400000})
            del self.info.st_birthtime
            self.assertEqual(upload_dates(self.file, "video"),
                             {"dateTaken": 1789887737000, "dateModified": 1789887737000})

    def test_exif_date_with_offset_wins_over_file_creation(self):
        self.file.seek(0)
        self.file.truncate()
        exif = Image.Exif()
        exif[36867] = "2020:01:02 12:00:00"
        exif[36881] = "+08:00"
        Image.new("RGB", (2, 2)).save(self.file, format="JPEG", exif=exif)
        expected = round(datetime(2020, 1, 2, 4, tzinfo=timezone.utc).timestamp() * 1000)
        with patch("telegram_file_downloader.xiaomi_cloud.os.fstat", return_value=self.info):
            dates = upload_dates(self.file, "image")
        self.assertEqual(dates["dateTaken"], expected)
        self.assertEqual(dates["dateModified"], 1789887737000)
        self.assertEqual(self.file.tell(), 0)

    def test_unreadable_metadata_reports_file_time_fallback(self):
        with patch("telegram_file_downloader.xiaomi_cloud.os.fstat", return_value=self.info), \
                patch("telegram_file_downloader.xiaomi_cloud.Image.open", side_effect=OSError("unsupported image")), \
                self.assertLogs("telegram_file_downloader.xiaomi_cloud", level="WARNING"):
            self.assertEqual(upload_dates(self.file, "image")["dateTaken"], 1789887737000)

    def test_official_storage_node_allowed_without_weakening_url_checks(self):
        node = "https://kssh2.xmssdn.micloud.mi.com/2/1595215017082"
        self.assertEqual(xiaomi_url(node, STORAGE_HOSTS), node)
        for invalid in (node.replace("https:", "http:"),
                        "https://xmssdn.micloud.mi.com.evil.test/upload",
                        "https://user@kssh2.xmssdn.micloud.mi.com/upload",
                        "https://kssh2.xmssdn.micloud.mi.com:80/upload"):
            with self.subTest(invalid=invalid), self.assertRaises(XiaomiError):
                xiaomi_url(invalid, STORAGE_HOSTS)

    def test_windows_path_and_handle_versions_keep_same_birthtime(self):
        path = SimpleNamespace(st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_ctime_ns=5, st_birthtime_ns=5)
        handle = SimpleNamespace(**{**vars(path), "st_ctime_ns": 6})
        with patch("telegram_file_downloader.storage.os.name", "nt"):
            self.assertEqual(file_version(path), file_version(handle))
        with patch("telegram_file_downloader.storage.os.name", "posix"):
            self.assertNotEqual(file_version(path), file_version(handle))


class UploadPayloadChecks(unittest.IsolatedAsyncioTestCase):
    async def test_dates_reach_create_request_and_dedup_does_not_need_storage_url(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.auth = AsyncMock(return_value=({}, "test-session"))
        cloud.gallery = AsyncMock(return_value={"content": {"id": "1"}, "fileExists": True})
        with tempfile.TemporaryFile() as file:
            Image.new("RGB", (2, 2)).save(file, format="PNG")
            size = file.tell()
            result = await cloud.upload("connection", "1", "photo.png", "image", "image/png", size, file,
                                        modified_at=1609502400000)
            content = json.loads(cloud.gallery.call_args.kwargs["form"]["data"])["content"]
        self.assertEqual(content["dateTaken"], 1609502400000)
        self.assertEqual(content["dateModified"], 1609502400000)
        self.assertTrue(result["exists"])

    async def test_new_upload_uses_official_node_and_commits_without_account_cookies(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.auth = AsyncMock(return_value=({}, "test-session"))
        cloud.gallery = AsyncMock(side_effect=[{
            "content": {"id": "1"}, "kss": {
                "node_urls": ["https://kssh2.xmssdn.micloud.mi.com/2/1595215017082"],
                "file_meta": "file", "block_metas": [{"block_meta": "first"}, {"block_meta": "second"}],
            },
        }, {}])
        cloud.request = AsyncMock(side_effect=[httpx.Response(200, json={"commit_meta": "first-commit"}),
                                              XiaomiError("TLS EOF", 503, retryable_connect=True),
                                              httpx.Response(200, json={"commit_meta": "second-commit"})])
        with tempfile.TemporaryFile() as file, patch("telegram_file_downloader.xiaomi_cloud.asyncio.sleep", new_callable=AsyncMock) as sleep:
            Image.new("RGB", (2, 2)).save(file, format="PNG")
            file.seek(BLOCK_SIZE)
            file.write(b"x")
            result = await cloud.upload("connection", "1", "photo.png", "image", "image/png", file.tell(), file)
        self.assertFalse(result["exists"])
        self.assertTrue(cloud.request.call_args.args[1].startswith("https://kssh2.xmssdn.micloud.mi.com/"))
        self.assertNotIn("cookies", cloud.request.call_args.kwargs)
        self.assertEqual(cloud.request.await_count, 3)
        self.assertEqual(len(cloud.request.call_args_list[0].kwargs["content"]), BLOCK_SIZE)
        self.assertEqual(cloud.request.call_args_list[1], cloud.request.call_args_list[2])
        sleep.assert_awaited_once_with(1)
        self.assertEqual(cloud.gallery.call_args.args[2], "/gallery/user/full/1/storage")
        self.assertEqual(json.loads(cloud.gallery.call_args.kwargs["form"]["data"])["kss"]["commit_metas"],
                         [{"commit_meta": "first-commit"}, {"commit_meta": "second-commit"}])

    async def test_chunk_retry_is_bounded_and_never_retries_http_or_business_rejections(self):
        for failure, attempts in ((XiaomiError("TLS EOF", 503, retryable_connect=True), 3),
                                  (XiaomiError("certificate failure", 503), 1),
                                  (httpx.Response(429), 1), (httpx.Response(403), 1),
                                  (httpx.Response(503), 1)):
            with self.subTest(failure=failure):
                cloud = XiaomiCloud.__new__(XiaomiCloud)
                cloud.auth = AsyncMock(return_value=({}, "test-session"))
                cloud.gallery = AsyncMock(return_value={"content": {"id": "1"}, "kss": {
                    "node_urls": ["https://kssh2.xmssdn.micloud.mi.com/upload"],
                    "file_meta": "private", "block_metas": [{"block_meta": "private"}],
                }})
                cloud.request = AsyncMock(side_effect=failure if isinstance(failure, Exception) else None,
                                          return_value=failure)
                with tempfile.TemporaryFile() as file, patch("telegram_file_downloader.xiaomi_cloud.asyncio.sleep", new_callable=AsyncMock), \
                        self.assertRaises(XiaomiError):
                    Image.new("RGB", (2, 2)).save(file, format="PNG")
                    await cloud.upload("connection", "1", "photo.png", "image", "image/png", file.tell(), file)
                self.assertEqual(cloud.request.await_count, attempts)
                self.assertEqual(cloud.gallery.await_count, 1)

    async def test_final_record_not_create_record_is_used_as_upload_proof(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.auth = AsyncMock(return_value=({}, "test-session"))
        cloud.gallery = AsyncMock(side_effect=[{
            "content": {"id": "1", "dateTaken": 1609502400000, "groupId": "1", "sha1": "create-only", "size": 1},
            "kss": {"node_urls": ["https://kssh2.xmssdn.micloud.mi.com/upload"], "file_meta": "file",
                    "block_metas": [{"is_existed": 1, "commit_meta": "commit"}]},
        }, {"content": {"id": "1", "groupId": "1", "sha1": "committed", "size": 2, "encryptInfo": "private"}}])
        with tempfile.TemporaryFile() as file:
            file.write(b"a")
            result = await cloud.upload("connection", "1", "photo.jpg", "image", "image/jpeg", 1, file)
        self.assertEqual(result["record"], {"id": "1", "groupId": "1", "sha1": "committed", "size": 2})
        self.assertEqual(result["lookup_time"], 1609502400000)

    async def test_duplicate_preserves_server_date_and_album(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.auth = AsyncMock(return_value=({}, "test-session"))
        cloud.gallery = AsyncMock(return_value={"fileExists": True, "content": {
            "id": "7", "groupId": "2", "sha1": "existing", "size": 3, "sortTime": 946684800000,
        }})
        with tempfile.TemporaryFile() as file:
            file.write(b"abc")
            result = await cloud.upload("connection", "1", "photo.jpg", "image", "image/jpeg", 3, file, modified_at=1609502400000)
        self.assertEqual(result["lookup_time"], 946684800000)
        self.assertEqual(result["record"]["groupId"], "2")


if __name__ == "__main__":
    unittest.main()
