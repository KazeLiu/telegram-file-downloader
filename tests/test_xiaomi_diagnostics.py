"""Request failures remain actionable without leaking request URLs or credentials."""
import ssl
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from telegram_file_downloader.xiaomi_cloud import XiaomiCloud, XiaomiError


class XiaomiDiagnosticsChecks(unittest.IsolatedAsyncioTestCase):
    async def test_network_error_reports_phase_and_type_without_signed_url(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        secret = "signed-secret-cookie"
        cloud.http = SimpleNamespace(cookies={}, send=AsyncMock(side_effect=httpx.ConnectError(secret)))
        with self.assertLogs("telegram_file_downloader.xiaomi_cloud", level="WARNING") as logs:
            with self.assertRaises(XiaomiError) as error:
                await cloud.request("POST", f"https://kssh2.xmssdn.micloud.mi.com/upload?token={secret}", cookies={"serviceToken": secret})
        self.assertEqual(error.exception.status, 503)
        self.assertIn("ConnectError", str(error.exception))
        self.assertIn("上传存储节点", str(error.exception))
        self.assertIn("HTTP=no_response", " ".join(logs.output))
        self.assertNotIn(secret, str(error.exception) + " ".join(logs.output))
        self.assertTrue(error.exception.retryable_connect)

    async def test_tls_eof_can_retry_but_certificate_and_read_errors_cannot(self):
        for native, retryable in ((ssl.SSLEOFError(8, "EOF"), True),
                                  (ssl.SSLCertVerificationError(1, "invalid certificate"), False),
                                  (httpx.ReadTimeout("read timed out"), False)):
            failure = native if isinstance(native, httpx.RequestError) else httpx.ConnectError("TLS failed")
            if failure is not native:
                failure.__cause__ = native
            cloud = XiaomiCloud.__new__(XiaomiCloud)
            cloud.http = SimpleNamespace(cookies={}, send=AsyncMock(side_effect=failure))
            with self.subTest(native=native), self.assertLogs("telegram_file_downloader.xiaomi_cloud", level="WARNING"), \
                    self.assertRaises(XiaomiError) as error:
                await cloud.request("POST", "https://ali.xmssdn.micloud.mi.com/upload")
            self.assertEqual(error.exception.retryable_connect, retryable)

    async def test_http_rate_limit_keeps_status_and_retry_hint(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.http = SimpleNamespace(cookies={}, send=AsyncMock(return_value=httpx.Response(429, headers={"Retry-After": "60"})))
        with self.assertLogs("telegram_file_downloader.xiaomi_cloud", level="WARNING") as logs:
            response = await cloud.request("POST", "https://i.mi.com/gallery/user/full")
        with self.assertRaises(XiaomiError) as error:
            cloud.check_http(response)
        self.assertEqual(error.exception.status, 429)
        self.assertIn("HTTP 429", str(error.exception))
        self.assertIn("retry_after=60", " ".join(logs.output))

    async def test_business_error_records_code_and_stops_more_dispatch(self):
        cloud = XiaomiCloud.__new__(XiaomiCloud)
        cloud.request = AsyncMock(return_value=httpx.Response(200, json={"code": 12345, "message": "private-token"}))
        with self.assertLogs("telegram_file_downloader.xiaomi_cloud", level="WARNING") as logs:
            with self.assertRaises(XiaomiError) as error:
                await cloud.gallery({"userId": "user"}, "secret", "/gallery/user/full", form={})
        self.assertEqual(error.exception.status, 409)
        self.assertIn("12345", str(error.exception))
        self.assertIn("code=12345", " ".join(logs.output))
        self.assertNotIn("private-token", " ".join(logs.output))
