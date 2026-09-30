from .tray_layout import configure_table_style, build_header, build_table, build_controls
from desktop.dispatch import Dispatcher
import os
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
from .dialogs import SettingsDialog, AddMemberDialog, SyncMedalsDialog


class TrayUI:

    def __init__(self, engine, show=False):
        self.engine = engine
        self.commands = queue.Queue()
        self.rows_cache = {}
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        self.root = tk.Tk()
        self.engine.dispatcher = Dispatcher(self.root)
        self.root.bind(
            "<<BackgroundActionFailed>>",
            lambda _: messagebox.showerror(
                "执行失败", "后台操作失败，请查看日志并重试", parent=self.root
            ),
        )
        self.scale = self.root.winfo_fpixels("1i") / 96.0
        self.px = lambda value: max(1, round(value * self.scale))
        p = self.px
        self.root.title("LiveSupport · 直播助手")
        w, h = (p(990), p(550))
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(p(920), p(480))
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.root.configure(bg=BG_WINDOW)
        self.closed = False
        center_window(self.root, None, w, h, p)
        configure_table_style(p)
        body = tk.Frame(self.root, bg=BG_WINDOW, padx=p(18), pady=p(16))
        body.pack(fill="both", expand=True)
        build_header(self, body, p)
        build_table(self, body, p)
        build_controls(self, body, p)
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
        self.show()
        AddMemberDialog(self.root, self.engine, self.px, lambda: self.commands.put("check"))

    def open_sync_medals(self):
        self.show()
        SyncMedalsDialog(self.root, self.engine, self.px, lambda: self.commands.put("check"))

    def open_settings(self, focus_auth=False, scan=False):
        self.show()
        dialog = SettingsDialog(
            self.root,
            self.engine,
            self.px,
            lambda: self.commands.put("check"),
            focus_auth=focus_auth,
        )
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
            self.menu.post(event.x_root, event.y_root)
        else:
            self.tree.selection_remove(self.tree.selection())

    def on_open_room(self):
        selected = self.tree.selection()
        if selected and selected[0] != "_empty":
            webbrowser.open(f"https://live.bilibili.com/{selected[0]}")

    def on_redo_task(self, task_type):
        selected = self.tree.selection()
        if not selected or selected[0] == "_empty":
            return
        room_id = int(selected[0])
        row = self.rows_cache.get(str(room_id))
        if not row:
            return
        uid = row.get("uid")
        name = row.get("name", "")
        cookies = read_json(self.engine.root / "credentials.json", {})
        if not cookies.get("SESSDATA") or not cookies.get("bili_jct"):
            messagebox.showwarning(
                "提示", "尚未配置有效凭证！请先在【⚙️ 系统设置】中配置凭证。", parent=self.root
            )
            return
        self.summary.set(f"正在为【{name}】执行补齐任务…")

        def task_thread():
            try:
                res = self.engine.application.redo(room_id, uid, task_type)
            except Exception as exc:
                res = {"success": False, "error": f"执行失败（{type(exc).__name__}）"}
            self.commands.put(("task_done", name, res))

        self.engine.dispatcher.submit(task_thread)

    def on_wear_medal(self):
        selected = self.tree.selection()
        if not selected or selected[0] == "_empty":
            return
        room_id = int(selected[0])
        row = self.rows_cache.get(str(room_id))
        if not row:
            return
        uid = row.get("uid")
        cookies = read_json(self.engine.root / "credentials.json", {})
        if not cookies.get("SESSDATA") or not cookies.get("bili_jct"):
            messagebox.showwarning(
                "提示", "尚未配置有效凭证！请先在【⚙️ 系统设置】中配置凭证。", parent=self.root
            )
            return

        def wear_thread():
            medals = self.engine.application.call(
                "get_my_medals", *self.engine.application.credentials()
            )
            info = medals.get(uid) or medals.get(str(uid))
            if not info or not info.get("medal_id"):
                self.commands.put(("wear_done", row.get("name", ""), "no_medal"))
                return
            ok = self.engine.application.call(
                "wear_medal", info["medal_id"], *self.engine.application.credentials()
            )
            self.commands.put(("wear_done", row.get("name", ""), "ok" if ok else "fail"))

        self.engine.dispatcher.submit(wear_thread)

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
        self.engine.application.remove_member(room_id)
        self.commands.put("check")

    def refresh(self):
        if self.closed:
            return
        self._read_commands()
        if self.closed:
            return
        snap = self.engine.snapshot()
        self._render_overview(snap)
        self._render_rows(snap)
        self._render_footer(snap)
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
                if time.time() - request.get("created", 0) < 60:
                    self.commands.put(request.get("command"))
            finally:
                path.unlink(missing_ok=True)
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
                    self.engine.check_now()
                elif action == "wear_done":
                    _, name, res = cmd
                    if res == "ok":
                        self.summary.set(f"已佩戴【{name}】粉丝牌！")
                    elif res == "no_medal":
                        self.summary.set(f"未拥有【{name}】的粉丝勋章，无法佩戴")
                    else:
                        self.summary.set(f"佩戴【{name}】粉丝牌失败，请稍后重试")
                    self.engine.check_now()
                continue
            if cmd == "exit":
                self.closed = True
                self.engine.close()
                self.tray.stop()
                self.root.destroy()
                return
            if cmd == "show":
                self.show()
            elif cmd in {"toggle", "pause", "resume"}:
                self.engine.set_paused(
                    not self.engine.paused if cmd == "toggle" else cmd == "pause"
                )
                self.tray.update_menu()
            elif cmd == "check":
                self.engine.check_now()
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

        def recover():
            ok, message = self.engine.resume_safety(confirmed=True)
            self.engine.dispatcher.post(
                lambda: messagebox.showinfo("账号保护", message, parent=self.root)
            )

        self.engine.dispatcher.submit(recover)

    def _render_overview(self, snap):
        active = sum((row["active"] for row in snap["rows"]))
        title = "已暂停" if snap["paused"] else f"{active} 个直播间挂机中" if active else "等待开播"
        if snap["error"]:
            title = "需要处理"
        self.summary.set(
            snap["error"]
            or f"{title} · 共 {len(snap['rows'])} 个关注直播间"
            + (" · 正在检查…" if snap["checking"] else "")
        )
        notice, until = getattr(self, "task_notice", ("", 0))
        if time.time() < until:
            self.summary.set(notice)
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
        color = "#f2ab55" if snap["error"] else "#9ca9af" if snap["paused"] else "#63d4b2"
        if getattr(self, "last_color", None) != color:
            self.tray.icon = icon_image(color)
            self.last_color = color
        self.pause_button.configure(text="恢复挂机" if snap["paused"] else "暂停挂机")

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
                    icon = "🏅" if is_lighted else "⚪"
                    if next_int and next_int > 0:
                        pct = int(intimacy / next_int * 100)
                        medal_str = f"{icon}{medal_name} Lv{level} ({intimacy}/{next_int}, {pct}%)"
                    else:
                        medal_str = f"{icon}{medal_name} Lv{level}"
                else:
                    medal_str = "—"
                tasks = row.get("tasks", [])
                tasks_str = (
                    "进度待更新"
                    if row.get("tasks_stale")
                    else format_task_mini_badge(tasks, is_lighted, has_medal=bool(medal_name))
                )
                live_dur = row.get("live_duration", "")
                if row.get("active"):
                    minutes = max(0, int((time.time() - (row.get("started") or time.time())) / 60))
                    phase_str = f"{row['phase']} ({minutes}m)" + (
                        f" · {live_dur}" if live_dur else ""
                    )
                    if row.get("task_error"):
                        phase_str += " · 任务待补齐"
                elif is_live:
                    phase_str = row["phase"] + (f" ({live_dur})" if live_dur else "")
                else:
                    phase_str = row["phase"]
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
        hold = snap.get("safety", {})
        if hold.get("blocked"):
            until = hold.get("until")
            suffix = (
                " · 最早恢复 " + time.strftime("%H:%M:%S", time.localtime(until))
                if until
                else " · 托盘菜单中选择“处理账号保护暂停”"
            )
            self.footer.set(hold["reason"] + suffix)
            return
        next_time = (
            time.strftime("%H:%M:%S", time.localtime(snap["next_check"]))
            if snap["next_check"]
            else "即将检查"
        )
        self.footer.set(
            "暂停会停止全部挂机。双击表格行直接在浏览器打开直播间，右键可进行补齐操作。"
            if snap["paused"]
            else f"下次检查：{next_time} · 双击表格行直达直播间 · 悬停可查看任务详情。"
        )
