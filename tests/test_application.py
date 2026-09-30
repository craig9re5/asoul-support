"""Offline contracts for the shared implementation and desktop boundary."""

import json
import io
from contextlib import redirect_stdout, redirect_stderr
import sys
import tempfile
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asoul_support import heartbeat, checkin, videos, dynamics
from asoul_support.application import AppContext
from asoul_support.context import CURRENT
from asoul_support.http import ApiError, get_json
from asoul_support.runtime import write_json
from asoul_support.services.content import video_window
from desktop.dispatch import Dispatcher


class ApplicationTests(unittest.TestCase):
    def test_fixed_watch_honors_tasks_and_changed_server_interval(self):
        from asoul_support.services.watch import _watch_duration

        clock = [0.0]
        chain = SimpleNamespace(last_response_at=0.0, heartbeat_interval=60)

        def beat():
            clock[0] = chain.last_response_at + chain.heartbeat_interval
            chain.last_response_at = clock[0]
            chain.heartbeat_interval = 30
            return {"ok": True}

        chain.beat = beat
        task = SimpleNamespace(check=Mock(return_value={"success": True}), day="day")
        gateway = Mock(DANMAKU_RECHECK_INTERVAL=600)
        gateway.task_day.return_value = "day"
        with patch("asoul_support.services.watch.time.monotonic", side_effect=lambda: clock[0]):
            result = _watch_duration(
                chain, task, "test", 2, "", 60, 2, True, False, "fake", "fake", gateway
            )
        task.check.assert_called_once()
        self.assertEqual(result["beats_total"], 3)
        self.assertEqual(result["minutes"], 2)
        self.assertTrue(result["success"])

    def test_contexts_isolate_credentials_events_and_restore_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            roots = [Path(folder) / str(index) for index in range(2)]
            observers = [[], []]
            apps = [AppContext(root, observer=observers[i].append) for i, root in enumerate(roots)]
            before = (heartbeat._COOKIE_PATHS, heartbeat._LOG_FILE, heartbeat._log)
            for i, root in enumerate(roots):
                write_json(root / "credentials.json", {"SESSDATA": f"fake-{i}", "bili_jct": "fake"})
            barrier = threading.Barrier(2)

            def run(index):
                barrier.wait()
                app = apps[index]
                value = app.call("load_cookies")
                app.call("_log", {"type": "test", "index": index})
                self.assertIsNone(CURRENT.get())
                return value["SESSDATA"]

            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(run, range(2))), ["fake-0", "fake-1"])
            for i, root in enumerate(roots):
                row = json.loads((root / "logs/activity.jsonl").read_text(encoding="utf-8"))
                self.assertEqual(row["index"], i)
                self.assertEqual(observers[i][0]["index"], i)
            with self.assertRaises(AttributeError):
                apps[0].call("missing")
            self.assertIsNone(CURRENT.get())
            self.assertEqual(before, (heartbeat._COOKIE_PATHS, heartbeat._LOG_FILE, heartbeat._log))

    def test_desktop_policy_calls_same_command_without_changing_argv(self):
        gateway = Mock()
        gateway.main.return_value = 0
        app = AppContext("unused", gateway=gateway)
        argv = sys.argv[:]
        app.run_watch(
            {"name": "test"},
            {"auto_revive": False, "auto_danmaku_intimacy": True, "auto_like": True},
        )
        self.assertEqual(
            gateway.main.call_args.args[0],
            ["--until-offline", "--members", "test", "--no-revive", "--live-likes"],
        )
        self.assertEqual(sys.argv, argv)

    def test_member_updates_validate_and_keep_parallel_additions(self):
        with tempfile.TemporaryDirectory() as folder:
            app = AppContext(folder)
            additions = [{"name": f"member-{i}", "uid": i + 1, "room": i + 10} for i in range(12)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda member: app.add_members([member]), additions))
            saved = json.loads((Path(folder) / "members.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 12)
            with self.assertRaises(ValueError):
                app.add_members([{"name": "member-0", "uid": 100, "room": 200}])
            self.assertEqual(len(app.remove_member(10)), 11)

    @patch("asoul_support.heartbeat._post_form", return_value={"code": 0})
    def test_pacing_uses_explicit_app_directory(self, post):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertTrue(AppContext(root).call("_send_danmaku", 1, "test", "fake", "fake"))
            self.assertTrue((root / "locks/danmaku-send.lock").exists())

    @patch("asoul_support.heartbeat.DailyTaskRunner")
    @patch("asoul_support.checkin.send_danmaku")
    def test_automatic_checkin_uses_shared_verified_task_runner(self, send, runner):
        runner.return_value.check.return_value = {
            "success": False,
            "danmaku": {
                "total_sent": 2,
                "attempted": 3,
                "light_done": True,
                "error": "任务尚未完成",
            },
        }
        result = checkin.batch_checkin(
            [{"name": "test", "uid": 1, "room": 2}],
            ["test"],
            "fake",
            "fake",
            count=None,
            auto_medal=False,
        )
        send.assert_not_called()
        self.assertFalse(result[0]["success"])
        self.assertEqual(result[0]["sent_ok"], 2)
        self.assertEqual(result[0]["sent_fail"], 1)


class ApiContracts(unittest.TestCase):
    @patch(
        "asoul_support.videos.load_members", return_value=[{"name": "test", "uid": 1, "room": 2}]
    )
    @patch(
        "asoul_support.videos.fetch_user_videos",
        return_value=[{"aid": 1, "created": 2_000_000_000}],
    )
    @patch(
        "asoul_support.videos.process_member_videos",
        return_value=[{"actions": [{"success": False}]}],
    )
    def test_video_action_failure_returns_nonzero(self, process, fetch, members):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = videos.main(
                ["--days", "7", "--json", "--sessdata", "fake", "--bili-jct", "fake"]
            )
        self.assertEqual(result, 1)

    @patch(
        "asoul_support.videos.load_members", return_value=[{"name": "test", "uid": 1, "room": 2}]
    )
    @patch("asoul_support.videos._get_default_fav", return_value=None)
    @patch("asoul_support.videos.fetch_user_videos")
    def test_unavailable_requested_favorites_abort_before_actions(self, fetch, favorite, members):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = videos.main(
                ["--days", "7", "--fav", "--sessdata", "fake", "--bili-jct", "fake"]
            )
        self.assertEqual(result, 1)
        fetch.assert_not_called()

    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError("SESSDATA=private"))
    def test_transport_error_is_explicit_and_does_not_echo_credentials(self, _open):
        result = get_json("https://example.test", {})
        self.assertEqual(result["error_kind"], "network")
        self.assertNotIn("private", json.dumps(result))

    @patch("asoul_support.heartbeat._get_json")
    def test_medal_page_failure_never_returns_partial_success(self, get):
        get.side_effect = [
            {
                "code": 0,
                "data": {
                    "list": [{"medal": {"target_id": 1, "medal_id": 2}}],
                    "page_info": {"total_page": 2},
                },
            },
            {"code": -101, "message": "未登录"},
        ]
        with self.assertRaises(ApiError):
            heartbeat.get_my_medals("fake", "fake")

    @patch("asoul_support.heartbeat._get_json", return_value={"code": 0, "data": {}})
    def test_missing_live_status_is_unknown(self, get):
        self.assertIsNone(heartbeat._get_room_info(1, "fake", "fake"))

    @patch("asoul_support.dynamics._post", return_value={"code": 500, "message": "failed"})
    @patch("asoul_support.dynamics._make_headers", return_value={})
    def test_dynamic_500_is_failure(self, headers, post):
        self.assertFalse(dynamics.like_dynamic("1", "fake", "fake")["success"])

    @patch("asoul_support.videos.get_mixin_key", return_value="fake")
    @patch("asoul_support.videos._get", return_value={"code": -1, "message": "网络请求失败"})
    def test_video_failure_is_not_no_new_videos(self, get, key):
        with self.assertRaises(ApiError):
            videos.fetch_user_videos(1, "fake", "fake")

    def test_video_window_paginates_beyond_first_page(self):
        now = 2_000_000_000
        page = [{"aid": i, "created": now} for i in range(30)]
        gateway = Mock()
        gateway.fetch_user_videos.side_effect = [page, [{"aid": 31, "created": now}]]
        with patch("asoul_support.services.content.time.time", return_value=now):
            result = video_window(1, SimpleNamespace(month=None, days=7), "fake", "fake", gateway)
        self.assertEqual(len(result), 31)
        self.assertEqual(gateway.fetch_user_videos.call_args.kwargs["page"], 2)

    @patch("asoul_support.dynamics._make_headers", return_value={})
    @patch("asoul_support.dynamics._get")
    def test_incomplete_dynamic_window_is_reported(self, get, headers):
        get.return_value = {
            "code": 0,
            "data": {"items": [{"id_str": "1", "modules": {}}], "offset": "next", "has_more": True},
        }
        with self.assertRaisesRegex(RuntimeError, "上限"):
            dynamics.fetch_user_dynamics(1, "fake", "fake", max_pages=1, require_complete=True)

    def test_month_validation_is_shared(self):
        for module in (videos, dynamics):
            with self.assertRaises(ValueError):
                module.parse_month("2026-13")


class DispatchTests(unittest.TestCase):
    def test_cancelled_background_task_does_not_report_error(self):
        from concurrent.futures import Future

        dispatcher = Dispatcher(Mock())
        future = Future()
        future.cancel()
        try:
            dispatcher._report(future)
            self.assertTrue(dispatcher.callbacks.empty())
        finally:
            dispatcher.close()

    def test_worker_posts_without_calling_tk_and_main_thread_drains(self):
        root = Mock()
        dispatcher = Dispatcher(root)
        seen = []
        owner = threading.get_ident()
        try:
            dispatcher.submit(
                lambda: dispatcher.post(lambda: seen.append(threading.get_ident()))
            ).result(2)
            self.assertEqual(seen, [])
            self.assertEqual(root.after.call_count, 1)
            dispatcher.drain()
            self.assertEqual(seen, [owner])
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(RuntimeError):
                    pool.submit(dispatcher.drain).result(2)
        finally:
            dispatcher.close()

    def test_late_callback_after_close_is_discarded(self):
        dispatcher = Dispatcher(Mock())
        dispatcher.close()
        dispatcher.post(lambda: self.fail("must not run"))
        self.assertTrue(dispatcher.callbacks.empty())


if __name__ == "__main__":
    unittest.main()
