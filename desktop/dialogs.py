from .settings_layout import build_automation, build_system, build_auth
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import time

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None
from desktop.storage import load_config, read_json
from desktop.windows import is_autostart_enabled, set_autostart
from asoul_support.runtime import update_json, save_login
from .widgets import *


class SettingsDialog(tk.Toplevel):
    """现代卡片化系统设置面板"""

    def __init__(self, parent, engine, px, on_saved, focus_auth=False):
        super().__init__(parent)
        self.engine = engine
        self.px = px
        self.on_saved = on_saved
        p = self.px
        self.title("LiveSupport 系统设置")
        w, h = (p(580), p(630))
        self.geometry(f"{w}x{h}")
        self.minsize(p(520), p(450))
        self.configure(bg=BG_WINDOW)
        self.transient(parent)
        self.grab_set()
        center_window(self, parent, w, h, p)
        config, _ = load_config(self.engine.root)
        try:
            cookies = read_json(self.engine.root / "credentials.json", {})
        except RuntimeError:
            cookies = {}
        bottom_bar = tk.Frame(self, bg=BG_WINDOW, padx=p(20), pady=p(12))
        bottom_bar.pack(side="bottom", fill="x")
        tk.Frame(self, height=1, bg=BORDER_CARD).pack(side="bottom", fill="x")
        ModernButton(bottom_bar, text="保存设置", primary=True, command=self.do_save, px=p).pack(
            side="right"
        )
        ModernButton(bottom_bar, text="取消", primary=False, command=self.destroy, px=p).pack(
            side="right", padx=(0, p(8))
        )
        scroll_area = tk.Frame(self, bg=BG_WINDOW)
        scroll_area.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(scroll_area, bg=BG_WINDOW, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        container = tk.Frame(self.canvas, bg=BG_WINDOW, padx=p(20), pady=p(16))
        self.canvas_window = self.canvas.create_window((0, 0), window=container, anchor="nw")
        self.canvas.bind(
            "<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )
        container.bind(
            "<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        def _on_mousewheel(event):
            try:
                if self.canvas.winfo_exists():
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _bind_wheel(_=None):
            self.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_=None):
            self.unbind_all("<MouseWheel>")

        self.bind("<Enter>", _bind_wheel)
        self.bind("<Leave>", _unbind_wheel)
        self.bind("<Destroy>", lambda _: self.unbind_all("<MouseWheel>"))
        header = tk.Frame(container, bg=BG_WINDOW)
        header.pack(fill="x", pady=(0, p(14)))
        tk.Label(
            header, text="系统设置", font=(FONT_FAMILY, 15, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
        ).pack(anchor="w")
        tk.Label(
            header,
            text="自定义开播挂机自动化策略、Windows 提醒与登录凭证",
            font=(FONT_FAMILY, 9),
            bg=BG_WINDOW,
            fg=TEXT_MUTED,
        ).pack(anchor="w", pady=(p(2), 0))
        build_automation(self, container, config, p)
        build_system(self, container, config, p)
        build_auth(self, container, cookies, p, focus_auth)

    def set_auth_status(self, text, color):
        if hasattr(self, "status_label") and self.status_label.winfo_exists():
            self.status_label.configure(text=text, fg=color)

    def on_credentials_changed(self, *_):
        self.verified_pair = None
        self.set_auth_status("登录信息已修改，保存前将重新验证", TEXT_MUTED)

    def open_qr_login(self):
        from .qr_dialog import QrLoginDialog

        QrLoginDialog(self, self.engine, self.px, self.on_qr_login)

    def on_qr_login(self, cookies, account, *, context=None):
        if not self.winfo_exists():
            return
        options = {"context": context} if context is not None else {}
        save_login(
            cookies["SESSDATA"],
            cookies["bili_jct"],
            self.engine.root / "credentials.json",
            **options,
        )
        self.engine.reload_settings()
        self.sessdata_var.set(cookies["SESSDATA"])
        self.jct_var.set(cookies["bili_jct"])
        self.verified_pair = (cookies["SESSDATA"], cookies["bili_jct"])
        self.verified_at = time.monotonic()
        self.set_auth_status(f"扫码登录成功：{account}，已保存。", "#059669")
        self.on_saved()

    def do_verify_login(self, on_success=None):
        if getattr(self, "verifying", False):
            return
        s = self.sessdata_var.get().strip()
        j = self.jct_var.get().strip()
        if not s or not j:
            self.set_auth_status("⚠️ 请先完整输入 SESSDATA 与 bili_jct 再进行验证", "#d97706")
            return
        self.btn_verify.configure(state="disabled")
        self.verifying = True
        self.verified_pair = None
        self.set_auth_status("⏳ 正在请求 B 站认证接口，验证凭证有效性…", TEXT_MUTED)

        def check_thread():
            try:
                ok, msg = self.engine.application.validate_credentials(s, j)
            except Exception as exc:
                # UI boundary: always release the busy state without exposing request data.
                ok, msg = False, f"登录验证异常（{type(exc).__name__}），请重试"

            def on_res():
                if (
                    self.winfo_exists()
                    and hasattr(self, "btn_verify")
                    and self.btn_verify.winfo_exists()
                ):
                    self.btn_verify.configure(state="normal")
                    self.verifying = False
                    if (self.sessdata_var.get().strip(), self.jct_var.get().strip()) != (s, j):
                        self.set_auth_status(
                            "登录信息已修改，本次验证结果已忽略，请重新验证", TEXT_MUTED
                        )
                        return
                    if ok:
                        self.verified_pair = (s, j)
                        self.verified_at = time.monotonic()
                        self.set_auth_status(f"🟢 验证通过：{msg}。点击保存后才会应用。", "#059669")
                        if on_success:
                            on_success()
                    else:
                        self.set_auth_status(
                            f"🔴 验证失败：{msg}（请确认 Cookie 是否过期或复制完整）", "#dc2626"
                        )

            self.engine.dispatcher.post(on_res)

        self.engine.dispatcher.submit(check_thread)

    def _scroll_to_auth(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)
        if hasattr(self, "e_sess"):
            self.e_sess.focus_set()
            self.e_sess.selection_range(0, "end")
        if hasattr(self, "card_auth"):
            self.card_auth.configure(highlightbackground=ACCENT_BLUE, highlightthickness=2)
            self.after(
                2500,
                lambda: (
                    self.card_auth.configure(highlightbackground=BORDER_CARD, highlightthickness=1)
                    if self.card_auth.winfo_exists()
                    else None
                ),
            )

    def do_save(self):
        try:
            interval = int(self.interval_var.get().strip())
            if not 1 <= interval <= 1440:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "检查间隔需为 1~1440 之间的整数（分钟）", parent=self)
            return
        new_sess = self.sessdata_var.get().strip()
        new_jct = self.jct_var.get().strip()
        if bool(new_sess) != bool(new_jct):
            messagebox.showwarning(
                "凭证不完整",
                "SESSDATA 与 bili_jct 必须同时填写！\n若需清空凭证，请将两项均留空。",
                parent=self,
            )
            return
        if new_sess and (
            self.verified_pair != (new_sess, new_jct)
            or time.monotonic() - getattr(self, "verified_at", 0) > 120
        ):
            self.do_verify_login(on_success=self.do_save)
            return
        changes = {
            "auto_revive": self.var_auto_revive.get(),
            "auto_danmaku_intimacy": self.var_auto_danmu.get(),
            "auto_like": self.var_auto_like.get(),
            "notify_on_live": self.var_notify.get(),
            "check_minutes": interval,
        }

        def change(settings):
            settings = {**settings, **changes}
            settings.pop("danmaku", None)
            settings.pop("live_likes", None)
            return settings

        try:
            save_login(new_sess, new_jct, self.engine.root / "credentials.json")
            update_json(self.engine.root / "settings.json", change, {})
            self.engine.reload_settings()
        except (OSError, ValueError, RuntimeError):
            messagebox.showerror(
                "保存失败", "请检查本机文件权限和配置，设置尚未全部应用。", parent=self
            )
            return
        if not set_autostart(self.var_autostart.get()):
            messagebox.showwarning(
                "部分设置未应用", "设置已保存，但 Windows 自启动设置失败。", parent=self
            )
        self.on_saved()
        self.destroy()


class AddMemberDialog(tk.Toplevel):
    """现代卡片化添加主播面板"""

    def __init__(self, parent, engine, px, on_added):
        super().__init__(parent)
        self.engine = engine
        self.px = px
        self.on_added = on_added
        self.resolved_info = None
        p = self.px
        self.title("添加监控主播")
        w, h = (p(490), p(360))
        self.geometry(f"{w}x{h}")
        self.minsize(p(450), p(320))
        self.configure(bg=BG_WINDOW)
        self.transient(parent)
        self.grab_set()
        center_window(self, parent, w, h, p)
        container = tk.Frame(self, bg=BG_WINDOW, padx=p(20), pady=p(18))
        container.pack(fill="both", expand=True)
        tk.Label(
            container,
            text="添加监控主播",
            font=(FONT_FAMILY, 14, "bold"),
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
        ).pack(anchor="w")
        tk.Label(
            container,
            text="支持输入房间长号、短号、主播 UID 或直播间链接",
            font=(FONT_FAMILY, 9),
            bg=BG_WINDOW,
            fg=TEXT_MUTED,
        ).pack(anchor="w", pady=(p(2), p(12)))
        input_card = CardFrame(container, px=p, pady=10)
        input_card.pack(fill="x", pady=(0, p(12)))
        self.last_query = ""
        self.query_var = tk.StringVar()
        entry = tk.Entry(
            input_card,
            textvariable=self.query_var,
            font=(FONT_FAMILY, 10),
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
            highlightthickness=1,
            highlightbackground=BORDER_CARD,
            bd=0,
        )
        entry.pack(side="left", fill="x", expand=True, ipady=p(4), padx=(0, p(8)))
        entry.focus()

        def on_enter(_):
            q = self.query_var.get().strip()
            if self.resolved_info and q == self.last_query:
                self.do_add()
            else:
                self.do_search()

        entry.bind("<Return>", on_enter)
        self.query_var.trace_add("write", lambda *_: self.on_query_changed())
        self.search_btn = ModernButton(
            input_card,
            text="识别查询",
            primary=True,
            accent=ACCENT_BLUE,
            accent_hover=ACCENT_BLUE_HOVER,
            command=self.do_search,
            px=p,
        )
        self.search_btn.pack(side="right")
        self.preview_card = CardFrame(container, px=p, pady=12)
        self.preview_card.pack(fill="both", expand=True, pady=(0, p(12)))
        self.preview_text = tk.StringVar(value="💡 请在上方输入主播信息并点击识别查询")
        self.preview_label = tk.Label(
            self.preview_card,
            textvariable=self.preview_text,
            justify="left",
            font=(FONT_FAMILY, 9),
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self.preview_label.pack(anchor="w")
        btn_row = tk.Frame(container, bg=BG_WINDOW)
        btn_row.pack(fill="x")
        self.add_btn = ModernButton(
            btn_row, text="确认添加", primary=True, command=self.do_add, px=p, state="disabled"
        )
        self.add_btn.pack(side="right")
        ModernButton(btn_row, text="取消", primary=False, command=self.destroy, px=p).pack(
            side="right", padx=(0, p(8))
        )

    def on_query_changed(self):
        if self.resolved_info and self.query_var.get().strip() != self.last_query:
            self.resolved_info = None
            self.add_btn.configure(state="disabled")
            self.preview_text.set("💡 输入已更改，请重新点击识别查询")
            self.preview_label.configure(fg=TEXT_MUTED)

    def do_search(self):
        query = self.query_var.get().strip()
        if not query:
            self.preview_text.set("⚠️ 请先输入房间号、UID 或直播间链接后再查询")
            self.preview_label.configure(fg="#d97706")
            return
        self.last_query = query
        self.search_btn.configure(state="disabled")
        self.preview_text.set("⏳ 正在查询 B 站接口…")
        self.preview_label.configure(fg=TEXT_MUTED)

        def query_thread():
            cookies = read_json(self.engine.root / "credentials.json", {})
            info = self.engine.application.resolve(query)
            self.engine.dispatcher.post(lambda: self.on_search_done(info))

        self.engine.dispatcher.submit(query_thread)

    def on_search_done(self, info):
        self.search_btn.configure(state="normal")
        if not info:
            self.preview_text.set("❌ 未查询到对应主播，请检查输入的房间号或 UID。")
            self.preview_label.configure(fg="#dc2626")
            self.add_btn.configure(state="disabled")
            self.resolved_info = None
            return
        members = read_json(self.engine.root / "members.json", [])
        is_existing = any((m.get("room") == info["room"] for m in members))
        medal = f"【{info['medal_name']}】" if info.get("medal_name") else "（暂无勋章）"
        text = f"👤 主播昵称： {info['name']}\n📺 直播房间： {info['room']}\n🆔 主播 UID： {info['uid']}\n🏅 粉丝勋章： {medal}"
        if is_existing:
            text += "\n\n⚠️ 该主播已在监控列表中，无需重复添加。"
            self.preview_text.set(text)
            self.preview_label.configure(fg=TEXT_MAIN)
            self.add_btn.configure(state="disabled")
            self.resolved_info = None
        else:
            self.resolved_info = info
            self.preview_text.set(text)
            self.preview_label.configure(fg=TEXT_MAIN)
            self.add_btn.configure(state="normal")

    def do_add(self):
        if not self.resolved_info:
            return
        members = read_json(self.engine.root / "members.json", [])
        if any((m.get("room") == self.resolved_info["room"] for m in members)):
            messagebox.showwarning("提示", "该主播已在监控列表中！", parent=self)
            return
        try:
            self.engine.application.add_members([self.resolved_info])
        except ValueError as exc:
            messagebox.showerror("添加失败", str(exc), parent=self)
            return
        self.on_added()
        self.destroy()


class SyncMedalsDialog(tk.Toplevel):
    """现代卡片化一键同步粉丝牌面板"""

    def __init__(self, parent, engine, px, on_synced):
        super().__init__(parent)
        self.parent = parent
        self.engine = engine
        self.px = px
        self.on_synced = on_synced
        self.items_data = []
        p = self.px
        self.title("一键同步我的所有粉丝牌")
        w, h = (p(580), p(450))
        self.geometry(f"{w}x{h}")
        self.minsize(p(520), p(400))
        self.configure(bg=BG_WINDOW)
        self.transient(parent)
        self.grab_set()
        center_window(self, parent, w, h, p)
        container = tk.Frame(self, bg=BG_WINDOW, padx=p(20), pady=p(18))
        container.pack(fill="both", expand=True)
        tk.Label(
            container,
            text="同步粉丝牌主播",
            font=(FONT_FAMILY, 14, "bold"),
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
        ).pack(anchor="w")
        self.status_var = tk.StringVar(value="正在拉取您的全部粉丝牌列表…")
        tk.Label(
            container,
            textvariable=self.status_var,
            font=(FONT_FAMILY, 9),
            bg=BG_WINDOW,
            fg=TEXT_MUTED,
        ).pack(anchor="w", pady=(p(2), p(10)))
        card = CardFrame(container, px=p, padx=1, pady=1)
        card.pack(fill="both", expand=True, pady=(0, p(12)))
        self.tree = ttk.Treeview(
            card, columns=("sel", "name", "room", "medal"), show="headings", height=7
        )
        self.tree.heading("sel", text="选择")
        self.tree.heading("name", text="主播名称")
        self.tree.heading("room", text="直播间")
        self.tree.heading("medal", text="粉丝牌")
        self.tree.column("sel", width=p(50), minwidth=p(50), stretch=False, anchor="center")
        self.tree.column("name", width=p(150), minwidth=p(120), stretch=True, anchor="w")
        self.tree.column("room", width=p(110), minwidth=p(100), stretch=False, anchor="center")
        self.tree.column("medal", width=p(150), minwidth=p(130), stretch=True, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Button-1>", self.on_click_item)
        self.tree.bind("<Double-1>", lambda e: self.on_click_item(e))
        self.tree.bind("<space>", lambda _: self.on_space_key())
        self.btn_row = tk.Frame(container, bg=BG_WINDOW)
        self.btn_row.pack(fill="x")
        self.btn_select_all = ModernButton(
            self.btn_row, text="全选", command=self.toggle_all, px=p, state="disabled"
        )
        self.btn_select_all.pack(side="left")
        self.btn_import = ModernButton(
            self.btn_row,
            text="导入选中主播",
            primary=True,
            command=self.do_import,
            px=p,
            state="disabled",
        )
        self.btn_import.pack(side="right")
        self.btn_cancel = ModernButton(
            self.btn_row, text="取消", primary=False, command=self.destroy, px=p
        )
        self.btn_cancel.pack(side="right", padx=(0, p(8)))
        self.engine.dispatcher.submit(self.fetch_medals)

    def on_space_key(self):
        item_id = self.tree.focus()
        if item_id:
            self.toggle_item(item_id)

    def toggle_item(self, item_id):
        if not item_id:
            return
        entry = next((e for e in self.items_data if e["item_id"] == item_id), None)
        if entry:
            entry["checked"] = not entry["checked"]
            new_sym = "☑" if entry["checked"] else "☐"
            vals = list(self.tree.item(item_id, "values"))
            vals[0] = new_sym
            self.tree.item(item_id, values=vals)

    def on_no_credentials(self):
        self.status_var.set("⚠️ 尚未配置登录凭证，请先设置登录！")
        self.btn_goto = ModernButton(
            self.btn_row,
            text="🔑 前往配置凭证",
            primary=True,
            command=self.open_settings_and_close,
            px=self.px,
        )
        self.btn_goto.pack(side="left", padx=(self.px(8), 0))

    def open_settings_and_close(self):
        self.destroy()
        if hasattr(self.parent, "open_settings"):
            self.parent.open_settings(focus_auth=True)

    def fetch_medals(self):
        cookies = read_json(self.engine.root / "credentials.json", {})
        if not cookies.get("SESSDATA") or not cookies.get("bili_jct"):
            self.engine.dispatcher.post(self.on_no_credentials)
            return
        try:
            all_medals = self.engine.application.medals()
        except (OSError, ValueError, RuntimeError):
            self.engine.dispatcher.post(self.show_fetch_error)
            return
        current_members = read_json(self.engine.root / "members.json", [])
        current_rooms = {m["room"] for m in current_members}
        unmonitored = [m for m in all_medals if m["room"] not in current_rooms]
        self.engine.dispatcher.post(lambda: self.display_medals(unmonitored, len(all_medals)))

    def display_medals(self, unmonitored, total):
        if not self.winfo_exists():
            return
        if total == 0:
            self.status_var.set(
                "当前账号未查询到任何粉丝勋章（请确认登录凭证有效且账号拥有粉丝牌）。"
            )
            self.btn_cancel.configure(text="关闭")
            return
        if not unmonitored:
            self.status_var.set(f"您拥有的全部 {total} 个粉丝牌主播均已在监控列表中！")
            self.btn_cancel.configure(text="关闭")
            return
        self.status_var.set(
            f"发现 {len(unmonitored)} 位未监控主播，勾选后点击导入即可开启自动监控："
        )
        self.btn_select_all.configure(state="normal")
        self.btn_import.configure(state="normal")
        self.items_data = []
        for m in unmonitored:
            item_id = str(m["room"])
            self.items_data.append({"item_id": item_id, "checked": True, "data": m})
            medal_str = f"{m['medal_name']} Lv{m['level']}"
            self.tree.insert("", "end", iid=item_id, values=("☑", m["name"], m["room"], medal_str))

    def show_fetch_error(self):
        if self.winfo_exists():
            self.status_var.set("查询失败，请检查登录和网络后重新打开。")
            self.btn_cancel.configure(text="关闭")

    def on_click_item(self, event):
        item_id = self.tree.identify_row(event.y)
        self.toggle_item(item_id)

    def toggle_all(self):
        if not self.items_data:
            return
        any_unchecked = any((not e["checked"] for e in self.items_data))
        new_state = any_unchecked
        new_sym = "☑" if new_state else "☐"
        for e in self.items_data:
            e["checked"] = new_state
            vals = list(self.tree.item(e["item_id"], "values"))
            vals[0] = new_sym
            self.tree.item(e["item_id"], values=vals)

    def do_import(self):
        selected = [e["data"] for e in self.items_data if e["checked"]]
        if not selected:
            messagebox.showinfo("提示", "请先勾选需要导入的主播！", parent=self)
            return
        try:
            self.engine.application.add_members(selected)
        except ValueError as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        messagebox.showinfo("导入成功", f"成功导入 {len(selected)} 位主播到监控列表！", parent=self)
        self.on_synced()
        self.destroy()
