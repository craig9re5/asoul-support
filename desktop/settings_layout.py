import tkinter as tk
from .widgets import *
from .windows import is_autostart_enabled


def build_automation(self, container, config, p):
    tk.Label(
        container, text="自动任务", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    card_auto = CardFrame(container, px=p)
    card_auto.pack(fill="x", pady=(0, p(14)))
    self.var_auto_revive = tk.BooleanVar(value=bool(config.get("auto_revive", True)))
    create_setting_row(
        card_auto,
        "自动复活点亮粉丝牌",
        "粉丝牌熄灭时，自动发 10 条弹幕重新点亮",
        lambda r: ToggleSwitch(r, variable=self.var_auto_revive, px=p),
        px=p,
    )
    create_divider(card_auto, px=p)
    self.var_auto_danmu = tk.BooleanVar(value=bool(config.get("auto_danmaku_intimacy", True)))
    create_setting_row(
        card_auto,
        "自动完成每日弹幕任务",
        "按剩余进度发送，自动确认是否完成",
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
        "默认关闭。实验性，接口成功不等于任务完成",
        lambda r: ToggleSwitch(r, variable=self.var_auto_like, px=p),
        px=p,
    )


def build_system(self, container, config, p):
    tk.Label(
        container, text="系统", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    card_sys = CardFrame(container, px=p)
    card_sys.pack(fill="x", pady=(0, p(14)))
    self.var_notify = tk.BooleanVar(value=bool(config.get("notify_on_live", True)))
    create_setting_row(
        card_sys,
        "开播通知",
        "开播时在屏幕右下角提醒",
        lambda r: ToggleSwitch(r, variable=self.var_notify, px=p),
        px=p,
    )
    create_divider(card_sys, px=p)
    self.var_autostart = tk.BooleanVar(value=bool(is_autostart_enabled()))
    create_setting_row(
        card_sys,
        "开机自动启动",
        "开机后在托盘静默运行",
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
        "检查频率",
        "多久检查一次是否开播，推荐 15~30 分钟",
        make_interval_box,
        px=p,
    )


def build_auth(self, container, cookies, p, focus_auth):
    """QR-only login: credentials are never typed or revealed in the UI."""
    tk.Label(
        container, text="B 站登录", font=(FONT_FAMILY, 10, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(anchor="w", pady=(0, p(4)))
    self.card_auth = CardFrame(container, px=p)
    self.card_auth.pack(fill="x", pady=(0, p(14)))
    row_login = tk.Frame(self.card_auth, bg=BG_CARD)
    row_login.pack(fill="x", pady=p(4))
    ModernButton(row_login, text="扫码登录", primary=True, command=self.open_qr_login, px=p).pack(
        side="left"
    )
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
        self.set_auth_status("🟢 已保存登录，可重新扫码更换账号", "#059669")
    else:
        self.set_auth_status("🔴 尚未登录，请点击【扫码登录】", "#dc2626")
    if focus_auth:
        self.after(120, self._scroll_to_auth)
