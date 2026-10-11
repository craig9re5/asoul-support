"""Recovery routing and availability contracts; no account or Tk side effects."""

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
from desktop.interaction import action_reason, recovery_route
from desktop.engine import Engine
from desktop.storage import initialize
from desktop.dispatch import Dispatcher


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.snap = {"account": "synthetic", "account_confirmed": True, "paused": False,
                     "safety": {"blocked": False}, "rows": []}
        self.row = {"room": 1, "name": "synthetic", "live_status": 1,
                    "medal_name": "test", "reconnect_allowed": True}

    def test_healthy_state_does_not_advertise_an_unavailable_safety_action(self):
        self.assertEqual(recovery_route(self.snap), {})

    def test_account_failures_have_matching_routes_and_disabled_reasons(self):
        for kind, action, label in (("auth", "login", "重新扫码登录"),
                                   ("credentials", "login", "重新扫码登录"),
                                   ("review", "safety", "解除异常暂停")):
            with self.subTest(kind=kind):
                snap = {**self.snap, "safety": {"blocked": True, "kind": kind, "reason": "synthetic"}}
                route = recovery_route(snap)
                self.assertEqual((route["action"], route["label"]), (action, label))
                for operation in ("redo", "reconnect", "wear"):
                    self.assertIn(label, action_reason(snap, self.row, operation))
                self.assertFalse(action_reason(snap, self.row, "open"))

    def test_cooldown_explains_automatic_recovery_without_offering_a_bypass(self):
        snap = {**self.snap, "safety": {"blocked": True, "kind": "network", "until": time.time()+60}}
        self.assertEqual(recovery_route(snap)["label"], "查看冷却说明")
        self.assertIn("自动恢复", action_reason(snap, self.row, "redo"))

    def test_pause_and_unverified_login_have_a_next_step(self):
        snap = {**self.snap, "paused": True}
        self.assertEqual(recovery_route(snap)["action"], "resume")
        self.assertIn("恢复挂机", action_reason(snap, self.row, "redo"))
        for account, expected in (("", "login"), ("synthetic", "check")):
            snap = {**self.snap, "account": account, "account_confirmed": False}
            self.assertEqual(recovery_route(snap)["action"], expected)
            self.assertTrue(action_reason(snap, self.row, "redo"))

    def test_query_and_progress_errors_offer_check_or_affected_room(self):
        self.assertEqual(recovery_route({**self.snap, "error": "query failure"})["action"], "check")
        for field in ("connection_warning", "watch_warning", "task_error", "status_error"):
            with self.subTest(field=field):
                route = recovery_route({**self.snap, "rows": [{**self.row, field: "synthetic failure"}]})
                self.assertEqual(route["room"], 1)
                self.assertEqual(route["action"], "check" if field == "status_error" else "room")
        self.assertEqual(recovery_route({**self.snap, "rows": [{**self.row, "tasks_stale": True}]})["action"], "check")

    def test_unavailable_room_actions_explain_the_condition(self):
        for live, words in ((None, "立即检查"), (0, "已下播")):
            row = {**self.row, "live_status": live, "reconnect_allowed": False}
            for action in ("redo", "reconnect"):
                self.assertIn(words, action_reason(self.snap, row, action))
        self.assertIn("选择主播", action_reason(self.snap, {}, "redo"))
        self.assertIn("同步粉丝牌", action_reason(self.snap, {**self.row, "medal_name": ""}, "wear"))
        self.assertIn("17 秒", action_reason(self.snap, {**self.row, "reconnect_cooldown_until": 117}, "reconnect", now=100))
        self.assertIn("等待", action_reason(self.snap, {**self.row, "reconnecting": True}, "reconnect"))

    def test_pending_busy_or_closing_cannot_submit_a_second_write(self):
        for action in ("redo", "reconnect", "wear"):
            self.assertTrue(action_reason(self.snap, self.row, action, pending=True))
            self.assertTrue(action_reason({**self.snap, "closing": True}, self.row, action))
            self.assertTrue(action_reason({**self.snap, "engine_busy": True}, self.row, action))
        self.assertEqual(recovery_route({**self.snap, "engine_busy": True})["action"], "logs")
        self.assertEqual(recovery_route({**self.snap, "ui_error": "synthetic"})["action"], "refresh")
        self.assertIn("重试界面", action_reason({**self.snap, "ui_error": "synthetic"}, self.row, "redo"))

    def test_ui_snapshot_does_not_wait_for_a_busy_monitor_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [])
            engine = Engine(root, job=Mock())
            acquired, release = threading.Event(), threading.Event()
            def hold():
                with engine.lock:
                    acquired.set()
                    release.wait(2)
            thread = threading.Thread(target=hold)
            thread.start()
            try:
                self.assertTrue(acquired.wait(1))
                self.assertIsNone(engine.snapshot(blocking=False))
            finally:
                release.set()
                thread.join(2)
            self.assertIsInstance(engine.snapshot(blocking=False), dict)

    def test_controls_remain_available_when_all_io_workers_are_busy(self):
        dispatcher = Dispatcher(Mock())
        release = threading.Event()
        started = [threading.Event() for _ in range(3)]
        def occupy(event):
            event.set()
            release.wait(3)
        try:
            for event in started:
                dispatcher.submit(lambda event=event: occupy(event))
            self.assertTrue(all(event.wait(1) for event in started))
            self.assertEqual(dispatcher.submit_control(lambda: "available").result(1), "available")
        finally:
            release.set()
            dispatcher.close()

    def test_qr_session_creation_failure_still_has_a_refresh_route(self):
        from desktop.qr_dialog import QrSessionView
        view = SimpleNamespace(session_factory=Mock(side_effect=RuntimeError("synthetic-secret")),
                               post=Mock(), show_error=Mock())
        cancelled = threading.Event()
        QrSessionView.run_session(view, cancelled)
        view.post.assert_called_once_with(cancelled, view.show_error)

    def test_saved_settings_apply_failure_releases_button_and_does_not_report_success(self):
        from desktop.dialogs import apply_saved_settings
        dispatcher = Mock()
        dispatcher.submit_control.side_effect = lambda callback: callback() or Mock()
        dispatcher.post.side_effect = lambda callback: callback()
        panel = SimpleNamespace(engine=SimpleNamespace(dispatcher=dispatcher,
                                reload_settings=Mock(side_effect=RuntimeError("synthetic-secret"))),
                                scope="automation", save_button=Mock(), save_status=Mock(), on_saved=Mock(),
                                winfo_exists=Mock(return_value=True))
        apply_saved_settings(panel)
        self.assertFalse(panel.applying)
        panel.on_saved.assert_not_called()
        self.assertEqual(panel.save_button.configure.call_args.kwargs["state"], "normal")
        message = panel.save_status.set.call_args.args[0]
        self.assertIn("已保存，但应用失败", message)
        self.assertNotIn("synthetic-secret", message)
