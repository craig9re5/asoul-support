"""QR login state transitions and credential handling without real account IO."""

import unittest
from unittest.mock import Mock
from asoul_support.qr_login import QrLoginSession, PollResult, confirmed_credentials


class QrLoginTests(unittest.TestCase):
    def session(self, replies):
        clock = [0]
        request = Mock(
            side_effect=[
                (
                    {
                        "url": "https://passport.bilibili.com/h5-app/passport/login/scan?qrcode_key=synthetic",
                        "qrcode_key": "synthetic",
                    },
                    {},
                )
            ]
            + replies
        )
        session = QrLoginSession(request, lambda: clock[0])
        session.generate()
        return session, clock, request

    def test_wait_scan_confirm_extracts_only_login_pair(self):
        session, _, request = self.session(
            [
                ({"code": 86101}, {}),
                ({"code": 86090}, {}),
                (
                    {"code": 0},
                    {
                        "SESSDATA": "synthetic%2Csession",
                        "bili_jct": "synthetic-csrf",
                        "unrelated": "omit",
                    },
                ),
            ]
        )
        self.assertEqual(session.poll().state, "waiting")
        self.assertEqual(session.poll().state, "scanned")
        result = session.poll()
        self.assertEqual(
            result.credentials, {"SESSDATA": "synthetic%2Csession", "bili_jct": "synthetic-csrf"}
        )
        self.assertNotIn("synthetic", repr(result))
        self.assertFalse(session.key)
        self.assertEqual(session.poll().state, "confirmed")
        self.assertEqual(request.call_count, 4)

    def test_local_expiry_stops_network(self):
        session, clock, request = self.session([])
        clock[0] = 180
        self.assertEqual(session.poll().state, "expired")
        self.assertFalse(session.key)
        self.assertEqual(request.call_count, 1)

    def test_cancelled_session_does_not_poll(self):
        session, _, request = self.session([])
        session.cancel()
        self.assertEqual(session.poll().state, "cancelled")
        self.assertFalse(session.url)
        self.assertEqual(request.call_count, 1)

    def test_remote_expiry_clears_qr(self):
        session, _, _ = self.session([({"code": 86038}, {})])
        self.assertEqual(session.poll().state, "expired")
        self.assertFalse(session.key)

    def test_confirmed_without_credentials_fails(self):
        session, _, _ = self.session([({"code": 0, "url": "https://unexpected.invalid/"}, {})])
        with self.assertRaises(RuntimeError):
            session.poll()
        self.assertNotEqual(session.state, "confirmed")

    def test_cross_domain_url_decoded_once_without_following(self):
        value = confirmed_credentials(
            {
                "url": "https://passport.biligame.com/crossDomain?SESSDATA=synthetic%252Csession&bili_jct=synthetic-csrf"
            },
            {},
        )
        self.assertEqual(value["SESSDATA"], "synthetic%2Csession")

    def test_unexpected_qr_host_rejected(self):
        session = QrLoginSession(
            Mock(
                return_value=({"url": "https://unexpected.invalid/", "qrcode_key": "synthetic"}, {})
            )
        )
        with self.assertRaises(RuntimeError):
            session.generate()

    def test_unknown_state_is_not_a_success(self):
        session, _, _ = self.session([({"code": -999}, {})])
        with self.assertRaises(RuntimeError):
            session.poll()

    def test_current_account_host_supported(self):
        session = QrLoginSession(
            Mock(
                return_value=(
                    {
                        "url": "https://account.bilibili.com/h5/account-h5/auth/scan-web?key=synthetic",
                        "qrcode_key": "synthetic",
                    },
                    {},
                )
            )
        )
        self.assertTrue(session.generate().startswith("https://account.bilibili.com/"))
