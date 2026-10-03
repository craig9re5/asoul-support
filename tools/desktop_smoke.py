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
        members = [{"name": f"测试主播{i}Viridis", "room": 2 * i, "uid": i} for i in range(1, 8)]
        initialize(root, members)
        engine = Engine(root, job=Mock())
        engine.statuses = {str(member["room"]): {"live_status": 1, "title": "超长直播标题\n" * 30}
                           for member in members}
        engine.status_times = {str(member["room"]): time.time() for member in members}
        capacities = []
        with (
            patch("desktop.avatars.load_avatar", return_value=__import__("PIL.Image", fromlist=["Image"]).new("RGB", (32,32), "green")),
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
                assert ui.workbench.detail_gain.master == ui.workbench.detail_medal.master
                detail_children = ui.workbench.detail_frame.pack_slaves()
                assert detail_children.index(ui.workbench.detail_medal) < detail_children.index(ui.workbench.detail_gain)
                item = ui.tree.items["2"]
                assert item["phase"].master == item["medal"].master == item["gain"].master
                assert {item[key].grid_info()["row"] for key in ("phase", "medal", "gain")} == {0}
                assert "双击" not in ui.footer.get() and "右键" not in ui.footer.get()
                toolbar = ui.workbench.toolbar
                assert ui.summary_label.master == ui.pause_button.master == ui.safety_button.master == toolbar
                assert ui.workbench.check_button.master == toolbar
                assert ui.footer_label.master == ui.workbench.footer_bar
                # Map real widgets at both supported sizes to catch clipping.
                ui.rows_cache["2"].update(medal_name="同行者", intimacy_gain=9)
                values = list(item["values"])
                values[2], values[4] = "同行者 Lv.9", "挂机中·42分钟"
                ui.tree.item("2", values=tuple(values))
                ui.root.deiconify()
                for width, height in ((1180, 760), (980, 620)):
                    ui.root.geometry(f"{ui.px(width)}x{ui.px(height)}")
                    ui.root.update()
                    canvas = ui.tree.canvas
                    row_frames = [ui.tree.items[str(member["room"])]["frame"] for member in members]
                    visible = sum(frame.winfo_rooty() >= canvas.winfo_rooty()
                                  and frame.winfo_rooty() + frame.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
                                  for frame in row_frames)
                    assert visible >= 6, (width, height, visible)
                    assert len({frame.winfo_height() for frame in row_frames}) == 1
                    capacities.append((width, height, canvas.winfo_height() // row_frames[0].winfo_height()))
                    for button in (ui.pause_button, ui.safety_button, ui.workbench.check_button):
                        assert button.winfo_height() >= button.winfo_reqheight()
                        assert button.winfo_y() + button.winfo_height() <= toolbar.winfo_height()
                    assert ui.summary_label.winfo_width() >= ui.summary_label.winfo_reqwidth()
                    for key in ("phase", "medal", "gain"):
                        widget = item[key]
                        assert widget.winfo_width() >= widget.winfo_reqwidth(), (key, width)
                    actions = ui.workbench.detail_actions
                    for button in actions.pack_slaves():
                        assert button.winfo_height() >= button.winfo_reqheight()
                        assert button.winfo_y() + button.winfo_height() <= actions.winfo_height()
                        assert button.winfo_x() + button.winfo_width() <= actions.winfo_width()
                    assert actions.winfo_y() + actions.winfo_height() <= ui.workbench.detail_outer.winfo_height()
                ui.root.withdraw()
                engine.safety = {"blocked": True, "kind": "review", "reason": "测试账号保护暂停"}
                ui.refresh()
                assert "测试账号保护暂停" in ui.footer.get()
                assert "解除异常暂停" in ui.footer.get()
                assert ui.safety_button.winfo_manager() == "pack"
                assert ui.safety_button.cget("state") == "normal"
                engine.safety = {"blocked": True, "kind": "network", "until": time.time() + 60,
                                 "reason": "心跳连接异常"}
                ui.refresh()
                assert ui.safety_button.cget("text") == "冷却中 · 自动恢复"
                engine.safety = {"blocked": True, "kind": "auth", "reason": "登录失效"}
                ui.refresh()
                assert ui.safety_button.cget("text") == "重新扫码登录"
                engine.safety = {"blocked": True, "kind": "review", "reason": "测试账号保护暂停"}
                ui.refresh()
                assert ui.rows_cache["2"]["phase"] == "账号保护暂停"
                engine.safety = {"blocked": False}
                ui.refresh()
                assert ui.safety_button.cget("state") == "disabled"
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
    print(f"Desktop views: OK (isolated data, no network); visible room capacity: {capacities}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
