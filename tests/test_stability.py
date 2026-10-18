"""Fault recovery contracts, isolated from the real account and desktop."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from desktop.engine import Engine
from desktop.storage import initialize, read_json, write_json
from desktop.view import TrayUI
from desktop.health import check_progress, recovery_delay, CONNECT_TIMEOUT, TASK_TIMEOUT
from desktop.worker import RoomStateRecorder


class StabilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"name": "test", "uid": 2, "room": 1}])
        self.engine = Engine(self.root, job=Mock())

    def test_bad_room_json_does_not_prevent_status_publication(self):
        (self.root / "state/1.json").write_text("{broken")
        self.engine.persist()
        saved = read_json(self.root / "status.json")
        self.assertEqual(saved["pid"], os.getpid())
        self.assertEqual(saved["rows"][0]["phase"], "状态记录异常")
        write_json(self.root / "state/1.json", {"started": None, "last_heartbeat": None})
        self.engine.persist()
        self.assertNotIn(1, self.engine.state_errors)

    def test_publish_failure_keeps_tick_and_health_alive_then_recovers(self):
        original = write_json
        def fail_status(path, value):
            if Path(path).name == "status.json":
                raise PermissionError("synthetic file held open")
            original(path, value)
        # The test's two cycles share a throttle window; force the health refresh below.
        self.engine.last_health_publish = 0
        with patch.object(self.engine, "tick") as tick:
            with patch("desktop.engine.write_json", side_effect=fail_status):
                self.engine.cycle()
            tick.assert_called_once()
            health = read_json(self.root / "monitor-health.json")
            self.assertEqual(health["publish_error"], "PermissionError")
            self.assertGreater(health["last_tick"], 0)
            self.engine.last_health_publish = 0
            self.engine.cycle()
        self.assertEqual(self.engine.publish_error, "")
        self.assertEqual(read_json(self.root / "status.json")["error"], "")
        self.assertGreater(read_json(self.root / "monitor-health.json")["last_status_publish"], 0)

    @unittest.skipUnless(os.name == "nt", "Windows file sharing failure")
    def test_real_windows_file_occupation_recovers_without_stopping_tick(self):
        import ctypes
        from ctypes import wintypes
        self.engine.persist()
        # Let the next cycle publish a failure instead of skipping this one as recent.
        self.engine.last_status_publish = 0
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.CreateFileW(str(self.root / "status.json"), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with patch.object(self.engine, "tick") as tick:
                self.engine.cycle()
            tick.assert_called_once()
            self.assertEqual(self.engine.publish_error, "PermissionError")
            self.assertEqual(read_json(self.root / "monitor-health.json")["publish_error"], "PermissionError")
        finally:
            kernel.CloseHandle(handle)
        with patch.object(self.engine, "tick"):
            self.engine.cycle()
        self.assertEqual(self.engine.publish_error, "")
        self.assertEqual(read_json(self.root / "status.json")["pid"], os.getpid())

    def test_tick_failure_still_publishes_diagnostic_status(self):
        with patch.object(self.engine, "tick", side_effect=ValueError("synthetic bad config")):
            self.engine.cycle()
        self.assertIn("ValueError", read_json(self.root / "status.json")["error"])

    def test_snapshots_are_throttled_but_state_changes_and_errors_publish_immediately(self):
        with patch.object(self.engine, "tick"):
            self.engine.cycle()
            first = read_json(self.root / "status.json")["updated"]
            self.engine.cycle()
            self.assertEqual(read_json(self.root / "status.json")["updated"], first)
            self.engine.persist()
            self.assertGreater(read_json(self.root / "status.json")["updated"], first)
        # A failure during the throttle window is still recorded for diagnostics.
        self.engine.last_status_publish = 0
        with patch("desktop.engine.write_json", side_effect=PermissionError("synthetic")):
            with patch.object(self.engine, "tick"):
                self.engine.cycle()
        self.assertEqual(self.engine.publish_error, "PermissionError")

    def test_stalled_worker_terminated_and_backoff_respected(self):
        proc = Mock(pid=99)
        proc.poll.return_value = None
        self.engine.workers[1] = proc
        self.engine.worker_health[1] = {
            "pid": 99, "started": 0, "progress": 0,
            "signature": (100, 0), "had_beat": True,
        }
        write_json(self.root / "state/1.json", {"pid": 99, "last_heartbeat": 100, "beats": 1})
        with patch("desktop.engine.time.monotonic", return_value=500):
            self.engine._watch_workers(1000)
            proc.terminate.assert_called_once()
            self.assertNotIn(1, self.engine.workers)
            with patch.object(self.engine, "spawn") as spawn:
                self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}}, 1000)
            spawn.assert_not_called()
        with patch("desktop.engine.time.monotonic", return_value=561):
            with patch.object(self.engine, "spawn", return_value=Mock(pid=100)) as spawn:
                self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}}, 1061)
            spawn.assert_called_once()
        self.assertEqual(self.engine.worker_health[1]["pid"], 100)
        self.assertEqual(recovery_delay(1), 60)
        self.assertEqual(recovery_delay(2), 120)
        self.assertEqual(recovery_delay(100), 900)

    def test_retry_probe_does_not_spin_when_offline_or_query_fails(self):
        self.engine.worker_retries[1] = {"attempt": 1, "until": 0}
        self.engine._apply_probe({"statuses": {"1": {"live_status": 0}}}, 100)
        self.assertNotIn(1, self.engine.worker_retries)
        for result in ({"error": "network unavailable"}, {"statuses": {}}):
            self.engine.worker_retries[1] = {"attempt": 1, "until": 0}
            with patch("desktop.engine.time.monotonic", return_value=500):
                self.engine._apply_probe(result, 100)
            self.assertEqual(self.engine.worker_retries[1]["until"], 800)
        self.engine.probe = Mock()
        self.engine.next_check = 9999
        with patch("desktop.engine.time.monotonic", return_value=900):
            self.engine._watch_workers(100)
        self.assertEqual(self.engine.next_check, 9999)

    def test_old_generation_file_cannot_refresh_worker_progress(self):
        record = {"pid": 99, "started": 0, "progress": 0}
        state = {"pid": 98, "last_heartbeat": time.time()}
        self.assertFalse(check_progress(state, record, CONNECT_TIMEOUT - 1))
        self.assertTrue(check_progress(state, record, CONNECT_TIMEOUT + 1))

    def test_task_queue_grace_is_bounded_and_beats_extend_progress(self):
        record = {"pid": 99, "started": 0, "progress": 0}
        state = {"pid": 99, "phase": "执行任务中", "task_started": 50}
        self.assertFalse(check_progress(state, record, 1))
        self.assertFalse(check_progress(state, record, TASK_TIMEOUT))
        self.assertTrue(check_progress(state, record, TASK_TIMEOUT + 2))
        state.update(phase="挂机中", last_heartbeat=100)
        self.assertFalse(check_progress(state, record, TASK_TIMEOUT + 3))

    def test_protection_still_prevents_worker_restart(self):
        self.engine.worker_retries[1] = {"until": 0, "attempt": 3}
        self.engine.safety = {"blocked": True}
        with patch.object(self.engine, "spawn") as spawn:
            self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}}, 100)
        spawn.assert_not_called()

    def test_task_churn_cannot_extend_the_heartbeat_deadline(self):
        record = {"pid": 99, "started": 0, "progress": 0}
        state = {"pid": 99, "last_heartbeat": 100, "phase": "挂机中"}
        self.assertFalse(check_progress(state, record, 0))
        for stamp in (300, 900, 1700):
            state.update(phase="执行任务中", task_started=stamp)
            self.assertFalse(check_progress(state, record, stamp))
        self.assertTrue(check_progress(state, record, TASK_TIMEOUT + 1))
        state.update(phase="挂机中", task_started=None)
        self.assertTrue(check_progress(state, record, TASK_TIMEOUT + 2))

    def test_manual_reconnect_stops_only_selected_room_and_waits_for_fresh_probe(self):
        selected, other = Mock(pid=99), Mock(pid=100)
        selected.poll.return_value = other.poll.return_value = None
        self.engine.workers = {1: selected, 2: other}
        self.engine.worker_health[1] = {"pid": 99}
        self.engine.worker_retries[1] = {"attempt": 3, "until": 10000}
        with patch("desktop.engine.time.time", return_value=100):
            ok, _ = self.engine.reconnect_room(1)
        self.assertTrue(ok)
        selected.terminate.assert_called_once()
        other.terminate.assert_not_called()
        self.assertNotIn(1, self.engine.workers)
        self.assertEqual(self.engine.next_check, 0)
        with patch.object(self.engine, "spawn", return_value=Mock(pid=101)) as spawn:
            self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}, "observed": 99}, 101)
            spawn.assert_not_called()
            self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}, "observed": 102}, 103)
        spawn.assert_called_once_with("--worker", "1", "--watch-only")
        self.assertTrue(self.engine.manual_reconnects[1]["skip_actions"])

    def test_manual_reconnect_respects_pause_protection_and_duplicate_cooldown(self):
        self.engine.paused = True
        self.assertFalse(self.engine.reconnect_room(1)[0])
        self.engine.paused = False
        with patch.object(self.engine.application, "safety_status", return_value={"blocked": True}):
            self.assertFalse(self.engine.reconnect_room(1)[0])
        with patch("desktop.engine.time.time", return_value=100):
            self.assertTrue(self.engine.reconnect_room(1)[0])
            self.assertFalse(self.engine.reconnect_room(1)[0])
        self.assertFalse(self.engine.reconnect_room(999)[0])

    def test_manual_reconnect_never_starts_for_offline_or_unknown_status(self):
        for result in ({"statuses": {"1": {"live_status": 0}}}, {"statuses": {}}, {"error": "network"}):
            with self.subTest(result=result):
                self.engine.manual_reconnects.clear()
                with patch("desktop.engine.time.time", return_value=100):
                    self.assertTrue(self.engine.reconnect_room(1)[0])
                with patch.object(self.engine, "spawn") as spawn:
                    self.engine._apply_probe(result, 101)
                spawn.assert_not_called()
                self.assertIn(self.engine.manual_reconnects[1]["state"], ("offline", "failed"))

    def test_manual_reconnect_worker_skips_reactions_without_changing_saved_policy(self):
        from desktop.worker import watch
        from desktop.storage import load_config
        with patch("desktop.worker.Mutex") as mutex, patch("desktop.worker.AppContext") as app:
            mutex.return_value.acquired = True
            app.return_value.run_watch.return_value = 0
            watch(self.root, 1, watch_only=True)
            policy = app.return_value.run_watch.call_args.args[1]
        self.assertFalse(any(policy.get(k) for k in ("auto_revive", "auto_danmaku_intimacy", "auto_like")))
        self.assertTrue(load_config(self.root)[0]["auto_revive"])

    def test_failed_worker_spawn_releases_pending_reconnect(self):
        with patch("desktop.engine.time.time", return_value=100):
            self.assertTrue(self.engine.reconnect_room(1)[0])
        with patch.object(self.engine, "spawn", side_effect=OSError("synthetic spawn failure")):
            self.engine._apply_probe({"statuses": {"1": {"live_status": 1}}}, 101)
        self.assertEqual(self.engine.manual_reconnects[1]["state"], "failed")
        self.assertNotIn(1, self.engine.workers)
        self.assertGreater(self.engine.worker_retries[1]["until"], time.monotonic())

    def test_failed_probe_spawn_releases_pending_reconnect(self):
        self.engine.next_check = 0
        self.engine.manual_reconnects[1] = {"state": "checking", "requested_at": 0, "skip_actions": True}
        with patch.object(self.engine, "spawn", side_effect=OSError("synthetic spawn failure")):
            self.engine.cycle()
        self.assertEqual(self.engine.manual_reconnects[1]["state"], "failed")

    def test_stale_connection_has_reconnect_action_and_is_not_healthy(self):
        self.engine.workers[1] = Mock()
        self.engine.workers[1].poll.return_value = None
        self.engine.statuses["1"] = {"live_status": 1}
        self.engine.status_times["1"] = time.time()
        write_json(self.root / "state/1.json", {"started": time.time()-1000, "last_heartbeat": time.time()-900})
        row = self.engine.snapshot()["rows"][0]
        self.assertTrue(row["reconnect_allowed"])
        self.assertTrue(row["connection_warning"])
        self.assertFalse(row["heartbeat_healthy"])

    def test_refresh_survives_snapshot_exception(self):
        ui = Mock(closed=False)
        ui.engine.snapshot.side_effect = ValueError("synthetic error")
        TrayUI.refresh(ui)
        ui.root.after.assert_called_once_with(1000, ui.refresh)
        ui.summary.set.assert_called_once()

    def test_bad_command_does_not_block_following_valid_command(self):
        folder = self.root / "commands"
        (folder / "0.json").write_text("{broken")
        write_json(folder / "1.json", {"command": "show", "created": time.time()})
        import queue
        ui = Mock();ui.engine.root = self.root;ui.commands = queue.Queue()
        # Do not consume the valid command via the generic Mock's queue handling.
        ui.show = Mock()
        TrayUI._read_commands(ui)
        ui.show.assert_called_once()
        self.assertEqual(list(folder.glob("*.json")), [])

    def test_room_recorder_marks_task_execution_and_restores_phase(self):
        recorder = RoomStateRecorder(self.root / "state/1.json", {"room": 1, "name": "test"})
        recorder({"type": "task_check_start"})
        self.assertEqual(read_json(recorder.path)["phase"], "执行任务中")
        recorder({"type": "task_check_end"})
        self.assertNotIn("task_started", read_json(recorder.path))
        self.assertEqual(read_json(recorder.path)["phase"], "正在连接")
