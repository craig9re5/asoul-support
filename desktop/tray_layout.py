import tkinter as tk
import os
from tkinter import ttk
from tkinter import font as tkfont
from .widgets import *
from asoul_support.runtime import APP_VERSION


def configure_table_style(p):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "Treeview",
        background=BG_CARD,
        fieldbackground=BG_CARD,
        foreground=TEXT_MAIN,
        rowheight=max(p(34), tkfont.Font(family=FONT_FAMILY, size=10).metrics("linespace") + p(14)),
        font=(FONT_FAMILY, 10),
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background=BORDER_LIGHT,
        foreground=TEXT_MAIN,
        font=(FONT_FAMILY, 10, "bold"),
        relief="flat",
        borderwidth=0,
        padding=p(6),
    )
    style.map(
        "Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1e3a8a")]
    )


def build_header(self, body, p):
    header = tk.Frame(body, bg=BG_WINDOW)
    header.pack(fill="x", pady=(0, p(4)))
    title_box = tk.Frame(header, bg=BG_WINDOW)
    title_box.pack(side="left")
    tk.Label(
        title_box, text="LiveSupport", font=("Segoe UI", 21, "bold"), bg=BG_WINDOW, fg=TEXT_MAIN
    ).pack(side="left")
    tk.Label(
        title_box,
        text=f" · 直播助手  {APP_VERSION}",
        font=(FONT_FAMILY, 10),
        bg=BG_WINDOW,
        fg=TEXT_MUTED,
    ).pack(side="left", pady=(p(6), 0))
    self.badge_frame = tk.Frame(
        header,
        bg="#ecfdf5",
        highlightbackground="#a7f3d0",
        highlightthickness=1,
        padx=p(10),
        pady=p(4),
        cursor="hand2",
    )
    self.badge_frame.pack(side="right", pady=(p(2), 0))
    self.account_label = tk.Label(
        self.badge_frame,
        text="正在检测登录…",
        font=(FONT_FAMILY, 9, "bold"),
        bg="#ecfdf5",
        fg="#065f46",
        cursor="hand2",
    )
    self.account_label.pack()
    self.badge_frame.bind("<Button-1>", lambda _: self.open_settings(focus_auth=True))
    self.account_label.bind("<Button-1>", lambda _: self.open_settings(focus_auth=True))
    self.summary = tk.StringVar(value="正在启动…")
    self.summary_label = tk.Label(
        body,
        textvariable=self.summary,
        wraplength=p(900),
        font=(FONT_FAMILY, 9),
        bg=BG_WINDOW,
        fg=TEXT_MUTED,
        anchor="w",
    )
    self.summary_label.pack(fill="x", pady=(0, p(10)))


def build_table(self, body, p):
    table_card = CardFrame(body, px=p, padx=1, pady=1)
    table_card.pack(fill="both", expand=True)
    self.tree = ttk.Treeview(
        table_card,
        columns=("name", "content", "medal", "tasks", "phase", "last"),
        show="headings",
        height=6,
    )
    columns_def = [
        ("name", "直播间 (双击直达)", 140, False, "w"),
        ("content", "直播内容", 200, True, "w"),
        ("medal", "粉丝牌 (等级/经验)", 175, True, "w"),
        ("tasks", "今日任务 (悬停明细)", 165, False, "center"),
        ("phase", "当前状态", 175, False, "w"),
        ("last", "最近心跳", 85, False, "center"),
    ]
    for column, title, width, stretch, anchor in columns_def:
        self.tree.heading(column, text=title)
        self.tree.column(column, width=p(width), minwidth=p(width), stretch=stretch, anchor=anchor)
    self.tree.tag_configure("live", background="#f0fdf4")
    self.tree.tag_configure("even", background="#ffffff")
    self.tree.tag_configure("odd", background="#f8fafc")
    self.tree.tag_configure("placeholder", foreground="#94a3b8")
    self.tree.pack(side="left", fill="both", expand=True)
    scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
    scrollbar.pack(side="right", fill="y")
    self.tree.configure(yscrollcommand=scrollbar.set)
    self.tree.bind("<Double-1>", self.on_double_click)
    self.tree.bind("<Return>", lambda _: self.on_open_room())
    self.tree.bind("<KP_Enter>", lambda _: self.on_open_room())
    self.tree.bind("<Delete>", lambda _: self.on_remove_member())
    self.tree.bind("<BackSpace>", lambda _: self.on_remove_member())
    self.tooltip = Tooltip(self.tree, lambda iid: self.rows_cache.get(iid), px=p)
    self.menu = tk.Menu(
        self.root,
        tearoff=0,
        font=(FONT_FAMILY, 10),
        bg=BG_CARD,
        fg=TEXT_MAIN,
        activebackground="#e0f2fe",
        activeforeground="#0369a1",
    )
    self.menu.add_command(label="🌐 打开直播间 (默认浏览器)", command=self.on_open_room)
    self.menu.add_separator()
    self.menu.add_command(label="💬 补齐弹幕任务", command=lambda: self.on_redo_task("danmaku"))
    self.menu.add_command(label="👍 补做点赞任务", command=lambda: self.on_redo_task("like"))
    self.menu.add_command(label="🔄 重新执行全部任务", command=lambda: self.on_redo_task("all"))
    self.menu.add_command(label="🏅 佩戴该主播勋章", command=self.on_wear_medal)
    self.menu.add_separator()
    self.menu.add_command(label="❌ 从关注列表中移除", command=self.on_remove_member)
    self.tree.bind("<Button-3>", self.on_right_click)


def build_controls(self, body, p):
    buttons = tk.Frame(body, bg=BG_WINDOW)
    buttons.pack(fill="x", pady=(p(12), p(6)))
    self.pause_button = ModernButton(
        buttons, text="暂停挂机", command=lambda: self.commands.put("toggle"), px=p
    )
    self.pause_button.pack(side="left")
    ModernButton(
        buttons,
        text="立即检查",
        command=lambda: (self.summary.set("正在发起即时检查…"), self.commands.put("check")),
        px=p,
    ).pack(side="left", padx=(p(6), 0))
    for text, callback in [
        ("➕ 添加主播", self.open_add_member),
        ("📥 同步粉丝牌", self.open_sync_medals),
        ("⚙️ 系统设置", self.open_settings),
        ("📂 查看日志", lambda: os.startfile(str(self.engine.root / "logs"))),
    ]:
        ModernButton(buttons, text=text, command=callback, px=p).pack(side="left", padx=(p(6), 0))
    self.footer = tk.StringVar()
    self.footer_label = tk.Label(
        body,
        textvariable=self.footer,
        wraplength=p(900),
        font=(FONT_FAMILY, 9),
        bg=BG_WINDOW,
        fg=TEXT_MUTED,
        anchor="w",
    )
    self.footer_label.pack(fill="x")
    body.bind(
        "<Configure>",
        lambda event: [
            label.configure(wraplength=max(p(100), event.width - p(36)))
            for label in (self.summary_label, self.footer_label)
        ],
    )
