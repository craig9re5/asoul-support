import tkinter as tk
import webbrowser
from .widgets import *
from .windows import is_autostart_enabled


def build_automation(self, container, config, p):
    tk.Label(
        container, text="开播自动化策略", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    card_auto = CardFrame(container, px=p)
    card_auto.pack(fill="x", pady=(0, p(14)))
    self.var_auto_revive = tk.BooleanVar(value=bool(config.get("auto_revive", True)))
    create_setting_row(
        card_auto,
        "自动复活点亮粉丝牌",
        "检测到勋章熄灭时，自动向房间发送 10 条应援弹幕复活点亮",
        lambda r: ToggleSwitch(r, variable=self.var_auto_revive, px=p),
        px=p,
    )
    create_divider(card_auto, px=p)
    self.var_auto_danmu = tk.BooleanVar(value=bool(config.get("auto_danmaku_intimacy", True)))
    create_setting_row(
        card_auto,
        "自动完成每日弹幕任务",
        "按服务端剩余进度发送弹幕，巡检确认任务完成",
        lambda r: ToggleSwitch(r, variable=self.var_auto_danmu, px=p),
        px=p,
    )
    create_divider(card_auto, px=p)
    self.var_auto_like = tk.BooleanVar(
        value=bool(config.get("auto_like", config.get("live_likes", False)))
    )
    create_setting_row(
        card_auto,
        "直播间点赞（实验性）",
        "默认关闭；接口成功不代表任务已记账",
        lambda r: ToggleSwitch(r, variable=self.var_auto_like, px=p),
        px=p,
    )


def build_system(self, container, config, p):
    tk.Label(
        container, text="系统与提醒", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    card_sys = CardFrame(container, px=p)
    card_sys.pack(fill="x", pady=(0, p(14)))
    self.var_notify = tk.BooleanVar(value=bool(config.get("notify_on_live", True)))
    create_setting_row(
        card_sys,
        "开播桌面通知 (Toast)",
        "关注的主播开播时，在 Windows 屏幕右下角弹出气泡提醒",
        lambda r: ToggleSwitch(r, variable=self.var_notify, px=p),
        px=p,
    )
    create_divider(card_sys, px=p)
    self.var_autostart = tk.BooleanVar(value=bool(is_autostart_enabled()))
    create_setting_row(
        card_sys,
        "开机自动启动",
        "随 Windows 开机启动并在后台静默托盘运行",
        lambda r: ToggleSwitch(r, variable=self.var_autostart, px=p),
        px=p,
    )
    create_divider(card_sys, px=p)

    def make_interval_box(r):
        box = tk.Frame(r, bg=BG_CARD)
        self.interval_var = tk.StringVar(value=str(config.get("check_minutes", 30)))
        entry = tk.Entry(
            box,
            textvariable=self.interval_var,
            width=5,
            justify="center",
            font=(FONT_FAMILY, 9),
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
            highlightthickness=1,
            highlightbackground=BORDER_CARD,
            bd=0,
        )
        entry.pack(side="left")
        tk.Label(box, text=" 分钟", font=(FONT_FAMILY, 9), bg=BG_CARD, fg=TEXT_MUTED).pack(
            side="left"
        )
        return box

    create_setting_row(
        card_sys,
        "开播巡检频率",
        "后台轮询检查关注主播开播状态的时间间隔（推荐 15~30 分钟）",
        make_interval_box,
        px=p,
    )


def build_auth(self, container, cookies, p, focus_auth):
    tk.Label(
        container, text="B 站登录凭证", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    self.card_auth = CardFrame(container, px=p)
    self.card_auth.pack(fill="x", pady=(0, p(14)))
    self.sessdata_var = tk.StringVar(value=cookies.get("SESSDATA", ""))
    self.jct_var = tk.StringVar(value=cookies.get("bili_jct", ""))
    self.verified_pair = None
    self.sessdata_var.trace_add("write", self.on_credentials_changed)
    self.jct_var.trace_add("write", self.on_credentials_changed)
    self.e_sess = credential_entry(self.card_auth, "SESSDATA", self.sessdata_var, p)
    self.e_jct = credential_entry(self.card_auth, "bili_jct", self.jct_var, p)
    row_actions = tk.Frame(self.card_auth, bg=BG_CARD)
    row_actions.pack(fill="x", pady=(p(6), p(2)))
    self.btn_verify = ModernButton(
        row_actions, text="🔍 验证登录凭证", command=self.do_verify_login, px=p
    )
    self.btn_verify.pack(side="left")
    row_login = tk.Frame(self.card_auth, bg=BG_CARD)
    row_login.pack(fill="x", pady=p(4))
    ModernButton(row_login, text="扫码登录", primary=True, command=self.open_qr_login, px=p).pack(
        side="left", padx=(0, p(6))
    )
    ModernButton(
        row_actions,
        text="🌐 打开 B 站主页",
        command=lambda: webbrowser.open("https://www.bilibili.com"),
        px=p,
    ).pack(side="left", padx=(p(6), 0))
    self.status_label = tk.Label(
        self.card_auth,
        text="",
        font=(FONT_FAMILY, 9),
        bg=BG_CARD,
        fg=TEXT_MUTED,
        anchor="w",
        justify="left",
    )
    self.status_label.pack(fill="x", pady=(p(6), 0))
    if cookies.get("SESSDATA") and cookies.get("bili_jct"):
        self.set_auth_status(
            "⚪ 本地已保存凭证，点击【🔍 验证登录凭证】可在线检测有效性", TEXT_MUTED
        )
    else:
        self.set_auth_status("🔴 尚未登录，请点击【扫码登录】", "#dc2626")
    tk.Label(
        self.card_auth,
        text="推荐使用 B 站 App 扫码登录；确认后验证并保存到本机。",
        wraplength=p(480),
        font=(FONT_FAMILY, 8),
        bg=BG_CARD,
        fg=TEXT_MUTED,
    ).pack(anchor="w", pady=(p(4), 0))
    if focus_auth:
        self.after(120, self._scroll_to_auth)


def credential_entry(parent, name, variable, p):
    row = tk.Frame(parent, bg=BG_CARD)
    row.pack(fill="x", pady=p(3))
    tk.Label(
        row, text=name, width=10, anchor="w", font=(FONT_FAMILY, 9), bg=BG_CARD, fg=TEXT_MUTED
    ).pack(side="left")
    entry = tk.Entry(
        row,
        textvariable=variable,
        show="●",
        font=(FONT_FAMILY, 9),
        bg=BG_WINDOW,
        fg=TEXT_MAIN,
        highlightthickness=1,
        highlightbackground=BORDER_CARD,
        bd=0,
    )
    entry.pack(side="left", fill="x", expand=True, ipady=p(2), padx=(0, p(6)))

    def toggle_sess():
        cur = entry.cget("show")
        entry.configure(show="" if cur else "●")
        button.configure(text="🔒" if not cur else "👁️")

    button = tk.Button(
        row,
        text="👁️",
        command=toggle_sess,
        font=(FONT_FAMILY, 8),
        bg=BG_CARD,
        fg=TEXT_MUTED,
        bd=0,
        relief="flat",
        cursor="hand2",
    )
    button.pack(side="right")
    return entry
