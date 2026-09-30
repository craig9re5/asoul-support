import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import heartbeat
import daily_summary
import runtime
from desktop.storage import initialize, load_config, read_status
from desktop.engine import Engine
from desktop.ui import format_task_result


class IsolatedTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        auth = patch.object(heartbeat, "get_viewer_uid", return_value=123)
        auth.start()
        self.addCleanup(auth.stop)
        for name, value in (
            ("_TASK_STATE_DIR", self.root / "state/tasks"),
            ("_LOCK_DIR", self.root / "locks"),
            ("_LOG_FILE", self.root / "logs/activity.jsonl"),
            ("_COOKIE_PATHS", [self.root / "credentials.json"]),
        ):
            setting = patch.object(heartbeat, name, value)
            setting.start()
            self.addCleanup(setting.stop)


class RuntimeTests(IsolatedTests):
    def test_all_entry_points_share_paths_and_members(self):
        initialize(self.root, [{"name": "configured", "uid": 123, "room": 456}])
        program = """import json,sys
sys.path.insert(0, 'scripts')
import heartbeat, videos, dynamics, checkin, daily_summary, credentials
from desktop.storage import data_dir
print(json.dumps({'credentials': [str(m._COOKIE_PATHS[0]) for m in
    (heartbeat,videos,dynamics,checkin)], 'path': str(credentials.cookie_path()),
    'logs': [str(heartbeat._LOG_FILE), str(daily_summary._LOG_FILE)],
    'members': [m.load_members() for m in (heartbeat,videos,dynamics,checkin)],
    'root': str(data_dir())}))"""
        result = subprocess.run(
            [sys.executable, "-c", program],
            cwd=ROOT,
            env={**os.environ, "ASOUL_APP_DATA": str(self.root)},
            capture_output=True,
            text=True,
            check=True,
        )
        value = json.loads(result.stdout)
        self.assertEqual(set(value["credentials"]), {str(self.root / "credentials.json")})
        self.assertEqual(set(value["logs"]), {str(self.root / "logs/activity.jsonl")})
        self.assertTrue(all(m[0]["name"] == "configured" for m in value["members"]))

    def test_login_update_preserves_browser_context_only_for_same_session(self):
        path = self.root / "credentials.json"
        runtime.write_json(
            path,
            {
                "SESSDATA": "fake",
                "bili_jct": "fake",
                "LIVE_BUVID": "device",
                "live_like_cookie": "browser",
            },
        )
        runtime.save_login("fake", "fake", path)
        self.assertEqual(runtime.read_json(path)["LIVE_BUVID"], "device")
        runtime.save_login("new-fake", "new-fake", path)
        self.assertNotIn("LIVE_BUVID", runtime.read_json(path))
        self.assertNotIn("live_like_cookie", runtime.read_json(path))

    def test_parallel_updates_do_not_lose_settings(self):
        path = self.root / "settings.json"
        runtime.write_json(path, {"count": 0})

        def increment(_):
            runtime.update_json(path, lambda value: {"count": value["count"] + 1})

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(12)))
        self.assertEqual(runtime.read_json(path)["count"], 12)

    def test_room_lease_is_released_and_excludes_another_process(self):
        path = self.root / "room.watch.lock"
        program = "from runtime import FileLock; import sys; lock=FileLock(sys.argv[1]); print(int(lock.acquired)); lock.close()"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "scripts")}
        with runtime.FileLock(path) as lease:
            self.assertTrue(lease.acquired)
            result = subprocess.run(
                [sys.executable, "-c", program, str(path)],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), "0")
        with runtime.FileLock(path) as lease:
            self.assertTrue(lease.acquired)


