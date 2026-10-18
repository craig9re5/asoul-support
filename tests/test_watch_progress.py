"""Delayed settlement and failed reads must not be confused with reward success."""

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asoul_support.runtime import task_day
from asoul_support.services.credit_clock import CreditClock
from asoul_support.services.watch_progress import ProgressTracker, WatchProgressMonitor, parse_watch_task
from asoul_support.services.watch import HeartbeatChain, _watch_duration, _watch_until_offline
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
        gateway._get_single_room_status.return_value = {"live_status": 1}
        chain = SimpleNamespace(last_response_at=0, heartbeat_interval=60, restart=Mock(return_value=True))
        def beat():
            clock[0] += 60
            chain.last_response_at = clock[0]
            return {"ok": True}
        chain.beat = beat
        monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", gateway)
        task = Mock()
        with patch("asoul_support.services.watch.time.monotonic", side_effect=lambda: clock[0]):
            monitor.check(force=True)
            result = _watch_duration(chain, task, "test", 1, "", 60, 32, False, False,
                                     "fake", "fake", gateway, progress_monitor=monitor)
        task.check.assert_not_called()
        self.assertEqual(result["watch_progress"]["status"], "stalled")
        self.assertEqual(gateway._notify.call_count, 1)
        self.assertGreaterEqual(gateway.get_fans_club_task_info.call_count, 4)
        chain.restart.assert_called_once()

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

    def test_malformed_task_payload_is_unavailable_without_crashing_watch(self):
        for tasks in (None, {}, "invalid", [{"jump_type": "watchLive", "sub_title": 123}]):
            with self.subTest(tasks=tasks):
                self.assertIsNone(parse_watch_task({"task_info": tasks}))
        info = club()
        info["task_info"][0]["title"] = 123
        self.assertEqual(parse_watch_task(info)["threshold"], 1800)

    def test_cli_reports_pending_rewards_despite_successful_connection(self):
        from asoul_support import heartbeat
        result = heartbeat.format_output(
            [{"name": "test", "success": True, "minutes": 30, "beats_ok": 30, "beats_total": 30,
              "x25kn": True, "watch_progress": {"status": "stalled", "progress": {"current": 0, "limit": 10},
                                                 "warning": "奖励尚未确认"}}], [], {}, [])
        self.assertIn("看播任务：0/10（未完成）", result)
        self.assertIn("奖励尚未确认", result)


