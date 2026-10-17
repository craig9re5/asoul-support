"""Credential validation and GUI login persistence without real account IO."""

import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from asoul_support.application import AppContext
from asoul_support.credentials import parse_login_import
from desktop.dialogs import SettingsDialog


class ScopedSettingsTests(unittest.TestCase):
    def test_automation_save_preserves_credentials_and_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "settings.json").write_text(json.dumps({"paused": True, "unknown": 7}))
            panel = SimpleNamespace(scope="automation", interval_var=Mock(), engine=Mock(root=root),
                                    on_saved=Mock(), save_status=Mock())
            panel.interval_var.get.return_value = "15"
            for name in ("var_auto_revive", "var_auto_danmu", "var_auto_like", "var_notify", "var_autostart"):
                setattr(panel, name, Mock())
                getattr(panel, name).get.return_value = False
            with patch("desktop.dialogs.save_login") as save, patch("desktop.dialogs.set_autostart", return_value=True):
                SettingsDialog.do_save(panel)
            save.assert_not_called()
            config = json.loads((root / "settings.json").read_text())
            self.assertTrue(config["paused"])
            self.assertEqual(config["unknown"], 7)
            self.assertEqual(config["check_minutes"], 15)
            panel.engine.application.validate_credentials.assert_not_called()

    def test_account_save_never_writes_credentials_or_automation(self):
        engine = Mock(root=Path("isolated-data"))
        engine.dispatcher = None  # apply_saved_settings falls back to a direct reload
        panel = SimpleNamespace(scope="account", engine=engine,
                                on_saved=Mock(), save_status=Mock())
        with patch("desktop.dialogs.save_login") as save, patch("desktop.dialogs.update_json") as settings, \
             patch("desktop.dialogs.set_autostart") as autostart:
            SettingsDialog.do_save(panel)
        save.assert_not_called()
        settings.assert_not_called()
        autostart.assert_not_called()
        panel.on_saved.assert_called_once_with()



class LoginImportTests(unittest.TestCase):
    def test_export_import_keeps_only_login_fields(self):
        payload = {
            "format": "livesupport-login",
            "version": 1,
            "credentials": {
                "SESSDATA": "synthetic%2Csession",
                "bili_jct": "synthetic-csrf",
                "unrelated": "omit",
            },
        }
        self.assertEqual(
            parse_login_import(json.dumps(payload)),
            {"SESSDATA": "synthetic%2Csession", "bili_jct": "synthetic-csrf"},
        )

    def test_cookie_header_ignores_unrelated_fields(self):
        self.assertEqual(
            parse_login_import("SESSDATA=synthetic; extra=unused; bili_jct=synthetic"),
            {"SESSDATA": "synthetic", "bili_jct": "synthetic"},
        )

    def test_invalid_import_does_not_include_secret_in_errors(self):
        for raw in (
            '{"SESSDATA":"synthetic-secret"}',
            '{"credentials":[]}',
            '{"version":2}',
            "SESSDATA=synthetic-secret\r\nX-Test: injected; bili_jct=x",
            "x" * 16_385,
        ):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError) as captured:
                parse_login_import(raw)
            self.assertNotIn("synthetic-secret", str(captured.exception))

    def test_invalid_auth_header_rejected_before_network(self):
        ok, message = AppContext().validate_credentials(
            "synthetic\r\nInjected: header", "synthetic"
        )
        self.assertFalse(ok)
        self.assertNotIn("Injected", message)


class QrCredentialSaveTests(unittest.TestCase):
    def dialog(self):
        return SimpleNamespace(
            winfo_exists=Mock(return_value=True),
            engine=SimpleNamespace(root=Path("isolated-data"), reload_settings=Mock()),
            set_auth_status=Mock(),
            on_saved=Mock(),
        )

    def test_verified_qr_pair_saved_and_reloaded_without_import_ui(self):
        dialog = self.dialog()
        cookies = {"SESSDATA": "synthetic-session", "bili_jct": "synthetic-csrf"}
        with patch("desktop.dialogs.save_login") as save:
            SettingsDialog.on_qr_login(dialog, cookies, "test account")
        save.assert_called_once_with(
            "synthetic-session", "synthetic-csrf", Path("isolated-data/credentials.json")
        )
        dialog.engine.reload_settings.assert_called_once_with()
        dialog.on_saved.assert_called_once_with()

    def test_closed_settings_does_not_save_qr_result(self):
        dialog = self.dialog()
        dialog.winfo_exists.return_value = False
        with patch("desktop.dialogs.save_login") as save:
            SettingsDialog.on_qr_login(dialog, {}, "test account")
        save.assert_not_called()
        dialog.engine.reload_settings.assert_not_called()
        dialog.on_saved.assert_not_called()

    def test_failed_qr_save_does_not_apply_or_report_success(self):
        dialog = self.dialog()
        cookies = {"SESSDATA": "synthetic-session", "bili_jct": "synthetic-csrf"}
        with patch("desktop.dialogs.save_login", side_effect=OSError("unwritable")):
            with self.assertRaises(OSError):
                SettingsDialog.on_qr_login(dialog, cookies, "test account")
        dialog.engine.reload_settings.assert_not_called()
        dialog.on_saved.assert_not_called()
