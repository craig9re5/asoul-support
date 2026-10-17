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
        engine.account = "模拟账号"
        engine.account_checked_at = time.time()
        from asoul_support.runtime import task_day
        engine.tasks = {str(member["room"]): {"day": task_day(), "updated": time.time()} for member in members}
        engine.statuses = {str(member["room"]): {"live_status": 1, "title": "超长直播标题\n" * 30}
                           for member in members}
        engine.status_times = {str(member["room"]): time.time() for member in members}
        engine.medals = {member["uid"]: {"medal_name": "长粉丝牌" if member["uid"] % 2 else "短牌", "level": 9}
                         for member in members}
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
                summary_children = ui.workbench.detail_gain.master.pack_slaves()
                assert summary_children.index(ui.workbench.detail_gain) < summary_children.index(ui.workbench.detail_medal)
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
                    assert len({ui.tree.items[str(member["room"])]["medal"].winfo_rootx() for member in members}) == 1
                    assert len({ui.tree.items[str(member["room"])]["title"].winfo_rootx() +
                                ui.tree.items[str(member["room"])]["title"].winfo_width() for member in members}) == 1
                    assert all(ui.tree.items[str(member["room"])]["title"].cget("anchor") == "e" for member in members)
                    capacities.append((width, height, canvas.winfo_height() // row_frames[0].winfo_height()))
                    for button in (ui.pause_button, ui.safety_button, ui.workbench.check_button):
                        if not button.winfo_manager():
                            continue
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
                # A real warning must remain visible and notify only once while hidden.
                from desktop.worker import RoomStateRecorder
                from asoul_support.runtime import task_day
                recorder = RoomStateRecorder(root / "state/2.json", members[0])
                recorder({"type": "x25kn_x_success", "interval": 60})
                recorder({"type": "watch_progress", "day": task_day(), "checked_at": time.time(),
                          "verified_at": time.time(), "status": "stalled", "warning_since": time.time(),
                          "progress": {"current": 0, "limit": 10},
                          "tasks": [{"jump_type": "watchLive", "title": "观看直播满15分钟",
                                     "sub_title": "每日上限 0/10", "is_done": False}],
                          "warning": "看播进度已约 30 分钟未增长，奖励尚未确认；请在 B 站核对。"})
                engine.workers[2] = Mock()
                engine.workers[2].poll.return_value = None
                ui.tray.notify.reset_mock()
                ui.refresh()
                ui.refresh()
                assert "看播收益待核验" in ui.summary.get()
                assert "核对看播收益" in ui.footer.get()
                assert ui.workbench.detail_warning.winfo_manager() == "pack"
                assert "未增长" in ui.workbench.detail_warning.cget("text")
                assert ui.tree.items["2"]["phase"].cget("fg") == "#a65c00"
                ui.tray.notify.assert_called_once()
                recorder({"type": "watch_progress", "day": task_day(), "checked_at": time.time(),
                          "status": "tracking", "warning": ""})
                ui.refresh()
                assert not ui.workbench.detail_warning.winfo_manager()
                # An expired heartbeat provides a usable repair action and accurate counts.
                recorder.state.update(last_heartbeat=time.time() - 900, started=time.time() - 1200)
                recorder.save()
                ui.tray.notify.reset_mock()
                ui.refresh()
                ui.refresh()
                assert "挂机 0" in ui.summary.get() and "连接异常 1" in ui.summary.get()
                assert "重连此直播间" in ui.footer.get()
                assert ui.workbench.reconnect_button.cget("state") == "normal"
                assert "长时间没有成功心跳" in ui.workbench.detail_warning.cget("text")
                connection_children = ui.workbench.connection_card.pack_slaves()
                assert ui.workbench.detail_phase.master.master == ui.workbench.connection_card
                assert connection_children.index(ui.workbench.detail_heartbeat) < connection_children.index(ui.workbench.detail_warning)
                assert ui.tree.items["2"]["phase"].cget("fg") == "#a65c00"
                ui.tray.notify.assert_called_once()
                with patch.object(engine, "reconnect_room", return_value=(False, "模拟网络失败，请重试。")) as reconnect, \
                     patch.object(engine.dispatcher, "submit_control", side_effect=lambda callback: callback() or Mock()):
                    ui.workbench.reconnect_button.invoke()
                    assert ui.reconnect_pending
                    ui.on_reconnect_room()
                    reconnect.assert_called_once_with(2)
                    ui.refresh()
                    assert not ui.reconnect_pending and "模拟网络失败" in ui.summary.get()
                ui.task_notice = ("", 0)
                engine.manual_reconnects[2] = {"state": "checking", "cooldown_until": time.time() + 60}
                ui.refresh()
                assert ui.workbench.reconnect_button.cget("state") == "disabled"
                assert ui.workbench.reconnect_button.cget("text") == "重连中…"
                engine.manual_reconnects.clear()
                engine.paused = True
                ui.refresh()
                assert ui.workbench.reconnect_button.cget("state") == "disabled"
                engine.paused = False
                engine.workers.clear()
                engine.safety = {"blocked": True, "kind": "review", "reason": "测试账号保护暂停"}
                ui.refresh()
                assert "测试账号保护暂停" in ui.footer.get()
                assert "解除异常暂停" in ui.footer.get()
                assert ui.safety_button.winfo_manager() == "pack"
                assert ui.safety_button.cget("state") == "normal"
                engine.safety = {"blocked": True, "kind": "network", "until": time.time() + 60,
                                 "reason": "心跳连接异常"}
                ui.refresh()
                assert ui.safety_button.cget("text") == "查看冷却说明"
                engine.safety = {"blocked": True, "kind": "auth", "reason": "登录失效"}
                ui.refresh()
                assert ui.safety_button.cget("text") == "重新扫码登录"
                engine.safety = {"blocked": True, "kind": "review", "reason": "测试账号保护暂停"}
                ui.refresh()
                assert ui.rows_cache["2"]["phase"] == "账号保护暂停"
                engine.safety = {"blocked": False}
                ui.refresh()
                assert ui.safety_button.cget("state") == "disabled"
                assert not ui.safety_button.winfo_manager()
                # Detail and menu guards agree; queued actions cannot be duplicated.
                with patch.object(engine.dispatcher, "submit") as submit:
                    ui.on_redo_task("all")
                    ui.on_redo_task("all")
                    submit.assert_called_once()
                    assert ui.room_actions[2]["pending"]
                    assert ui.workbench.redo_button.cget("state") == "disabled"
                    assert ui.menu.entrycget(3, "state") == "disabled"
                    assert "执行" in ui.workbench.action_hint.cget("text")
                    with patch.object(engine.application, "redo", side_effect=RuntimeError("synthetic-secret")):
                        submit.call_args.args[0]()
                    ui.refresh()
                    assert not ui.room_actions[2]["pending"]
                    assert "RuntimeError" in ui.workbench.detail_warning.cget("text")
                    assert "synthetic-secret" not in ui.workbench.detail_warning.cget("text")
                    ui.refresh()
                    assert "RuntimeError" in ui.workbench.detail_warning.cget("text")
                ui.room_actions.clear()
                ui.task_notice = ("", 0)
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
                # Settings/account pages use the existing root, with independently scoped saves.
                ui.open_settings()
                automation = ui.workbench.settings_pages["automation"]
                ui.root.update()
                assert automation.winfo_toplevel() == ui.root
                assert automation.winfo_ismapped() and not ui.tree.winfo_ismapped()
                assert not hasattr(automation, "sessdata_var")
                assert ui.workbench.nav_buttons["automation"].cget("bg") == "#2b4443"
                assert ui.workbench.activity_button.winfo_rooty() > ui.workbench.nav_buttons["account"].winfo_rooty()
                from desktop.widgets import ToggleSwitch
                def switches(widget):
                    return ([widget] if isinstance(widget, ToggleSwitch) else []) + [
                        switch for child in widget.winfo_children() for switch in switches(child)]
                switch = switches(automation)[0]
                original = switch.var.get()
                callback = Mock()
                switch.command = callback
                switch.toggle()
                assert switch.var.get() != original
                callback.assert_called_once()
                switch.configure(state="disabled")
                switch.toggle()
                callback.assert_called_once()
                assert switch.var.get() != original
                switch.configure(state="normal")
                switch.var.set(original)
                assert switch.bind("<space>") and switch.bind("<Return>")
                from PIL import ImageTk
                assert ImageTk.getimage(switch.photo).getpixel((0, 0))[3] == 0
                with patch("desktop.dialogs.save_login") as save_login, patch("desktop.dialogs.set_autostart", return_value=True):
                    automation.do_save()
                    save_login.assert_not_called()
                ui.open_settings(focus_auth=True)
                account = ui.workbench.settings_pages["account"]
                ui.root.update()
                assert account.winfo_toplevel() == ui.root and account.e_sess.cget("show")
                assert not hasattr(account, "interval_var")
                from desktop.qr_dialog import QrLoginPanel
                inline_qr = QrLoginPanel(account.qr_host, engine, ui.px, Mock(), session_factory=lambda: session)
                inline_qr.pack()
                account.qr_panel = inline_qr
                for _ in range(20):
                    ui.root.update()
                    if getattr(inline_qr, "qr_image", None):
                        break
                    time.sleep(0.05)
                assert inline_qr.qr_image is not None and inline_qr.winfo_toplevel() == ui.root
                account.e_sess.configure(show="")
                ui.workbench.show_page("monitor")
                ui.root.update()
                assert inline_qr.cancelled.is_set() and account.e_sess.cget("show")
                assert ui.tree.winfo_ismapped() and ui.tree.selection() == ("2",)
                # Rounded buttons retain native disable/invoke behavior and transparent corners.
                button = ui.workbench.check_button
                from PIL import ImageTk
                assert ImageTk.getimage(button._photos[0]).getpixel((0,0))[3] == 0
                calls = Mock()
                button.configure(command=calls, state="disabled")
                button.invoke()
                calls.assert_not_called()
                button.configure(state="normal", text="立即检查测试")
                button.invoke()
                calls.assert_called_once()
                add = AddMemberDialog(ui.root, engine, ui.px, lambda: None)
                add.update_idletasks()
                add.query_var.set("synthetic-query")
                with patch.object(engine.dispatcher, "submit", side_effect=lambda task: task() or Mock()), \
                     patch.object(engine.dispatcher, "post", side_effect=lambda callback: callback()), \
                     patch.object(engine.application, "resolve", side_effect=RuntimeError("synthetic-secret")):
                    add.do_search()
                    assert not add.searching
                    assert add.search_btn.cget("state") == "normal"
                    assert "重试" in add.preview_text.get() and "synthetic-secret" not in add.preview_text.get()
                add.query_var.set("changed-input")
                add.on_search_done({"room": 999}, query="old-input")
                assert "忽略" in add.preview_text.get()
                assert add.add_btn.cget("state") == "disabled"
                add.destroy()
                add.on_search_done(None)
                with patch.object(engine.dispatcher, "submit"):
                    sync = SyncMedalsDialog(ui.root, engine, ui.px, lambda: None)
                sync.update_idletasks()
                sync.show_fetch_error()
                assert sync.btn_retry.cget("state") == "normal"
                with patch.object(engine.dispatcher, "submit") as submit:
                    sync.btn_retry.invoke()
                    sync.btn_retry.invoke()
                    submit.assert_called_once()
                sync.on_no_credentials()
                with patch.object(ui, "open_settings") as login:
                    sync.btn_goto.invoke()
                    ui.root.update()
                    login.assert_called_once_with(focus_auth=True, scan=True)
                with patch.object(engine.dispatcher, "submit"):
                    sync = SyncMedalsDialog(ui.root, engine, ui.px, lambda: None)
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
