"""QR session persistence and request/account boundaries with synthetic values."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from asoul_support.qr_login import QrLoginSession
from asoul_support.login_fields import login_context
from asoul_support.runtime import save_login, read_json
from asoul_support import heartbeat


class LoginContextTests(unittest.TestCase):
    def cookies(self):
        return {
            "SESSDATA": "synthetic-session",
            "bili_jct": "synthetic-csrf",
            "DedeUserID": "123",
            "DedeUserID__ckMd5": "synthetic-md5",
            "sid": "synthetic-sid",
            "buvid3": "server-device",
            "unrelated": "drop",
        }

    def test_qr_retains_device_and_account_cookies_without_exposing_repr(self):
        cookies = self.cookies()
        request = Mock(
            side_effect=[
                (
                    {"url": "https://account.bilibili.com/scan", "qrcode_key": "synthetic"},
                    {"buvid3": "server-device"},
                ),
                ({"code": 0}, {k: v for k, v in cookies.items() if k != "buvid3"}),
            ]
        )
        session = QrLoginSession(request)
        session.generate()
        result = session.poll()
        self.assertEqual(result.context["cookies"]["DedeUserID"], "123")
        self.assertEqual(result.context["cookies"]["buvid3"], "server-device")
        self.assertNotIn("unrelated", result.context["cookies"])
        self.assertEqual(set(result.credentials), {"SESSDATA", "bili_jct"})
        self.assertNotIn("synthetic", repr(result))
        session.cancel()
        self.assertFalse(session.cookies)
        self.assertEqual(result.context["cookies"]["sid"], "synthetic-sid")

    def test_context_rejects_header_injection_without_secret_in_errors(self):
        for cookies, ua in (
            ({**self.cookies(), "sid": "synthetic-secret\r\nInjected"}, "UA"),
            (self.cookies(), "UA\nInjected"),
        ):
            with self.assertRaises(ValueError) as captured:
                login_context(cookies, ua)
            self.assertNotIn("synthetic-secret", str(captured.exception))

    def test_login_and_context_save_atomically_rejects_foreign_session(self):
        context = login_context(self.cookies(), "QR UA")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            save_login("synthetic-session", "synthetic-csrf", path, context=context)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_login("foreign-session", "synthetic-csrf", path, context=context)
            self.assertEqual(path.read_bytes(), before)
            save_login("new-session", "new-csrf", path)
            self.assertNotIn("qr_login_context", read_json(path))

    def test_like_headers_use_matching_qr_identity_and_user_agent(self):
        context = login_context(self.cookies(), "QR UA")
        saved = {
            "SESSDATA": "synthetic-session",
            "bili_jct": "synthetic-csrf",
            "qr_login_context": context,
        }
        with patch.object(heartbeat, "load_cookies", return_value=saved):
            headers = heartbeat._live_like_headers(2, 123, "synthetic-session", "synthetic-csrf")
            self.assertEqual(headers["User-Agent"], "QR UA")
            self.assertIn("DedeUserID=123", headers["Cookie"])
            self.assertIn("buvid3=server-device", headers["Cookie"])
            self.assertNotIn("unrelated", headers["Cookie"])
            self.assertIsNone(
                heartbeat._live_like_headers(2, 456, "synthetic-session", "synthetic-csrf")
            )
            self.assertIsNone(
                heartbeat._live_like_headers(2, 123, "foreign-session", "synthetic-csrf")
            )
