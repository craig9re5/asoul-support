"""Account protection, uncertainty, vault migration and cross-process contracts."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asoul_support import safety, http, heartbeat, secret_store
from asoul_support.context import RuntimeContext, use_context
from asoul_support.runtime import (
    write_json,
    read_json,
    save_login,
    session_fingerprint,
    task_day,
    append_event,
)
from asoul_support.redaction import SafeStream, SafeFormatter, register_secrets, redact
from asoul_support.session_headers import session_headers
from desktop.engine import Engine
from desktop.storage import initialize

SESSION = "synthetic-security-session-A"
CSRF = "synthetic-security-csrf-A"
HEADERS = {"Cookie": f"SESSDATA={SESSION}; bili_jct={CSRF}"}
URL = "https://api.live.bilibili.com/msg/send"


class SecurityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        scope = use_context(RuntimeContext(self.root))
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        safety.bind_account(SESSION, 123)

    def test_uncertain_write_is_not_retried_and_blocks_another_room(self):
        with patch.object(
            http, "_once", return_value={"code": -1, "error_kind": "network"}
        ) as send:
            result = http.post_form(URL, {"roomid": "1"}, HEADERS)
            blocked = http.post_form(URL, {"roomid": "2"}, HEADERS)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["error_kind"], "network")
        self.assertEqual(blocked["error_kind"], "safety")
        self.assertEqual(safety.status(SESSION)["kind"], "uncertain")
        with patch.object(http, "_once", return_value={"code": 0}) as read:
            self.assertEqual(
                http.get_json("https://api.live.bilibili.com/progress", HEADERS)["code"], 0
            )
        read.assert_called_once()

    def test_http_500_write_has_unknown_outcome(self):
        with patch.object(http, "_once", return_value={"code": 500, "error_kind": "http"}):
            http.post_form(URL, {"roomid": "1"}, HEADERS)
        self.assertEqual(safety.status(SESSION)["kind"], "uncertain")

    def test_reads_have_bounded_backoff_then_account_cooldown(self):
        with (
            patch.object(http, "_once", return_value={"code": -1, "error_kind": "network"}) as read,
            patch.object(http.time, "sleep") as sleep,
        ):
            http.get_json("https://api.bilibili.com/read", HEADERS)
        self.assertEqual(read.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])
        self.assertEqual(safety.status(SESSION)["kind"], "network")

    def test_rate_obeys_retry_after_and_cannot_be_resumed_early(self):
        with patch.object(
            http, "_once", return_value={"code": 429, "error_kind": "http", "retry_after": 600}
        ):
            http.get_json("https://api.bilibili.com/read", HEADERS)
        hold = safety.status(SESSION)
        self.assertGreaterEqual(hold["until"] - hold["since"], 600)
        self.assertFalse(safety.resume(SESSION, confirmed=True)[0])
        with patch.object(safety.time, "time", return_value=hold["until"] + 1):
            self.assertFalse(safety.status(SESSION)["blocked"])

    def test_352_requires_review_and_reauthentication_does_not_clear_it(self):
        safety.observe(SESSION, URL, {"code": -352})
        safety.bind_account(SESSION, 123)
        self.assertEqual(safety.status(SESSION)["kind"], "review")
        self.assertFalse(safety.resume(SESSION)[0])
        self.assertTrue(safety.resume(SESSION, confirmed=True)[0])

    def test_auth_expiry_clears_only_after_successful_authentication(self):
        safety.observe(SESSION, URL, {"code": -101})
        self.assertFalse(safety.resume(SESSION, confirmed=True)[0])
        safety.observe(SESSION, http.NAV_URL, {"code": 0, "data": {"isLogin": True, "mid": 123}})
        self.assertFalse(safety.status(SESSION)["blocked"])

    def test_new_qr_session_same_uid_keeps_hold_and_budget(self):
        op = {"kind": "danmaku", "room": "1"}
        self.assertIsNone(safety.reserve(SESSION, op))
        safety.observe(SESSION, URL, {"code": 403})
        new = "synthetic-security-session-B"
        safety.bind_account(new, 123)
        self.assertEqual(safety.identity(new), safety.identity(SESSION))
        self.assertTrue(safety.status(new)["blocked"])
        counts = read_json(self.root / "state/safety/uid-123.json")["counts"]
        self.assertEqual(counts[f"{task_day()}:1:danmaku"], 1)

    def test_legacy_budget_migrates_once_without_session_reset(self):
        legacy = "synthetic-legacy-session"
        old = session_fingerprint(legacy)
        path = self.root / "state/tasks" / f"{old}-1.json"
        write_json(path, {"room": 1, "day": task_day(), "attempted": 35, "like_attempted": 2})
        safety.bind_account(legacy, 321)
        safety.bind_account(legacy, 321)
        current = read_json(self.root / "state/tasks/uid-321-1.json")
        self.assertEqual(current["attempted"], 35)
        self.assertFalse(path.exists())
        denied = safety.reserve(legacy, {"kind": "danmaku", "room": "1"})
        self.assertEqual(denied["error_kind"], "safety")

    def test_parallel_workers_share_request_budget(self):
        op = {"kind": "danmaku", "room": "1"}

        def reserve(_):
            with use_context(RuntimeContext(self.root)):
                return safety.reserve(SESSION, op)

        with patch.object(safety, "DANMAKU_SESSION_ATTEMPT_LIMIT", 3):
            with ThreadPoolExecutor(max_workers=4) as workers:
                results = list(workers.map(reserve, range(8)))
        self.assertEqual(sum(r is None for r in results), 3)

    def test_separate_processes_share_request_budget(self):
        program = (
            "from asoul_support import safety; import sys; "
            "safety.DANMAKU_SESSION_ATTEMPT_LIMIT=1; "
            "print(int(safety.reserve(sys.argv[1], {'kind':'danmaku','room':'2'}) is None))"
        )
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", program, SESSION],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "ASOUL_APP_DATA": str(self.root)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [p.communicate(timeout=15) for p in processes]
        self.assertTrue(all(p.returncode == 0 for p in processes), outputs)
        self.assertEqual(sum(int(out.strip()) for out, _ in outputs), 1)

    def test_unknown_identity_must_authenticate_before_write(self):
        headers = {"Cookie": "SESSDATA=unverified; bili_jct=synthetic"}
        with patch.object(http, "_once", return_value={"code": -101}) as transport:
            result = http.post_form(URL, {"roomid": "1"}, headers)
        self.assertEqual(result["code"], -101)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(transport.call_args.args[0], http.NAV_URL)

    def test_fixed_count_checkin_uses_daily_runner(self):
        from asoul_support import checkin

        with patch.object(heartbeat, "DailyTaskRunner") as runner:
            runner.return_value.check.return_value = {"success": True, "danmaku": {"done": True}}
            checkin.batch_checkin(
                [{"room": 1, "uid": 2, "name": "test"}],
                ["hello"],
                SESSION,
                CSRF,
                count=1000,
                auto_medal=False,
            )
        self.assertEqual(runner.call_args.kwargs["requested_count"], 1000)

    def test_engine_stops_all_workers_and_reports_protection(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        safety.observe(SESSION, URL, {"code": -352})
        with patch.object(engine, "spawn") as spawn:
            engine.tick()
        process.terminate.assert_called_once()
        spawn.assert_not_called()
        snapshot = engine.snapshot()
        self.assertTrue(snapshot["safety"]["blocked"])
        self.assertEqual(snapshot["rows"][0]["phase"], "账号保护暂停")
        self.assertFalse(snapshot["rows"][0]["active"])

    def test_reencrypting_same_credentials_does_not_restart_workers(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine.reload_settings()
        process.terminate.assert_not_called()

    def test_engine_allows_bounded_reconciliation_then_stops_uncertain_worker(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        safety.hold_account(SESSION, "uncertain", "结果未知")
        engine.tick()
        process.terminate.assert_not_called()
        hold = safety.status(SESSION)
        with patch.object(safety.time, "time", return_value=hold["since"] + 21):
            engine.tick()
        process.terminate.assert_called_once()

    def test_cannot_send_auth_to_other_host_or_redirect(self):
        with patch.object(http, "_once") as send:
            result = http.post_form("https://example.test/send", {}, HEADERS)
        send.assert_not_called()
        self.assertEqual(result["error_kind"], "safety")
        request = urllib.request.Request(URL, headers=HEADERS)
        with self.assertRaises(urllib.error.HTTPError):
            http.SameOriginRedirect().redirect_request(
                request, None, 302, "", {}, "https://example.test/"
            )

    def test_existing_heartbeat_and_dynamic_hosts_remain_available(self):
        with patch.object(http, "_once", return_value={"code": 0}) as send:
            for url in (
                heartbeat._X25KN_E_URL,
                heartbeat._X25KN_X_URL,
                "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb",
            ):
                self.assertEqual(http.post_form(url, {}, HEADERS)["code"], 0)
        self.assertEqual(send.call_count, 3)

    def test_uncertain_like_queries_progress_without_repeating_batch(self):
        from asoul_support.services.likes import like_live_room

        gateway = Mock(LIVE_LIKE_PROGRESS_DELAY=3)
        gateway.get_viewer_uid.return_value = 123
        gateway._live_like_headers.return_value = HEADERS
        gateway.get_live_like_progress.side_effect = [
            {"current": 0, "limit": 2, "per_round": 30, "done": False},
            {"current": 1, "limit": 2, "per_round": 30, "done": False},
        ]

        def unknown(*args, **kwargs):
            safety.hold_account(SESSION, "uncertain", "操作结果未知")
            return {"success": False, "code": -1, "message": "timeout"}

        gateway.report_live_likes.side_effect = unknown
        with patch("asoul_support.services.likes.time.sleep"):
            result = like_live_room(1, 2, SESSION, CSRF, _gateway=gateway)
        self.assertEqual(result["progress"], "1/2")
        self.assertTrue(result["needs_confirmation"])
        gateway.report_live_likes.assert_called_once()
        self.assertTrue(safety.status(SESSION)["blocked"])

    def test_logout_clears_session_aliases_but_preserves_uid_hold_and_budget(self):
        save_login(SESSION, CSRF, self.root / "credentials.json")
        safety.reserve(SESSION, {"kind": "danmaku", "room": "1"})
        safety.observe(SESSION, URL, {"code": -352})
        save_login("", "", self.root / "credentials.json")
        self.assertEqual(read_json(self.root / "state/account-bindings.json"), {})
        safety.bind_account("synthetic-new-session", 123)
        self.assertTrue(safety.status("synthetic-new-session")["blocked"])
        self.assertEqual(
            read_json(self.root / "state/safety/uid-123.json")["counts"][f"{task_day()}:1:danmaku"],
            1,
        )


class VaultTests(unittest.TestCase):
    def test_confirmed_qr_can_replace_unreadable_vault(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            save_login(SESSION, CSRF, path)
            context = {
                "cookies": {
                    "SESSDATA": "synthetic-qr-new-session",
                    "bili_jct": "synthetic-replacement-csrf",
                },
                "user_agent": "QR UA",
            }
            with patch("asoul_support.runtime.unseal", side_effect=RuntimeError("unreadable")):
                save_login(
                    context["cookies"]["SESSDATA"],
                    context["cookies"]["bili_jct"],
                    path,
                    context=context,
                )
            self.assertEqual(read_json(path)["SESSDATA"], "synthetic-qr-new-session")

    def test_legacy_plaintext_removed_only_after_verified_protection(self):
        from asoul_support.runtime import protect_credentials

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / ".asoul-support-data/.cookies.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"SESSDATA": SESSION, "bili_jct": CSRF}))
            result = protect_credentials(root / "new", legacy)
            self.assertTrue(result["protected"])
            self.assertTrue(result["legacy_removed"])
            self.assertFalse(legacy.exists())
            self.assertEqual(read_json(root / "new/credentials.json")["SESSDATA"], SESSION)

    def test_saved_credentials_are_protected_and_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            save_login(SESSION, CSRF, path)
            self.assertTrue(secret_store.is_envelope(json.loads(path.read_text())))
            self.assertNotIn(SESSION, path.read_text())
            self.assertEqual(read_json(path)["SESSDATA"], SESSION)
            save_login("", "", path)
            self.assertEqual(read_json(path), {})

    def test_plaintext_migration_is_atomic_and_does_not_make_plaintext_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(json.dumps({"SESSDATA": SESSION, "bili_jct": CSRF}))
            with patch("asoul_support.runtime.seal", side_effect=RuntimeError("vault unavailable")):
                with self.assertRaises(RuntimeError):
                    read_json(path)
            self.assertIn(SESSION, path.read_text())
            self.assertEqual(read_json(path)["SESSDATA"], SESSION)
            self.assertNotIn(SESSION, path.read_text())
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "real Windows user DPAPI")
    def test_dpapi_tampering_fails_closed(self):
        envelope = secret_store.seal({"SESSDATA": SESSION})
        envelope["payload"] = "invalid!"
        with self.assertRaises(RuntimeError) as error:
            secret_store.unseal(envelope)
        self.assertNotIn(SESSION, str(error.exception))

    def test_unavailable_os_vault_never_writes_plaintext(self):
        with (
            patch.object(secret_store.os, "name", "posix"),
            patch.object(secret_store, "_keyring", side_effect=RuntimeError("unavailable")),
        ):
            with self.assertRaises(RuntimeError):
                secret_store.seal({"SESSDATA": SESSION})

    def test_redacts_nested_events_urls_tracebacks_and_split_stream_writes(self):
        register_secrets({"SESSDATA": SESSION, "bili_jct": CSRF})
        value = redact(
            {
                "Cookie": f"SESSDATA={SESSION}",
                "message": f"https://api.bilibili.com/?csrf={CSRF}&SESSDATA={SESSION}",
            }
        )
        self.assertNotIn(SESSION, json.dumps(value))
        self.assertNotIn(CSRF, json.dumps(value))
        stream = io.StringIO()
        safe = SafeStream(stream)
        safe.write(SESSION[:10])
        safe.write(SESSION[10:] + "\n")
        self.assertNotIn(SESSION, stream.getvalue())
        import logging

        record = logging.LogRecord("test", 40, "", 1, SESSION, (), None)
        self.assertNotIn(SESSION, SafeFormatter().format(record))

    def test_all_modules_reuse_qr_session_and_user_agent(self):
        from asoul_support import videos, dynamics

        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            context = {
                "cookies": {
                    "SESSDATA": SESSION,
                    "bili_jct": CSRF,
                    "DedeUserID": "123",
                    "buvid3": "synthetic-device",
                },
                "user_agent": "QR UA",
            }
            save_login(SESSION, CSRF, Path(folder) / "credentials.json", context=context)
            for module in (heartbeat, videos, dynamics):
                headers = module._make_headers(SESSION, CSRF)
                self.assertEqual(headers["User-Agent"], "QR UA")
                self.assertIn("buvid3=synthetic-device", headers["Cookie"])
            with patch.object(heartbeat, "_post_form", return_value={"code": 0}) as post:
                heartbeat._x25kn_post(URL, {"ua": "old"}, SESSION, CSRF, URL)
            self.assertEqual(post.call_args.args[1]["ua"], "QR UA")