class AccountRotationTests(unittest.TestCase):
    """One account settles one room per turn; a queued room is not a failure."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.now = 1000.0
        self.clock = CreditClock(Path(folder.name), "uid-1", clock=lambda: self.now)

    def test_only_a_progress_increase_counts_as_a_credit(self):
        first = self.clock.observe(1, "day", 4)
        self.assertIsNone(first["seconds_since_credit"])
        self.assertEqual(first["pass_overs"], 0)
        self.now += 60
        self.assertEqual(self.clock.observe(1, "day", 4)["credits"], 0)
        self.now += 60
        credited = self.clock.observe(1, "day", 5)
        self.assertEqual((credited["credits"], credited["pass_overs"]), (1, 0))
        self.assertEqual(credited["seconds_since_credit"], 0)
        self.now += 120
        self.assertEqual(self.clock.observe(2, "day", 0)["pass_overs"], 0)

    def test_turns_credited_elsewhere_become_pass_overs(self):
        self.clock.observe(1, "day", 0)
        self.clock.observe(2, "day", 0)
        self.now += 600
        self.clock.observe(2, "day", 1)
        self.now += 600
        self.clock.observe(3, "day", 0)
        self.now += 600
        self.clock.observe(3, "day", 1)
        self.now += 600
        quiet = self.clock.observe(1, "day", 0)
        self.assertEqual(quiet["credits"], 2)
        self.assertEqual(quiet["pass_overs"], 2)
        self.assertEqual(quiet["last_credit_room"], 3)

    def test_cross_day_and_rollback_rebase_without_counting(self):
        self.clock.observe(1, "day", 7)
        self.now += 600
        self.assertEqual(self.clock.observe(1, "day", 3)["credits"], 0)
        self.now += 600
        rollback = self.clock.observe(1, "day", 1)
        self.assertEqual((rollback["credits"], rollback["pass_overs"]), (0, 0))
        self.now += 600
        self.assertEqual(self.clock.observe(1, "next-day", 2)["credits"], 0)

    def test_account_view_defers_stall_and_suppresses_reconnect_while_rotating(self):
        tracker = ProgressTracker()
        tracker.observe(club(), "day", 0, 0, {"seconds_since_credit": 0, "pass_overs": 0})
        rotating = tracker.observe(club(), "day", 1800, 1800,
                                   {"seconds_since_credit": 300, "pass_overs": 1})
        self.assertEqual(rotating["status"], "tracking")
        self.assertFalse(rotating["warning"])
        quiet = tracker.observe(club(), "day", 3700, 3700,
                                {"seconds_since_credit": 3700, "pass_overs": 4})
        self.assertEqual(quiet["status"], "stalled")
        self.assertIn("整个账号同期也没有到账", quiet["warning"])
        gateway = Mock()
        gateway.task_day.return_value = "day"
        gateway.get_fans_club_task_info.return_value = club()
        gateway._get_single_room_status.return_value = {"live_status": 1}
        monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", gateway)
        monitor.result = {"status": "stalled", "progress": {"current": 0, "limit": 10},
                          "account": {"seconds_since_credit": 300, "pass_overs": 1}}
        chain = Mock(heartbeat_interval=60)
        chain.restart.return_value = True
        # The forced read keeps the same stalled result; only the account view changes.
        monitor.check = Mock()
        monitor.maybe_recover(chain)
        chain.restart.assert_not_called()
        monitor.result["account"]["pass_overs"] = 2
        monitor.maybe_recover(chain)
        chain.restart.assert_called_once()
        self.assertEqual(monitor.result["recovery"]["status"], "reconnected")

    def test_desktop_explains_rotation_without_a_warning(self):
        from desktop.snapshot import watch_observation
        watch = {"day": task_day(), "status": "tracking", "warning": "", "rotation": True,
                 "unchanged_minutes": 35, "checked_at": time.time(), "verified_at": time.time(),
                 "progress": {"current": 3, "limit": 10}}
        _, warning, note, _, _ = watch_observation(
            {"watch_progress": watch}, {}, True, False, time.time())
        self.assertFalse(warning)
        self.assertIn("收益轮转中", note)
        watch["unchanged_minutes"] = 5
        self.assertFalse(watch_observation({"watch_progress": watch}, {}, True, False,
                                           time.time())[2])


class RewardRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        self.addCleanup(patch.stopall)
        patch("asoul_support.services.watch_progress.time.monotonic", side_effect=lambda: self.clock).start()
        self.hold = patch("asoul_support.services.watch_progress.safety.status", return_value={"blocked": False}).start()
        self.gateway = Mock(HEARTBEAT_INTERVAL=60, DANMAKU_RECHECK_INTERVAL=600)
        self.gateway.task_day.return_value = "day"
        self.gateway.get_fans_club_task_info.return_value = club()
        self.gateway._get_single_room_status.return_value = {"live_status": 1}
        self.monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", self.gateway)
        self.chain = Mock(heartbeat_interval=60)
        self.chain.restart.return_value = True
        self.monitor.check(force=True)

    def observe(self, stamp, current=0, **extra):
        self.clock = self.monitor.accepted_seconds = stamp
        self.gateway.get_fans_club_task_info.return_value = club(current, **extra)
        self.monitor.check(force=True)

    def test_one_restart_and_warning_after_another_30_minutes_without_credit(self):
        self.observe(1799)
        self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_not_called()
        self.observe(1800)
        self.monitor.maybe_recover(self.chain)
        self.assertEqual(self.monitor.result["recovery"]["status"], "reconnected")
        self.assertIn("自动重建", self.monitor.result["warning"])
        for stamp in (2400, 3599, 3600, 4200):
            self.observe(stamp)
            self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_called_once()
        self.assertEqual(self.monitor.result["recovery"]["status"], "pending_rewards")
        self.assertIn("不继续重连", self.monitor.result["warning"])
        self.assertEqual(self.gateway._notify.call_count, 2)

    def test_force_read_finds_delayed_credit_so_restart_is_cancelled(self):
        self.observe(1800)
        self.gateway.get_fans_club_task_info.return_value = club(1)
        self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_not_called()
        self.assertEqual(self.monitor.result["status"], "tracking")

    def test_no_recovery_for_completed_capped_unavailable_offline_or_blocked(self):
        for payload in (club(10), club(reach_free_intimacy_limit=True), {}):
            self.monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", self.gateway)
            self.clock = 0
            self.gateway.get_fans_club_task_info.return_value = club()
            self.monitor.check(force=True)
            self.observe(1800)
            self.gateway.get_fans_club_task_info.return_value = payload
            self.monitor.maybe_recover(self.chain)
        self.monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", self.gateway)
        self.clock = 0
        self.gateway.get_fans_club_task_info.return_value = club()
        self.monitor.check(force=True)
        for live in ({"live_status": 0}, None):
            self.observe(self.clock + 1800)
            self.gateway._get_single_room_status.return_value = live
            self.monitor.maybe_recover(self.chain)
        self.observe(self.clock + 1800)
        self.hold.return_value = {"blocked": True}
        self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_not_called()

    def test_protection_triggered_by_confirmation_prevents_restart(self):
        self.observe(1800)
        self.hold.side_effect = [{"blocked": False}, {"blocked": True}]
        self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_not_called()

    def test_failed_restart_consumes_episode_and_does_not_crash(self):
        for outcome in (False, RuntimeError("fake failure")):
            with self.subTest(outcome=outcome):
                self.monitor = WatchProgressMonitor(1, 2, "test", "fake", "fake", self.gateway)
                self.clock = 0
                self.monitor.check(force=True)
                self.observe(1800)
                self.chain.restart.reset_mock()
                self.chain.restart.side_effect = [outcome]
                self.monitor.maybe_recover(self.chain)
                self.observe(2400)
                self.monitor.maybe_recover(self.chain)
                self.chain.restart.assert_called_once()
                self.assertEqual(self.monitor.result["recovery"]["status"], "failed")

    def test_real_credit_clears_warning_and_session_budget_limits_new_stalls(self):
        self.observe(1800)
        self.monitor.maybe_recover(self.chain)
        self.observe(2400, 1)
        self.assertFalse(self.monitor.result["warning"])
        self.observe(4200, 1)
        self.monitor.maybe_recover(self.chain)
        self.observe(4800, 2)
        self.observe(6600, 2)
        self.monitor.maybe_recover(self.chain)
        self.assertEqual(self.chain.restart.call_count, 2)
        self.assertIn("次数已达上限", self.monitor.result["warning"])

    def test_offline_loop_recovers_stall_without_replaying_reaction_tasks(self):
        self.observe(1740)
        self.monitor.next_check = 1800
        self.chain.beat.side_effect = lambda: self.advance_beat()
        self.gateway._get_single_room_status.side_effect = [
            {"live_status": 1}, {"live_status": 1}, {"live_status": 0}]
        task = Mock()
        result = _watch_until_offline(self.chain, task, "test", 1, "", 60, 0,
                                     False, False, "fake", "fake", self.gateway, self.monitor)
        self.chain.restart.assert_called_once()
        task.check.assert_not_called()
        self.assertEqual(result["stopped_reason"], "offline")

    def test_unknown_live_status_rechecks_at_most_every_10_minutes(self):
        self.observe(1800)
        self.gateway._get_single_room_status.side_effect = OSError("network")
        self.monitor.maybe_recover(self.chain)
        self.clock = 1860
        self.monitor.maybe_recover(self.chain)
        self.gateway._get_single_room_status.assert_called_once()
        self.chain.restart.assert_not_called()

    def test_new_day_does_not_reconnect_for_yesterdays_stall(self):
        self.observe(1800)
        self.gateway.task_day.return_value = "next-day"
        self.monitor.maybe_recover(self.chain)
        self.chain.restart.assert_not_called()
        self.assertEqual(self.monitor.result["status"], "tracking")

    def advance_beat(self):
        self.clock += 60
        return {"ok": True}

    def test_restart_updates_protocol_state_and_keeps_login_and_device(self):
        original = {"secret_key": "old", "secret_rule": [1], "timestamp": 100,
                    "heartbeat_interval": 60}
        chain = HeartbeatChain(1, 2, 3, 4, "device", "uuid", "fake", "csrf",
                               original, 60, self.gateway)
        chain.protocol_seq = 99
        self.gateway.x25kn_enter_room.return_value = {
            "secret_key": "new", "secret_rule": [2], "timestamp": 200, "heartbeat_interval": 90}
        self.assertTrue(chain.restart())
        self.assertEqual((chain.protocol_seq, chain.ets, chain.secret_key, chain.heartbeat_interval),
                         (0, 200, "new", 90))
        self.gateway.x25kn_enter_room.assert_called_once_with(1, 2, 3, 4, "device", "uuid", "fake", "csrf")

    def test_duration_end_does_not_trigger_useless_restart(self):
        self.observe(1740)
        self.monitor.next_check = 1800
        chain = SimpleNamespace(last_response_at=1740, heartbeat_interval=60,
                                beat=self.advance_beat, restart=Mock(return_value=True))
        _watch_duration(chain, Mock(), "test", 1, "", 60, 1, False, False,
                        "fake", "fake", self.gateway, self.monitor)
        chain.restart.assert_not_called()

    def test_malformed_restart_does_not_partially_replace_protocol_secrets(self):
        original = {"secret_key": "old", "secret_rule": [1], "timestamp": 100}
        chain = HeartbeatChain(1, 2, 3, 4, "device", "uuid", "fake", "csrf",
                               original, 60, self.gateway)
        self.observe(1800)
        self.gateway.x25kn_enter_room.return_value = {"secret_key": "new"}
        self.monitor.maybe_recover(chain)
        self.assertEqual((chain.secret_key, chain.secret_rule, chain.ets), ("old", [1], 100))
        self.assertEqual(self.monitor.result["recovery"]["status"], "failed")


class HeartbeatTimingTests(unittest.TestCase):
    """Daily tasks must never push the next X past the server's window."""

    def setUp(self):
        self.addCleanup(patch.stopall)
        self.clock = 1000.0
        patch("asoul_support.services.watch.time.monotonic",
              side_effect=lambda: self.clock).start()
        self.gateway = Mock(HEARTBEAT_INTERVAL=60, DANMAKU_WORK_BUDGET=90,
                            DANMAKU_RECHECK_INTERVAL=600, DANMAKU_DELAY=0)

    def chain(self, due_in):
        chain = Mock(last_response_at=self.clock - (60 - due_in), heartbeat_interval=60)
        chain.restart.return_value = True
        return chain

    def test_task_deadline_stops_before_the_next_beat(self):
        from asoul_support.services.watch import _task_deadline, HEARTBEAT_TASK_MARGIN
        # 50s until the next beat: only 50 - margin of work fits, not the 90s budget.
        self.assertEqual(_task_deadline(self.chain(50), 90), self.clock + 50 - HEARTBEAT_TASK_MARGIN)
        # 120s until the beat: the work budget is the binding limit.
        self.assertEqual(_task_deadline(self.chain(120), 90), self.clock + 90)
        # The session deadline still caps everything.
        self.assertEqual(_task_deadline(self.chain(120), 90, self.clock + 10), self.clock + 10)

    def test_work_is_skipped_when_the_due_beat_cannot_wait(self):
        from asoul_support.services.watch import _task_window_open
        self.assertTrue(_task_window_open(self.chain(60)))
        self.assertFalse(_task_window_open(self.chain(5)))

    def test_watch_loop_bounds_every_check_before_the_next_beat(self):
        from asoul_support.services.watch import _watch_until_offline, HEARTBEAT_TASK_MARGIN
        runner = Mock(day="day")
        runner.check.return_value = {"success": True}
        chain = self.chain(60)
        chain.beat.side_effect = lambda: {"ok": True}
        self.gateway._get_single_room_status.side_effect = [{"live_status": 1}, {"live_status": 0}]
        _watch_until_offline(chain, runner, "test", 1, "", 60, 0, True, False,
                             "fake", "fake", self.gateway)
        deadline = runner.check.call_args.kwargs["deadline"]
        # The only beat is due in 60s, so work must stop before it is sent.
        self.assertEqual(deadline, self.clock + 60 - HEARTBEAT_TASK_MARGIN)
        self.assertIsNone(runner.check.call_args.kwargs["like_batches"])

    def test_like_runs_one_batch_per_pass(self):
        from asoul_support.services.watch import _watch_until_offline
        runner = Mock(day="day")
        runner.check.return_value = {"success": True}
        chain = self.chain(60)
        chain.beat.side_effect = lambda: {"ok": True}
        self.gateway._get_single_room_status.side_effect = [{"live_status": 1}, {"live_status": 0}]
        _watch_until_offline(chain, runner, "test", 1, "", 60, 0, False, True,
                             "fake", "fake", self.gateway)
        self.assertEqual(runner.check.call_args.kwargs["like_batches"], 1)

    def test_cross_day_reenters_before_sending_x(self):
        self.gateway.task_day.return_value = "day"
        self.gateway.x25kn_enter_room.return_value = {
            "secret_key": "new", "secret_rule": [2], "timestamp": 200, "heartbeat_interval": 60}
        self.gateway.x25kn_heartbeat.return_value = {
            "secret_key": "new", "secret_rule": [2], "timestamp": 200, "heartbeat_interval": 60}
        original = {"secret_key": "old", "secret_rule": [1], "timestamp": 100}
        chain = HeartbeatChain(1, 2, 3, 4, "device", "uuid", "fake", "csrf",
                               original, 60, self.gateway)
        self.gateway.task_day.return_value = "next-day"
        chain.beat()
        self.gateway.x25kn_enter_room.assert_called_once()
        self.gateway.x25kn_heartbeat.assert_called_once()
        self.assertEqual(chain.ets, 200)
        # The same day sends X without another E.
        chain.beat()
        self.gateway.x25kn_enter_room.assert_called_once()
        self.assertEqual(self.gateway.x25kn_heartbeat.call_count, 2)


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

    def test_reconnect_pending_notice_and_post_reconnect_failure_notice_reach_gui(self):
        ui = SimpleNamespace(tray=Mock())
        for stamp, message, recovery_status in (
            (self.now, "已自动重建该房间心跳，正在等待服务端结算", "reconnected"),
            (self.now + 1, "重建心跳后又观察至少 30 分钟，仍未确认看播增长", "pending_rewards"),
        ):
            self.recorder({**self.event, "warning": message, "warning_since": stamp,
                           "recovery": {"status": recovery_status, "attempts": 1}})
            row = self.engine.snapshot()["rows"][0]
            self.assertEqual(row["watch_warning"], message)
            self.assertEqual(row["watch_progress"]["recovery"]["status"], recovery_status)
            for _ in range(2):
                TrayUI._notify_watch_warnings(ui, {"rows": [row]})
        self.assertEqual(ui.tray.notify.call_count, 2)

    def test_old_session_cross_day_and_paused_rows_do_not_warn(self):
        self.recorder({**self.event, "day": "2000-01-01"})
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
        self.recorder(self.event)
        self.engine.paused = True
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
        self.engine.paused = False
        self.engine.workers.clear()
        self.assertFalse(self.engine.snapshot()["rows"][0]["watch_warning"])
