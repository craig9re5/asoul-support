"""Contracts at the local renderer boundary; no browser or account requests."""

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop.engine import Engine
from desktop.storage import initialize, read_json, write_json, send_command
from desktop.webui.api import Api
from desktop.webui.window import WebHost


class WebUiTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"room": 7, "uid": 9, "name": "测试主播"}])
        self.engine = Engine(self.root, job=Mock())
        self.ui = Mock()
        self.ui.apply_settings.side_effect = self.engine.reload_settings
        self.api = Api(self.engine, self.ui)

    def confirmed_room(self):
        self.engine.account = "测试账号"
        self.engine.account_checked_at = time.time()
        self.engine.statuses["7"] = {"live_status": 1}
        self.engine.status_times["7"] = time.time()
        self.engine.application.redo = Mock(return_value={"success": True})

    def test_snapshot_preserves_account_and_never_exposes_owned_objects_or_credentials(self):
        self.confirmed_room()
        write_json(self.root / "credentials.json", {"SESSDATA": "synthetic-session", "bili_jct": "synthetic-csrf"})
        with patch("asoul_support.runtime.unseal", side_effect=AssertionError("UI must not decrypt")):
            snap = self.api.snapshot()
        self.assertEqual(snap["account"], "测试账号")
        self.assertTrue(snap["accountInfo"]["signed_in"])
        self.assertEqual(snap["rows"][0]["actions"]["redo"], "")
        self.assertNotIn("synthetic-session", json.dumps(snap))
        self.assertTrue(all(callable(getattr(self.api, name)) for name in dir(self.api) if not name.startswith("_")))
        with patch.object(self.engine, "snapshot", return_value=None):
            cached = self.api.snapshot()
        self.assertTrue(cached["engine_busy"])
        self.assertEqual(cached["rows"][0]["name"], "测试主播")

    def test_settings_normalize_legacy_policy_and_apply_despite_autostart_failure(self):
        write_json(self.root / "settings.json", {"danmaku": False, "live_likes": True, "check_minutes": 15})
        with patch("desktop.windows.set_autostart", return_value=False), \
             patch("desktop.windows.is_autostart_enabled", return_value=False):
            result = self.api.save_settings({"autostart": True, "notify_on_live": True})
        self.assertTrue(result["ok"])
        self.assertTrue(result["warning"])
        saved = read_json(self.root / "settings.json")
        self.assertFalse(saved["auto_revive"])
        self.assertFalse(saved["auto_danmaku_intimacy"])
        self.assertTrue(self.engine.config["auto_like"])
        for changes in ({"auto_like": "false"}, {"check_minutes": 1.5}, {"check_minutes": True}):
            self.assertFalse(self.api.save_settings(changes)["ok"])

    def test_duplicate_room_writes_are_rejected_while_pause_remains_responsive(self):
        self.confirmed_room()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow_redo(*_):
            entered.set()
            release.wait(4)
            return {"success": True}
        self.engine.application.redo.side_effect = slow_redo
        worker = threading.Thread(target=lambda: self.api.redo(7))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.api.redo(7)["ok"])
            with patch.object(self.engine, "set_paused") as pause:
                self.assertTrue(self.api.set_paused(True)["ok"])
                pause.assert_called_once_with(True)
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.engine.application.redo = Mock(return_value={"success": False, "error": "任务尚未完成"})
        self.assertFalse(self.api.redo(7)["ok"])

    def test_sync_import_uses_resolved_members_and_retains_existing(self):
        self.engine.application.medals = Mock(return_value=[
            {"uid": 9, "room": 7, "name": "测试主播", "medal_name": "牌", "level": 8},
            {"uid": 10, "room": 8, "name": "新主播", "medal_name": "新牌", "level": 4},
        ])
        result = self.api.medals()
        self.assertTrue(result["ok"])
        self.assertTrue(next(row for row in result["medals"] if row["uid"] == 9)["watched"])
        self.assertEqual(self.api.import_medals([9, 10])["count"], 1)
        self.assertEqual({row["room"] for row in read_json(self.root / "members.json")}, {7, 8})

    def test_cancelled_qr_cannot_save_after_validation_returns(self):
        from asoul_support.qr_login import PollResult
        session = Mock()
        cancel = threading.Event()
        with self.api._qr_lock:
            generation = self.api._qr_generation
            self.api._qr_session, self.api._qr_cancel_event = session, cancel
        with self.api._state:
            self.api._active += 1
        session.poll.return_value = PollResult("confirmed", credentials={"SESSDATA": "test", "bili_jct": "test"})
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def validate(*_):
            entered.set()
            release.wait(3)
            return True, "测试账号"
        self.engine.application.validate_credentials = validate
        with patch("asoul_support.qr_login.POLL_INTERVAL", 0.001), \
             patch("asoul_support.runtime.save_login") as save:
            worker = threading.Thread(target=self.api._qr_poll, args=(generation, session, cancel))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.api.qr_cancel()
            finally:
                release.set()
                worker.join(4)
            save.assert_not_called()
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.api._active, 0)

    def test_shutdown_waits_for_accepted_io_and_processes_ipc(self):
        host = WebHost(self.engine)
        host._window = Mock()
        send_command(self.root, "show")
        send_command(self.root, "login")
        host._read_commands()
        host._window.show.assert_called()
        self.assertEqual(host._queue.get_nowait(), ("open_login", {}))
        self.assertFalse(list((self.root / "commands").glob("*.json")))
        drained = threading.Event()
        def wait_io():
            drained.wait(3)
        host._api._wait_for_io = wait_io
        self.engine.close = Mock()
        host.quit()
        self.assertFalse(host._closed.wait(0.05))
        self.assertFalse(host._api.save_settings({"auto_like": False})["ok"])
        drained.set()
        self.assertTrue(host._closed.wait(3))
        host._shutdown_thread.join(3)
        self.engine.close.assert_called_once()
        host._window.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
