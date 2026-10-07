"""Delayed settlement and failed reads must not be confused with reward success."""

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asoul_support.runtime import task_day
from asoul_support.services.watch_progress import ProgressTracker, WatchProgressMonitor, parse_watch_task
from asoul_support.services.watch import _watch_duration
from desktop.engine import Engine
from desktop.storage import initialize, read_json
from desktop.worker import RoomStateRecorder
from desktop.view import TrayUI


def club(current=0, limit=10, **extra):
    return {"task_info": [{"jump_type": "watchLive", "title": "观看直播满15分钟",
                           "sub_title": f"每日上限 {current}/{limit}", "is_done": current >= limit}], **extra}


class WatchProgressTests(unittest.TestCase):
    def test_stall_requires_elapsed_time_and_accepted_heartbeats(self):
        tracker = ProgressTracker()
        tracker.observe(club(), "day", 0, 0)
        self.assertEqual(tracker.observe(club(), "day", 1799, 1800)["status"], "tracking")
        self.assertEqual(tracker.observe(club(), "day", 3600, 60)["status"], "tracking")
        self.assertEqual(tracker.observe(club(), "day", 3600, 1800)["status"], "stalled")

    def test_delayed_credit_clears_alarm_and_restarts_observation(self):
        tracker = ProgressTracker()
        tracker.observe(club(), "day", 0, 0)
        self.assertTrue(tracker.observe(club(), "day", 1800, 1800)["warning"])
        self.assertFalse(tracker.observe(club(1), "day", 1900, 1900)["warning"])
        self.assertEqual(tracker.observe(club(1), "day", 3600, 3600)["status"], "tracking")
        self.assertEqual(tracker.observe(club(1), "day", 3700, 3700)["status"], "stalled")

    def test_completed_and_capped_tasks_are_not_stalled(self):
        tracker = ProgressTracker()
        tracker.observe(club(), "day", 0, 0)
        self.assertEqual(tracker.observe(club(10), "day", 3600, 3600)["status"], "complete")
        self.assertEqual(tracker.observe(club(reach_free_intimacy_limit=True), "day", 3700, 3700)["status"], "limited")
        self.assertEqual(tracker.observe(club(), "day", 3800, 3800)["status"], "tracking")

    def test_cross_day_rollbacks_and_target_changes_reset_baseline(self):
        tracker = ProgressTracker()
        tracker.observe(club(2), "yesterday", 0, 0)
        self.assertEqual(tracker.observe(club(), "today", 3600, 3600)["status"], "tracking")
        tracker.observe(club(2), "today", 3700, 3700)
        self.assertEqual(tracker.observe(club(1), "today", 6000, 6000)["status"], "tracking")
        self.assertEqual(tracker.observe(club(1, 20), "today", 9000, 9000)["status"], "tracking")

    def test_failed_reads_are_unavailable_not_zero_progress(self):
        tracker = ProgressTracker()
        tracker.observe(club(4), "day", 0, 0)
        self.assertFalse(tracker.observe({}, "day", 600, 600)["warning"])
        result = tracker.observe({}, "day", 1800, 1800)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["progress"]["current"], 4)
        self.assertIn("无法核验", result["warning"])
        self.assertIsNone(parse_watch_task(club(11)))
        self.assertTrue(parse_watch_task({"task_info": [{"jump_type": "watchLive", "is_done": True}]})["done"])

    def test_alert_once_per_stall_and_again_after_real_recovery(self):
        gateway = Mock()
        gateway.get_fans_club_task_info.return_value = club()
        gateway.task_day.return_value = "day"
        clock = [0]
        monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", gateway)
        with patch("asoul_support.services.watch_progress.time.monotonic", side_effect=lambda: clock[0]):
            monitor.check()
            for stamp in (1800, 2400):
                clock[0] = monitor.accepted_seconds = stamp
                monitor.check()
            self.assertEqual(gateway._notify.call_count, 1)
            gateway.get_fans_club_task_info.return_value = {}
            clock[0] = 2500
            monitor.check(force=True)
            gateway.get_fans_club_task_info.return_value = club()
            clock[0] = 2600
            monitor.check(force=True)
            self.assertEqual(gateway._notify.call_count, 1)
            gateway.get_fans_club_task_info.return_value = club(1)
            clock[0] = monitor.accepted_seconds = 2700
            monitor.check(force=True)
            clock[0] = monitor.accepted_seconds = 4500
            monitor.check()
        self.assertEqual(gateway._notify.call_count, 2)
        self.assertTrue(any(e.args[0]["type"] == "watch_progress_recovered" for e in gateway._log.call_args_list))

    def test_watch_checks_run_with_all_reaction_switches_disabled(self):
        clock = [0]
        gateway = Mock(DANMAKU_RECHECK_INTERVAL=600)
        gateway.task_day.return_value = "day"
        gateway.get_fans_club_task_info.return_value = club()
        chain = SimpleNamespace(last_response_at=0, heartbeat_interval=60)
        def beat():
            clock[0] += 60
            chain.last_response_at = clock[0]
            return {"ok": True}
        chain.beat = beat
        monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", gateway)
        task = Mock()
        with patch("asoul_support.services.watch.time.monotonic", side_effect=lambda: clock[0]):
            monitor.check(force=True)
            result = _watch_duration(chain, task, "test", 1, "", 60, 31, False, False,
                                     "fake", "fake", gateway, progress_monitor=monitor)
        task.check.assert_not_called()
        self.assertEqual(result["watch_progress"]["status"], "stalled")
        self.assertEqual(gateway._notify.call_count, 1)
        self.assertGreaterEqual(gateway.get_fans_club_task_info.call_count, 4)

    def test_completed_room_does_not_poll_again_until_next_day(self):
        gateway = Mock()
        gateway.task_day.return_value = "day"
        gateway.get_fans_club_task_info.return_value = club(10)
        monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", gateway)
        with patch("asoul_support.services.watch_progress.time.monotonic", return_value=0):
            monitor.check()
        with patch("asoul_support.services.watch_progress.time.monotonic", return_value=3600):
            monitor.check()
            gateway.get_fans_club_task_info.assert_called_once()
            gateway.task_day.return_value = "next-day"
            gateway.get_fans_club_task_info.return_value = club()
            monitor.check()
        self.assertEqual(gateway.get_fans_club_task_info.call_count, 2)
        self.assertFalse(monitor.result["warning"])

    def test_cli_reports_pending_rewards_despite_successful_connection(self):
        from asoul_support import heartbeat
        result = heartbeat.format_output(
            [{"name": "test", "success": True, "minutes": 30, "beats_ok": 30, "beats_total": 30,
              "x25kn": True, "watch_progress": {"status": "stalled", "progress": {"current": 0, "limit": 10},
                                                 "warning": "奖励尚未确认"}}], [], {}, [])
        self.assertIn("看播任务：0/10（未完成）", result)
        self.assertIn("奖励尚未确认", result)


class DesktopRewardWarningTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"name": "test", "room": 1, "uid": 2}])
        self.engine = Engine(self.root, job=Mock())
        self.engine.workers[1] = Mock()
        self.engine.workers[1].poll.return_value = None
        self.now = time.time()
        self.engine.statuses = {"1": {"live_status": 1}}
        self.engine.status_times = {"1": self.now}
        self.engine.tasks = {"1": {"day": task_day(), "updated": self.now - 10, "tasks": club()["task_info"]}}
        self.recorder = RoomStateRecorder(self.root / "state/1.json", {"name": "test", "room": 1})
        self.recorder({"type": "x25kn_x_success", "interval": 60})
        self.event = {"type": "watch_progress", "status": "stalled", "day": task_day(),
                      "checked_at": self.now, "verified_at": self.now, "tasks": club()["task_info"],
                      "progress": {"current": 0, "limit": 10}, "warning": "看播进度长时间未增长",
                      "warning_since": self.now}
        self.recorder(self.event)

    def test_warning_reaches_snapshot_and_notifies_once(self):
        row = self.engine.snapshot()["rows"][0]
        self.assertEqual(row["watch_warning"], self.event["warning"])
        self.assertIn("watch_progress", read_json(self.recorder.path))
        ui = SimpleNamespace(tray=Mock())
        for _ in range(3):
            TrayUI._notify_watch_warnings(ui, {"rows": [row]})
        ui.tray.notify.assert_called_once()
        row["watch_progress"]["warning_since"] += 10
        TrayUI._notify_watch_warnings(ui, {"rows": [row]})
        self.assertEqual(ui.tray.notify.call_count, 2)

    def test_fresh_probe_credit_clears_warning_without_waiting_for_worker(self):
        self.engine.tasks["1"].update(updated=self.now + 1, tasks=club(1)["task_info"])
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
        self.engine.tasks["1"].update(tasks=club(10)["task_info"])
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])

    def test_old_session_cross_day_and_paused_rows_do_not_warn(self):
        self.recorder({**self.event, "day": "2000-01-01"})
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
        self.recorder(self.event)
        self.engine.paused = True
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
        self.engine.paused = False
        self.engine.workers.clear()
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
