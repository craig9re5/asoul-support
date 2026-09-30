"""Build every real Tk view with fake tray/network adapters and isolated data."""

from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from desktop.engine import Engine
    from desktop.storage import initialize
    from desktop.ui import TrayUI, SettingsDialog, AddMemberDialog, SyncMedalsDialog

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        initialize(root, [{"name": "测试主播", "room": 2, "uid": 1}])
        engine = Engine(root, job=Mock())
        with (
            patch("desktop.view.pystray.Icon", return_value=Mock()),
            patch("urllib.request.urlopen", side_effect=AssertionError("network in UI smoke")),
            patch(
                "urllib.request.OpenerDirector.open",
                side_effect=AssertionError("network in UI smoke"),
            ),
        ):
            ui = TrayUI(engine, show=True)
            try:
                ui.root.withdraw()
                ui.root.update_idletasks()
                ui.refresh()
                ui.tree.selection_set("2")
                ui.tree.focus("2")
                ui.refresh()
                assert ui.tree.selection() == ("2",)
                assert ui.tree.focus() == "2"
                engine.safety = {"blocked": True, "kind": "review", "reason": "测试账号保护暂停"}
                ui.refresh()
                assert "测试账号保护暂停" in ui.footer.get()
                assert ui.rows_cache["2"]["phase"] == "账号保护暂停"
                engine.safety = {"blocked": False}
                settings = SettingsDialog(ui.root, engine, ui.px, lambda: None)
                settings.update_idletasks()
                assert settings.e_sess.cget("show")
                from desktop.qr_dialog import QrLoginDialog
                from asoul_support.qr_login import PollResult

                session = Mock()
                session.generate.return_value = (
                    "https://account.bilibili.com/h5/account-h5/auth/scan-web?key=synthetic"
                )
                session.poll.return_value = PollResult("waiting")
                qr = QrLoginDialog(settings, engine, ui.px, Mock(), session_factory=lambda: session)
                for _ in range(20):
                    ui.root.update()
                    if getattr(qr, "qr_image", None):
                        break
                    time.sleep(0.05)
                assert qr.qr_image is not None
                qr.close()
                assert qr.cancelled.is_set()
                settings.destroy()
                add = AddMemberDialog(ui.root, engine, ui.px, lambda: None)
                add.update_idletasks()
                add.destroy()
                with patch.object(engine.dispatcher, "submit"):
                    sync = SyncMedalsDialog(ui.root, engine, ui.px, lambda: None)
                sync.update_idletasks()
                sync.display_medals([], 0)
                sync.destroy()
            finally:
                engine.dispatcher.close()
                ui.closed = True
                ui.tray.stop()
                ui.root.destroy()
                engine.job.close()
    print("Desktop views: OK (isolated data, no network)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
