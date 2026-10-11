from .tray_layout import configure_table_style, build_room_menu
from .workbench import Workbench
from .presentation import phase_label
from .interaction import action_reason, recovery_route
from desktop.dispatch import Dispatcher
import os
import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
import webbrowser

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None
from desktop.storage import read_json
from .widgets import *
from .dialogs import AddMemberDialog, SyncMedalsDialog


class TrayUI:

    def __init__(self, engine, show=False):
        self.engine = engine
        self.commands = queue.Queue()
        self.rows_cache = {}
        self.room_actions = {}
        self.control_actions = set()
        self.control_messages = {}
        self.last_snapshot = None
        self.closing = False
        self.ui_error = ""
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        self.root = tk.Tk()
        self.root.report_callback_exception = self._callback_error
        self.engine.dispatcher = Dispatcher(self.root)
        self.root.bind(
            "<<BackgroundActionFailed>>",
            lambda _: messagebox.showerror(
                "执行失败", "后台操作失败，请查看日志并重试", parent=self.root
            ),
        )
        self.root.bind("<<OpenAccountLogin>>", lambda _: self.open_settings(focus_auth=True, scan=True))
        self.scale = self.root.winfo_fpixels("1i") / 96.0
        self.px = lambda value: max(1, round(value * self.scale))
        p = self.px
        self.root.title("LiveSupport · 直播助手")
        w, h = (min(p(1180), self.root.winfo_screenwidth() - p(40)),
                min(p(760), self.root.winfo_screenheight() - p(80)))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(min(p(980), w), min(p(620), h))
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.root.configure(bg=BG_WINDOW)
        self.closed = False
        center_window(self.root, None, w, h, p)
        configure_table_style(p)
        self.workbench = Workbench(self)
        build_room_menu(self)
        self.image = tk.PhotoImage(data=self._png_data())
        self.root.iconphoto(True, self.image)
        self.tray = pystray.Icon(
            "LiveSupport",
            icon_image(),
            "LiveSupport · 正在启动",
            pystray.Menu(
                pystray.MenuItem("查看状态", lambda: self.commands.put("show"), default=True),
                pystray.MenuItem(
                    lambda item: "恢复挂机" if self.engine.paused else "暂停挂机",
                    lambda: self.commands.put("toggle"),
                ),
                pystray.MenuItem("立即检查", lambda: self.commands.put("check")),
                pystray.MenuItem("处理账号保护暂停", lambda: self.commands.put("safety")),
                pystray.MenuItem("➕ 添加主播", lambda: self.commands.put("add_member")),
                pystray.MenuItem("📥 同步粉丝牌", lambda: self.commands.put("sync_medals")),
                pystray.MenuItem("⚙️ 系统设置", lambda: self.commands.put("settings")),
                pystray.MenuItem("📂 查看日志", lambda: self.commands.put("logs")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出（停止全部挂机）", lambda: self.commands.put("exit")),
            ),
        )
        threading.Thread(target=self.tray.run, name="tray", daemon=True).start()
        self.engine.notify_callback = lambda name, title: self.commands.put(("notify", name, title))
        if not show:
            self.root.withdraw()
        self.root.after(200, self.refresh)

    @staticmethod
    def _png_data():
        import base64
        import io

        stream = io.BytesIO()
        icon_image().save(stream, format="PNG")
        return base64.b64encode(stream.getvalue())

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after_idle(self.root.attributes, "-topmost", False)

    def open_add_member(self):
        if self.closing:
            return
        self.show()
        AddMemberDialog(self.root, self.engine, self.px, lambda: self.commands.put("check"))

    def open_sync_medals(self):
        if self.closing:
            return
        self.show()
        SyncMedalsDialog(self.root, self.engine, self.px, lambda: self.commands.put("check"))

    def open_settings(self, focus_auth=False, scan=False):
        if self.closing:
            return
        self.show()
        dialog = self.workbench.show_page("account" if focus_auth or scan else "automation")
        if scan:
            dialog.after_idle(dialog.open_qr_login)

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item == "_empty":
            self.open_add_member()
        elif item:
            webbrowser.open(f"https://live.bilibili.com/{item}")

    def on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and item != "_empty":
            self.tree.selection_set(item)
            self.workbench.render_detail()
            self.menu.post(event.x_root, event.y_root)
        else:
            self.tree.selection_remove(self.tree.selection())

    def _selected_action(self, action):
        selected = self.tree.selection()
        row = self.rows_cache.get(selected[0], {}) if selected else {}
        state = self.room_actions.get(row.get("room"), {})
        snap = self.last_snapshot or {}
        reason = action_reason({**snap, "closing": self.closing}, row, action, state.get("pending", False))
        if reason:
            self.task_notice = (reason, time.time() + 20)
            return None
        return row

    def _submit_room_action(self, row, kind, operation, *, control=False):
        room, name = row["room"], row["name"]
        self.room_actions[room] = {"kind": kind, "pending": True, "started": time.monotonic(),
                                   "message": {"redo": "正在补齐任务", "wear": "正在佩戴粉丝牌",
                                               "reconnect": "正在请求重连"}[kind]}
        if kind == "reconnect":
            self.reconnect_pending = True
        self.workbench.render_detail()
        def run():
            try:
                if self.closing or self.engine.paused:
                    message = "程序正在退出或挂机已暂停，尚未开始的操作已取消。"
                else:
                    message = operation()
            except Exception as exc:
                logging.error("Room action failed kind=%s error=%s", kind, type(exc).__name__)
                message = f"操作未成功（{type(exc).__name__}），请重试；登录失效可在账号管理扫码。"
            self.commands.put(("room_action_done", room, name, kind, message))
        submit = self.engine.dispatcher.submit_control if control else self.engine.dispatcher.submit
        if submit(run) is None:
            self.commands.put(("room_action_done", room, name, kind, "程序正在退出，操作未提交。"))

    def _submit_control(self, key, operation, message):
        if key in self.control_actions or self.closing and key != "exit":
            return
        self.control_actions.add(key)
        self.control_messages[key] = (message, time.monotonic())
        self.task_notice = (message, time.time() + 20)
        def run():
            try:
                returned = operation()
                ok, result = returned if isinstance(returned, tuple) and len(returned) == 2 and isinstance(returned[0], bool) else (True, message.replace("正在", "已"))
            except Exception as exc:
                logging.error("Desktop control failed action=%s error=%s", key, type(exc).__name__)
                ok, result = False, f"操作失败（{type(exc).__name__}），可重试或查看活动记录。"
            self.commands.put(("control_done", key, ok, result))
        if self.engine.dispatcher.submit_control(run) is None:
            self.commands.put(("control_done", key, False, "程序正在退出，操作未提交。"))

    def on_recovery_action(self):
        route = getattr(self, "recovery_target", {})
        action = route.get("action")
        if action == "login":
            self.open_settings(focus_auth=True, scan=True)
        elif action == "safety":
            self.on_safety_resume()
        elif action in ("resume", "check", "logs", "refresh"):
            self.commands.put(action)
        elif action == "room":
            self.workbench.show_page("monitor")
            self.tree.selection_set(str(route["room"]))
            self.workbench.detail_canvas.yview_moveto(0)
            self.workbench.render_detail()

    def on_open_room(self):
        selected = self.tree.selection()
        if selected and selected[0] != "_empty":
            webbrowser.open(f"https://live.bilibili.com/{selected[0]}")

    def on_redo_task(self, task_type):
        row = self._selected_action("redo")
        if not row:
            return
        self._submit_room_action(row, "redo", lambda: format_task_result(
            row["name"], self.engine.application.redo(row["room"], row.get("uid"), task_type)))

    def on_reconnect_room(self):
        row = self._selected_action("reconnect")
        if not row:
            return
        self._submit_room_action(row, "reconnect", lambda: self.engine.reconnect_room(row["room"])[1], control=True)

    def on_wear_medal(self):
        row = self._selected_action("wear")
        if not row:
            return
        def wear_thread():
            uid = row.get("uid")
            medals = self.engine.application.call(
                "get_my_medals", *self.engine.application.credentials()
            )
            info = medals.get(uid) or medals.get(str(uid))
            if not info or not info.get("medal_id"):
                return "没有可佩戴的粉丝牌，请先同步粉丝牌。"
            ok = self.engine.application.call(
                "wear_medal", info["medal_id"], *self.engine.application.credentials()
            )
            return "粉丝牌已佩戴。" if ok else "佩戴失败，请核对登录状态后重试。"
        self._submit_room_action(row, "wear", wear_thread)

    def on_remove_member(self):
        selected = self.tree.selection()
        if not selected or selected[0] == "_empty":
            return
        room_id = int(selected[0])
        row = self.rows_cache.get(str(room_id))
        name = row.get("name", "") if row else str(room_id)
        if not messagebox.askyesno(
            "移除主播",
            f"确定从关注列表中移除【{name}】（房间号：{room_id}）吗？\n移除后将不再对此直播间执行挂机与亲密度任务。",
            parent=self.root,
        ):
            return
        self._submit_control("remove", lambda: (self.engine.application.remove_member(room_id),
                                              self.engine.check_now()), "正在移除主播…")

    def _callback_error(self, kind, value, traceback):
        logging.error("Tk callback failed", exc_info=(kind, value, traceback))
        self.ui_error = "界面操作失败，请重试界面。"
        self.summary.set(self.ui_error)

    def refresh(self):
        if self.closed:
            return
        try:
            self._read_commands()
            if self.closed:
                return
            snap = self.engine.snapshot(blocking=False)
            if snap is None:
                if self.last_snapshot is None:
                    self.summary.set("后台正在启动，界面可继续操作。")
                    return
                snap = {**self.last_snapshot, "engine_busy": True}
            else:
                snap["engine_busy"] = False
            snap["closing"] = self.closing
            snap["ui_error"] = self.ui_error
            self.last_snapshot = snap
            self._render_overview(snap)
            self._render_rows(snap)
            self.workbench.render(snap)
            self._render_footer(snap)
            self._notify_watch_warnings(snap)
        except Exception:
            logging.exception("Desktop refresh failed")
            self.ui_error = "界面刷新失败，正在自动重试。"
            self.summary.set("界面刷新失败，稍后自动重试；请查看日志")
            # Preserve a visible recovery entry even when rendering itself failed.
            if isinstance(getattr(self, "workbench", None), Workbench):
                self.recovery_target = recovery_route({"ui_error": self.ui_error})
                self.safety_button.configure(text="重试界面", state="normal")
                if not self.safety_button.winfo_manager():
                    self.safety_button.pack(side="right", before=self.pause_button, padx=(self.px(6), 0))
        finally:
            if not self.closed:
                self.root.after(1000, self.refresh)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.engine.dispatcher.close()
            if not self.closed:
                self.engine.close()
                self.tray.stop()

    def _read_commands(self):
        for path in (self.engine.root / "commands").glob("*.json"):
            try:
                request = read_json(path, {})
                if not isinstance(request, dict):
                    raise ValueError("Command must be an object")
                age = time.time() - request.get("created", 0)
                if 0 <= age < 60:
                    self.commands.put(request.get("command"))
            except (OSError, ValueError, TypeError):
                logging.warning("Ignoring unreadable desktop command")
            finally:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logging.warning("Cannot remove processed desktop command")
        while not self.commands.empty():
            cmd = self.commands.get_nowait()
            if isinstance(cmd, tuple):
                action = cmd[0]
                if action == "notify":
                    _, name, title = cmd
                    try:
                        self.tray.notify(
                            f"【{name}】开播了：{title}", title="LiveSupport · 开播提醒"
                        )
                    except Exception:
                        pass
                elif action == "task_done":
                    _, name, res = cmd
                    self.task_notice = (format_task_result(name, res), time.time() + 20)
                    self.commands.put("check")
                elif action == "reconnect_done":
                    _, name, ok, message = cmd
                    self.reconnect_pending = False
                    self.task_notice = (f"【{name}】{message}", time.time() + 20)
                elif action == "room_action_done":
                    _, room, name, kind, message = cmd
                    self.room_actions[room].update(pending=False, message=message)
                    if kind == "reconnect":
                        self.reconnect_pending = any(state.get("pending") and state.get("kind") == "reconnect"
                                                     for state in self.room_actions.values())
                    self.task_notice = (f"【{name}】{message}", time.time() + 20)
                    if kind != "reconnect":
                        self.commands.put("check")
                elif action == "control_done":
                    _, key, ok, message = cmd
                    self.control_actions.discard(key)
                    self.control_messages.pop(key, None)
                    self.task_notice = (message, time.time() + 20)
                    if key == "exit":
                        if ok:
                            self.closed = True
                            self.tray.stop()
                            self.root.destroy()
                            return
                        self.closing = False
                    self.tray.update_menu()
                elif action == "wear_done":
                    _, name, res = cmd
                    if res == "ok":
                        self.task_notice = (f"已佩戴【{name}】粉丝牌！", time.time() + 20)
                    elif res == "no_medal":
                        self.task_notice = (f"未拥有【{name}】的粉丝勋章，无法佩戴", time.time() + 20)
                    else:
                        self.task_notice = (f"佩戴【{name}】粉丝牌失败，请稍后重试", time.time() + 20)
                    self.commands.put("check")
                continue
            if self.closing and cmd not in {"exit", "show", "logs"}:
                continue
            if cmd == "exit":
                self.closing = True
                for panel in self.workbench.settings_pages.values():
                    panel.deactivate()
                def exit_cleanly():
                    self.engine.close()
                    self.engine.dispatcher.wait_for_io()
                self._submit_control("exit", exit_cleanly, "正在退出，等待已提交操作结束…")
                continue
            if cmd == "show":
                self.show()
            elif cmd == "refresh":
                self.ui_error = ""
            elif cmd in {"toggle", "pause", "resume"}:
                paused = not self.engine.paused if cmd == "toggle" else cmd == "pause"
                self._submit_control("pause", lambda value=paused: self.engine.set_paused(value),
                                     "正在暂停挂机…" if paused else "正在恢复挂机…")
            elif cmd == "check":
                self._submit_control("check", self.engine.check_now, "正在请求检查…")
            elif cmd == "add_member":
                self.open_add_member()
            elif cmd == "sync_medals":
                self.open_sync_medals()
            elif cmd == "settings":
                self.open_settings()
            elif cmd == "login":
                self.open_settings(focus_auth=True, scan=True)
            elif cmd == "logs":
                os.startfile(str(self.engine.root / "logs"))
            elif cmd == "safety":
                self.on_safety_resume()

    def on_safety_resume(self):
        hold = self.engine.application.safety_status()
        if not hold.get("blocked"):
            messagebox.showinfo("账号保护", "当前没有账号保护暂停。", parent=self.root)
            return
        if hold.get("kind") in ("auth", "credentials"):
            self.open_settings(focus_auth=True, scan=True)
            return
        if hold.get("until"):
            until = time.strftime("%H:%M:%S", time.localtime(hold["until"]))
            messagebox.showinfo(
                "账号冷却", f"{hold['reason']}\n最早恢复时间：{until}", parent=self.root
            )
            return
        if not messagebox.askyesno(
            "恢复账号操作",
            hold["reason"]
            + "\n\n请先在 B 站完成必要验证、处理限制或核对任务进度。确认已经处理后恢复？当天预算不会重置。",
            parent=self.root,
        ):
            return

        self._submit_control("safety", lambda: self.engine.resume_safety(confirmed=True), "正在检查账号并解除保护暂停…")

    def _render_overview(self, snap):
        active = sum(row.get("heartbeat_healthy", row["active"] and not row.get("heartbeat_stale")) for row in snap["rows"])
        stalled = sum(bool(row.get("heartbeat_stale")) for row in snap["rows"])
        connecting = sum(bool(row["active"] and not row.get("heartbeat_healthy", False)
                              and not row.get("heartbeat_stale")) for row in snap["rows"])
        warnings = sum(bool(row.get("watch_warning")) for row in snap["rows"])
        title = "已暂停" if snap["paused"] else f"{active} 个直播间挂机中" if active else "等待开播"
        if snap["error"]:
            title = "需要处理"
        elif stalled:
            title = "连接异常，请查看详情"
        elif connecting and not snap["paused"]:
            title = "正在建立看播连接"
        live = sum(row.get("live_status") == 1 for row in snap["rows"])
        self.summary.set(
            snap["error"]
            or f"关注 {len(snap['rows'])} · 直播 {live} · "
            + ("已暂停" if snap["paused"] else f"挂机 {active}")
            + (" · 正在检查…" if snap["checking"] else "")
            + (f" · {warnings} 个看播收益待核验" if warnings else "")
            + (f" · 连接异常 {stalled}" if stalled else "")
            + (f" · 连接中 {connecting}" if connecting and not snap["paused"] else "")
        )
        notice, until = getattr(self, "task_notice", ("", 0))
        if time.time() < until:
            self.summary.set(notice)
        if self.control_messages:
            key = next((key for key in ("exit", "pause", "safety", "remove", "check") if key in self.control_messages))
            message, started = self.control_messages[key]
            self.summary.set(message + f" · 已等待 {max(0, int(time.monotonic()-started))} 秒")
        self.tray.title = f"LiveSupport · {title}"
        account = snap.get("account", "")
        if account and snap.get("account_confirmed"):
            checked = time.strftime("%H:%M", time.localtime(snap.get("account_checked_at") or 0))
            self.account_label.configure(text=f"🟢 {account} · {checked} 验证", fg="#065f46")
            self.badge_frame.configure(bg="#ecfdf5", highlightbackground="#a7f3d0")
        elif account:
            self.account_label.configure(text="🟠 登录状态待确认", fg="#92400e")
            self.badge_frame.configure(bg="#fffbeb", highlightbackground="#fde68a")
        else:
            self.account_label.configure(text="🔴 尚未登录", fg="#991b1b")
            self.badge_frame.configure(bg="#fef2f2", highlightbackground="#fecaca")
        color = "#f2ab55" if snap["error"] or warnings or stalled else "#9ca9af" if snap["paused"] else "#63d4b2"
        if getattr(self, "last_color", None) != color:
            self.tray.icon = icon_image(color)
            self.last_color = color
        pause_pending = "pause" in self.control_actions
        self.pause_button.configure(text="正在处理…" if pause_pending else "恢复挂机" if snap["paused"] else "暂停挂机",
                                    state="disabled" if pause_pending or self.closing else "normal")
        self.workbench.check_button.configure(state="disabled" if self.closing or "check" in self.control_actions else "normal")
        self.recovery_target = recovery_route(snap)
        if self.recovery_target:
            self.safety_button.configure(text=self.recovery_target["label"],
                                         state="disabled" if self.closing or "safety" in self.control_actions else "normal")
            if not self.safety_button.winfo_manager():
                self.safety_button.pack(side="right", before=self.pause_button, padx=(self.px(6), 0))
        else:
            self.safety_button.configure(state="disabled")
            self.safety_button.pack_forget()

    def _render_rows(self, snap):
        self.rows_cache.clear()
        desired = {str(row["room"]) for row in snap["rows"]} or {"_empty"}
        for item in self.tree.get_children():
            if item not in desired:
                self.tree.delete(item)
        if not snap["rows"]:
            if self.tree.exists("_empty"):
                return
            self.tree.insert(
                "",
                "end",
                iid="_empty",
                values=(
                    "(暂无监控主播)",
                    "点击下方【➕ 添加主播】或【📥 同步粉丝牌】开启挂机",
                    "—",
                    "—",
                    "等待添加",
                    "—",
                ),
                tags=("placeholder",),
            )
        else:
            for idx, row in enumerate(snap["rows"]):
                iid = str(row["room"])
                self.rows_cache[iid] = row
                last = (
                    time.strftime("%H:%M:%S", time.localtime(row["last_heartbeat"]))
                    if row["last_heartbeat"]
                    else "—"
                )
                is_live = row.get("live_status") == 1
                name_str = f"[直播中] {row['name']}" if is_live else row["name"]
                t = row.get("title", "")
                a = row.get("area_name", "")
                if is_live:
                    content_str = f"[{a}] {t}" if a and t else t or a or "直播中"
                elif row.get("live_status") is None:
                    content_str = "直播状态待确认"
                elif t:
                    content_str = f"(未开播) {t}"
                else:
                    content_str = "—"
                medal_name = row.get("medal_name")
                level = row.get("medal_level")
                is_lighted = row.get("is_lighted", 0)
                intimacy = row.get("intimacy", 0)
                next_int = row.get("next_intimacy", 0)
                if medal_name and level:
                    medal_str = f"{medal_name} Lv.{level}"
                else:
                    medal_str = "—"
                tasks = row.get("tasks", [])
                tasks_str = (
                    "进度待更新"
                    if row.get("tasks_stale")
                    else format_task_mini_badge(tasks, is_lighted, has_medal=bool(medal_name))
                )
                phase_str = phase_label(row)
                if row.get("task_error") and row.get("active"):
                    phase_str += " · 任务待确认"
                if is_live:
                    row_tags = ("live",)
                elif idx % 2 == 1:
                    row_tags = ("odd",)
                else:
                    row_tags = ("even",)
                values = (name_str, content_str, medal_str, tasks_str, phase_str, last)
                if self.tree.exists(iid):
                    self.tree.item(iid, values=values, tags=row_tags)
                else:
                    self.tree.insert("", "end", iid=iid, values=values, tags=row_tags)
                self.tree.move(iid, "", idx)

    def _render_footer(self, snap):
        route = recovery_route(snap)
        if route:
            self.footer.set(route["message"] + f" · 点击“{route['label']}”")
            return
        next_time = (
            time.strftime("%H:%M:%S", time.localtime(snap["next_check"]))
            if snap["next_check"]
            else "即将检查"
        )
        self.footer.set(
            "监控已暂停"
            if snap["paused"]
            else f"下次检查：{next_time}"
        )

    def _notify_watch_warnings(self, snap):
        from asoul_support.runtime import task_day

        day = task_day()
        if getattr(self, "watch_notice_day", None) != day:
            self.watch_notice_day = day
            self.watch_notices = set()
        for row in snap["rows"]:
            connection = row.get("connection_warning")
            warning = connection or row.get("watch_warning")
            if not warning:
                continue
            watch = row.get("watch_progress", {})
            key = (row["room"], row.get("session_id") or row.get("started"),
                   ("connection", row.get("last_heartbeat")) if connection else
                   (watch.get("status"), watch.get("warning_since")))
            if key in self.watch_notices:
                continue
            try:
                self.tray.notify(f"【{row['name']}】{warning}", title="LiveSupport · 连接提醒" if connection else "LiveSupport · 看播收益提醒")
            except Exception:
                logging.exception("Watch reward notification failed")
            self.watch_notices.add(key)