class TaskTests(IsolatedTests):
    @patch("heartbeat.task_day", return_value="2026-09-30")
    @patch("heartbeat.check_login", return_value=(True, "test"))
    @patch("heartbeat.check_live_status", return_value={456: {"live_status": 1}})
    @patch(
        "heartbeat.get_my_medals",
        side_effect=[
            {123: {"today_intimacy": 12, "medal_id": 1, "medal_name": "test", "level": 1}},
            {123: {"today_intimacy": 0, "medal_id": 1, "medal_name": "test", "level": 1}},
        ],
    )
    @patch(
        "heartbeat.watch_room",
        return_value={
            "name": "test",
            "room": 456,
            "success": True,
            "minutes": 1,
            "beats_ok": 1,
            "beats_total": 1,
        },
    )
    @patch("heartbeat.wear_medal", return_value=True)
    @patch("heartbeat.time.sleep")
    def test_main_session_uses_same_id_and_cross_day_delta(
        self, _sleep, _wear, watch, _medals, _status, _auth, day
    ):
        def finish(*args, **kwargs):
            day.return_value = "2026-10-01"
            heartbeat._log({"type": "x25kn_x_success", "room_id": 456})
            return {
                "name": "test",
                "room": 456,
                "success": True,
                "minutes": 1,
                "beats_ok": 1,
                "beats_total": 1,
            }

        watch.side_effect = finish
        with (
            patch.object(sys, "argv", ["heartbeat", "--sessdata", "fake", "--bili-jct", "fake"]),
            patch.object(heartbeat, "MEMBERS", heartbeat.MEMBERS),
            patch.object(
                heartbeat, "load_members", return_value=[{"name": "test", "uid": 123, "room": 456}]
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(heartbeat.main(), 0)
        rows = [
            json.loads(line)
            for line in heartbeat._LOG_FILE.read_text(encoding="utf-8").splitlines()
        ]
        session = [r for r in rows if r.get("session_id")]
        self.assertEqual(len({r["session_id"] for r in session}), 1)
        self.assertEqual(session[-1]["type"], "watch_end")
        self.assertIsNone(session[-1]["intimacy_delta"])

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_disabling_revival_does_not_send_to_unlit_medal(self, info, send, _sleep):
        info.return_value = {
            "is_lighted": False,
            "task_info": [{"jump_type": "sendDanmu", "sub_title": "0/5", "is_done": False}],
        }
        result = heartbeat.send_medal_danmaku_tasks(456, 123, "fake", "fake", auto_revive=False)
        self.assertFalse(result["done"])
        send.assert_not_called()

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_revival_only_stops_after_lighting_without_daily_task(self, info, send, _sleep):
        info.side_effect = [
            {"is_lighted": False, "task_info": []},
            {"is_lighted": True, "task_info": []},
            {"is_lighted": True, "task_info": []},
        ]
        result = heartbeat.send_medal_danmaku_tasks(456, 123, "fake", "fake", auto_intimacy=False)
        self.assertTrue(result["done"])
        self.assertEqual(send.call_count, 10)
        self.assertEqual(result["intimacy_sent"], 0)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_intimacy_only_sends_remaining_count(self, info, send, _sleep):
        info.side_effect = [
            {
                "is_lighted": True,
                "task_info": [{"jump_type": "sendDanmu", "sub_title": "2/5", "is_done": False}],
            },
            {
                "is_lighted": True,
                "task_info": [{"jump_type": "sendDanmu", "sub_title": "5/5", "is_done": True}],
            },
        ]
        result = heartbeat.send_medal_danmaku_tasks(456, 123, "fake", "fake", auto_revive=False)
        self.assertTrue(result["done"])
        self.assertEqual(send.call_count, 3)
        self.assertEqual(result["light_sent"], 0)

    @patch("heartbeat.task_day", return_value="2026-09-30")
    @patch("heartbeat.send_medal_danmaku_tasks", return_value={"attempted": 5, "done": True})
    def test_restart_reconfirms_progress_and_new_day_resets_completion(self, send, day):
        runner = heartbeat.DailyTaskRunner(456, 123, "fake", "fake")
        runner.check()
        runner.check()
        self.assertEqual(send.call_count, 1)
        restarted = heartbeat.DailyTaskRunner(456, 123, "fake", "fake")
        restarted.check()
        self.assertEqual(send.call_count, 2)
        day.return_value = "2026-10-01"
        restarted.check()
        self.assertEqual(send.call_count, 3)
        self.assertEqual(runtime.read_json(runner.path)["day"], "2026-10-01")

    @patch("heartbeat.task_day", return_value="2026-09-30")
    @patch("heartbeat.send_medal_danmaku_tasks")
    @patch("heartbeat.DANMAKU_SESSION_ATTEMPT_LIMIT", 5)
    @patch("heartbeat.DANMAKU_ATTEMPTS_PER_CHECK", 3)
    def test_restart_cannot_reset_send_budget(self, send, day):
        send.side_effect = lambda *a, **k: {"done": False, "attempted": k["max_attempts"]}
        heartbeat.DailyTaskRunner(456, 123, "fake", "fake").check()
        heartbeat.DailyTaskRunner(456, 123, "fake", "fake").check()
        heartbeat.DailyTaskRunner(456, 123, "fake", "fake").check()
        self.assertEqual([c.kwargs["max_attempts"] for c in send.call_args_list], [3, 2, 0])
        day.return_value = "2026-10-01"
        heartbeat.DailyTaskRunner(456, 123, "fake", "fake").check()
        self.assertEqual(send.call_args.kwargs["max_attempts"], 3)

    @patch(
        "heartbeat.send_medal_danmaku_tasks",
        return_value={"done": False, "attempted": 0, "error": "弹幕失败"},
    )
    @patch("heartbeat.like_live_room", return_value={"success": False, "error": "点赞失败"})
    def test_manual_failure_is_reported_by_ui(self, _like, _danmaku):
        result = heartbeat.redo_member_tasks(456, 123, "fake", "fake")
        self.assertFalse(result["success"])
        message = format_task_result("test", result)
        self.assertIn("弹幕失败", message)
        self.assertIn("点赞失败", message)
        self.assertNotIn("已确认完成", message)

    def test_cross_day_delta_does_not_report_a_loss(self):
        result = heartbeat.intimacy_change(12, 0, "2026-09-30", "2026-10-01")
        self.assertIsNone(result["intimacy_delta"])
        self.assertIn("跨日", result["intimacy_note"])
        self.assertEqual(heartbeat.intimacy_change(12, 15, "day", "day")["intimacy_delta"], 3)

    def test_session_context_follows_all_events(self):
        token = runtime.EVENT_CONTEXT.set({"session_id": "session-test", "room_id": 456})
        try:
            heartbeat._log({"type": "watch_start"})
            heartbeat._log({"type": "x25kn_x_success"})
            heartbeat._log({"type": "watch_end"})
        finally:
            runtime.EVENT_CONTEXT.reset(token)
        rows = [
            json.loads(line)
            for line in heartbeat._LOG_FILE.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual({r["session_id"] for r in rows}, {"session-test"})


class EngineTests(IsolatedTests):
    def setUp(self):
        super().setUp()
        initialize(self.root, [{"name": "test", "uid": 123, "room": 456}])
        self.engine = Engine(self.root, job=Mock())
        self.addCleanup(self.engine.job.close)
        self.engine.next_check = float("inf")

    def receive(self, value):
        self.engine.probe_path = self.root / "probe.json"
        runtime.write_json(self.engine.probe_path, value)
        self.engine.probe = Mock()
        self.engine.probe.poll.return_value = 0
        with patch.object(self.engine, "spawn", return_value=Mock()) as spawn:
            self.engine.tick()
        return spawn

    def test_old_action_marker_cannot_disable_restarted_worker(self):
        runtime.write_json(self.root / "state/actions.json", {"456": 1})
        spawn = self.receive({"statuses": {"456": {"live_status": 1}}})
        self.assertEqual(spawn.call_args.args, ("--worker", "456"))

    def test_worker_ignores_old_skip_flag_and_separates_switches(self):
        from desktop import worker

        runtime.update_json(
            self.root / "settings.json",
            lambda c: {
                **c,
                "auto_revive": False,
                "auto_danmaku_intimacy": True,
                "auto_like": False,
                "live_likes": True,
            },
        )
        app = Mock()
        app.run_watch.return_value = 0
        with (
            patch.object(worker, "AppContext", return_value=app),
            patch.object(worker, "Mutex", return_value=Mock(acquired=True)),
            patch.object(sys, "argv", ["test"]),
        ):
            worker.watch(self.root, 456, skip_actions=True)
            self.assertEqual(sys.argv, ["test"])
            policy = app.run_watch.call_args.args[1]
            self.assertFalse(policy["auto_revive"])
            self.assertTrue(policy["auto_danmaku_intimacy"])
            self.assertFalse(policy["auto_like"])

    def test_explicit_switches_override_legacy_flags(self):
        runtime.write_json(
            self.root / "settings.json",
            {
                "auto_like": False,
                "live_likes": True,
                "auto_revive": False,
                "auto_danmaku_intimacy": True,
                "danmaku": False,
            },
        )
        config, _ = load_config(self.root)
        self.assertFalse(config["auto_like"])
        self.assertFalse(config["auto_revive"])
        self.assertTrue(config["auto_danmaku_intimacy"])
        self.assertNotIn("live_likes", config)

    def test_saving_policy_stops_worker_and_schedules_new_check(self):
        proc = Mock()
        proc.poll.return_value = None
        self.engine.workers[456] = proc
        runtime.update_json(self.root / "settings.json", lambda c: {**c, "auto_revive": False})
        self.engine.reload_settings()
        proc.terminate.assert_called_once()
        self.assertFalse(self.engine.workers)
        self.assertEqual(self.engine.next_check, 0)

    def test_credential_change_clears_account_and_cached_tasks(self):
        self.engine.account = "previous"
        self.engine.tasks = {"456": {"tasks": []}}
        runtime.save_login("fake", "fake", self.root / "credentials.json")
        self.engine.reload_settings()
        self.assertEqual(self.engine.account, "")
        self.assertEqual(self.engine.tasks, {})

    def test_failed_query_is_not_offline_and_keeps_existing_worker(self):
        proc = Mock()
        proc.poll.return_value = None
        self.engine.workers[456] = proc
        self.receive({"error": "网络请求失败"})
        row = self.engine.snapshot()["rows"][0]
        self.assertIsNone(row["live_status"])
        self.assertEqual(row["status_error"], "网络请求失败")
        proc.terminate.assert_not_called()

    def test_stale_query_is_not_live_or_offline(self):
        self.engine.statuses = {"456": {"live_status": 1}}
        self.engine.status_times = {"456": time.time() - 7200}
        row = self.engine.snapshot()["rows"][0]
        self.assertTrue(row["status_stale"])
        self.assertIsNone(row["live_status"])
        self.assertEqual(row["phase"], "状态已过期")

    def test_saved_status_cannot_claim_active_after_expiration(self):
        runtime.write_json(
            self.root / "status.json",
            {
                "pid": os.getpid(),
                "updated": time.time() - 60,
                "rows": [{"active": True, "live_status": 1}],
            },
        )
        state = read_status(self.root)
        self.assertFalse(state["running"])
        self.assertFalse(state["rows"][0]["active"])
        self.assertIsNone(state["rows"][0]["live_status"])


class SummaryTests(unittest.TestCase):
    def test_missing_data_cannot_claim_nobody_was_live(self):
        result = daily_summary.build_summary([])
        self.assertIn("无法判断", result)
        self.assertNotIn("无人开播", result)

    def test_session_ids_prevent_reusing_an_end_record(self):
        rows = [
            {"type": "watch_start", "member": "A", "session_id": "old", "ts": 1},
            {"type": "watch_start", "member": "A", "session_id": "new", "ts": 2},
            {"type": "watch_end", "member": "A", "session_id": "new", "ts": 3, "minutes": 10},
        ]
        pairs = daily_summary.pair_sessions(rows)
        self.assertEqual(sum(s["end"] is not None for s in pairs), 1)

    def test_legacy_end_record_is_consumed_once(self):
        rows = [
            {"type": "watch_start", "member": "A", "ts": 1},
            {"type": "watch_start", "member": "A", "ts": 2},
            {"type": "watch_end", "member": "A", "ts": 3, "minutes": 10},
        ]
        pairs = daily_summary.pair_sessions(rows)
        self.assertEqual(sum(s["end"] is not None for s in pairs), 1)
        self.assertEqual(next(s["start"]["ts"] for s in pairs if s["end"]), 2)

    def test_interruption_does_not_replace_a_real_end(self):
        rows = [
            {"type": "watch_start", "session_id": "a", "ts": 1},
            {"type": "watch_end", "session_id": "a", "ts": 2, "minutes": 10},
            {"type": "watch_interrupted", "session_id": "a", "ts": 3, "minutes": 12},
        ]
        self.assertEqual(daily_summary.pair_sessions(rows)[0]["end"]["minutes"], 10)


if __name__ == "__main__":
    unittest.main()
