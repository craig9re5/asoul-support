"""Workbench layout. All user actions keep the existing application/engine adapters."""

import os
import tkinter as tk
from .avatars import AvatarLoader
from .room_list import RoomList
from .presentation import phase_label, gain_label
from .widgets import ModernButton, FONT_FAMILY

BG = "#f5f6f5"
INK = "#253638"
MUTED = "#657477"
ACCENT = "#2d6763"
SIDE = "#1e2c2f"


def label(parent, text="", *, size=10, color=INK, bg="white", bold=False):
    return tk.Label(parent, text=text, bg=bg, fg=color, anchor="w", justify="left",
                    font=(FONT_FAMILY, size, "bold" if bold else "normal"))


class Workbench:
    def __init__(self, ui):
        self.ui = ui
        self.loader = AvatarLoader(ui.engine.root, ui.engine.dispatcher)
        self.photos, self.snap = {}, {"rows": []}
        p = ui.px
        shell = tk.Frame(ui.root, bg=BG)
        shell.pack(fill="both", expand=True)
        side = tk.Frame(shell, bg=SIDE, width=p(194), padx=p(15), pady=p(25))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        label(side, "LiveSupport", size=16, color="#e5eeeb", bg=SIDE, bold=True).pack(anchor="w", pady=(0,p(35)))
        for text, command in (("监控总览", ui.show),
                              ("活动记录", lambda: os.startfile(str(ui.engine.root / "logs"))),
                              ("自动化设置", ui.open_settings), ("账号管理", lambda: ui.open_settings(focus_auth=True))):
            button = tk.Button(side, text=text, command=command, bg=SIDE, fg="#c0ceca",
                               activebackground="#334647", activeforeground="#ffffff", relief="flat",
                               bd=0, anchor="w", padx=p(10), pady=p(12), font=(FONT_FAMILY, 10), cursor="hand2")
            button.pack(fill="x", pady=p(2))
        label(side, "本机运行 · 托盘常驻", size=9, color="#a6bab4", bg=SIDE).pack(side="bottom", anchor="w")
        self.body = tk.Frame(shell, bg=BG, padx=p(14), pady=p(14))
        self.body.pack(side="left", fill="both", expand=True)
        header = tk.Frame(self.body, bg=BG)
        header.pack(fill="x", pady=(0,p(10)))
        self.heading = label(header, "监控总览", size=18, bg=BG, bold=True)
        self.heading.pack(side="left")
        ui.badge_frame = tk.Frame(header, bg="#ecfdf5", padx=p(8), pady=p(5))
        ui.badge_frame.pack(side="right")
        ui.account_label = label(ui.badge_frame, "正在验证登录…", size=9, bg="#ecfdf5")
        ui.account_label.pack()
        ui.account_label.bind("<Button-1>", lambda _: ui.open_settings(focus_auth=True))
        self._build_toolbar()
        self._build_footer()
        self.area = tk.Frame(self.body, bg=BG)
        self.area.pack(fill="both", expand=True)
        self.list_frame = tk.Frame(self.area, bg="white", highlightbackground="#e2e8e6", highlightthickness=1)
        self.list_frame.pack(side="left", fill="both", expand=True, padx=(0,p(12)))
        label(self.list_frame, "关注的直播间", size=10, bold=True).pack(anchor="w", padx=p(12), pady=p(8))
        ui.tree = RoomList(self.list_frame, ui)
        ui.tree.pack(fill="both", expand=True)
        ui.tree.bind("<<TreeviewSelect>>", lambda _: self.render_detail())
        self.detail_outer = tk.Frame(self.area, bg="white", width=p(318),
                                    highlightbackground="#e2e8e6", highlightthickness=1)
        self.detail_outer.pack(side="left", fill="y")
        self.detail_outer.pack_propagate(False)
        self.detail_actions = tk.Frame(self.detail_outer, bg="white", padx=p(14), pady=p(12))
        self.detail_actions.pack(side="bottom", fill="x")
        detail_scroll_area = tk.Frame(self.detail_outer, bg="white")
        detail_scroll_area.pack(fill="both", expand=True)
        self.detail_canvas = tk.Canvas(detail_scroll_area, bg="white", highlightthickness=0)
        detail_scroll = tk.Scrollbar(detail_scroll_area, command=self.detail_canvas.yview)
        detail_scroll.pack(side="right", fill="y")
        self.detail_canvas.configure(yscrollcommand=detail_scroll.set)
        self.detail_canvas.pack(fill="both", expand=True)
        self.detail_frame = tk.Frame(self.detail_canvas, bg="white", padx=p(16), pady=p(18))
        detail_window = self.detail_canvas.create_window(0, 0, window=self.detail_frame, anchor="nw")
        self.detail_canvas.bind("<Configure>", lambda e: self.detail_canvas.itemconfigure(detail_window, width=e.width))
        self.detail_frame.bind("<Configure>", lambda _: self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all")))
        self.detail_title = label(self.detail_frame, "选择主播查看详情", size=12, bold=True)
        self.detail_title.pack(fill="x")
        self.detail_phase = label(self.detail_frame, "", size=9, color=MUTED)
        self.detail_phase.pack(fill="x", pady=(p(8),p(18)))
        self.detail_live_title = label(self.detail_frame, "", size=9, color=MUTED)
        self.detail_live_title.configure(wraplength=p(265))
        self.detail_live_title.pack(fill="x", pady=(0,p(12)))
        self.detail_medal = label(self.detail_frame, "粉丝牌信息待更新", size=11)
        self.detail_medal.pack(fill="x")
        self.detail_gain = label(self.detail_frame, "今日亲密度：待更新", size=10, color=ACCENT)
        self.detail_gain.pack(fill="x", pady=(p(6),p(7)))
        self.detail_exp = label(self.detail_frame, "", size=9, color=MUTED)
        self.detail_exp.pack(fill="x", pady=(0,p(18)))
        self.task_labels = []
        for title in ("弹幕", "点赞", "看播", "灯牌"):
            row = tk.Frame(self.detail_frame, bg="white", pady=p(10))
            row.pack(fill="x")
            label(row, title, size=10).pack(side="left")
            value = label(row, "待更新", size=9, color=MUTED)
            value.pack(side="right")
            self.task_labels.append((title, value))
            tk.Frame(self.detail_frame, bg="#e2e8e6", height=1).pack(fill="x")
        self.detail_heartbeat = label(self.detail_frame, "", size=9, color=MUTED)
        self.detail_heartbeat.pack(fill="x", pady=(p(18),p(12)))
        self.detail_heartbeat.configure(wraplength=p(275))
        action = self.detail_actions
        ModernButton(action, text="打开直播间", command=ui.on_open_room, px=p).pack(side="left")
        self.redo_button = ModernButton(action, text="补齐任务", command=lambda: ui.on_redo_task("all"), px=p)
        self.redo_button.pack(side="left", padx=(p(8),0))

    def _build_toolbar(self):
        ui, p = self.ui, self.ui.px
        self.toolbar = tk.Frame(self.body, bg="#e9f4ed", padx=p(8), pady=p(5))
        self.toolbar.pack(fill="x", pady=(0,p(10)))
        ui.safety_button = ModernButton(self.toolbar, text="解除异常暂停", command=ui.on_safety_resume,
                                       px=p, state="disabled")
        ui.safety_button.pack(side="right", padx=(p(6),0))
        ui.pause_button = ModernButton(self.toolbar, text="暂停挂机", command=lambda: ui.commands.put("toggle"),
                                      primary=True, accent=ACCENT, accent_hover="#245550", px=p)
        ui.pause_button.pack(side="right", padx=(p(6),0))
        self.check_button = ModernButton(self.toolbar, text="立即检查", command=lambda: ui.commands.put("check"), px=p)
        self.check_button.pack(side="right", padx=(p(6),0))
        ui.summary = tk.StringVar(value="正在启动…")
        ui.summary_label = tk.Label(self.toolbar, textvariable=ui.summary, bg="#e9f4ed", fg="#24634e",
                                   font=(FONT_FAMILY, 9), anchor="w", width=1)
        ui.summary_label.pack(side="left", fill="x", expand=True)

    def _build_footer(self):
        ui, p = self.ui, self.ui.px
        self.footer_bar = tk.Frame(self.body, bg=BG)
        self.footer_bar.pack(side="bottom", fill="x", pady=(p(8),0))
        for text, command in (("添加主播", ui.open_add_member), ("同步粉丝牌", ui.open_sync_medals)):
            ModernButton(self.footer_bar, text=text, command=command, px=p).pack(side="right", padx=(p(6),0))
        ui.footer = tk.StringVar()
        ui.footer_label = tk.Label(self.footer_bar, textvariable=ui.footer, bg=BG, fg=MUTED,
                                   font=(FONT_FAMILY, 9), anchor="w", justify="left", width=1)
        ui.footer_label.pack(side="left", fill="x", expand=True)
        ui.footer_label.bind("<Configure>", lambda e: ui.footer_label.configure(wraplength=max(1, e.width)))

    def render(self, snap):
        self.snap = snap
        if not self.ui.tree.selection() and snap["rows"]:
            self.ui.tree.selection_set(str(snap["rows"][0]["room"]))
        for row in snap["rows"]:
            uid = row.get("uid")
            if uid in self.photos:
                item = self.ui.tree.items.get(str(row["room"]), {})
                if not item.get("photo"):
                    self.ui.tree.set_avatar(str(row["room"]), self.photos[uid])
                continue
            self.loader.request(uid, row.get("avatar_url", ""),
                                lambda image, key=str(row["room"]), account=uid: self._avatar(key, account, image))
        self.render_detail()

    def _avatar(self, room, uid, image):
        if self.ui.closed:
            return
        self.photos[uid] = image
        self.ui.tree.set_avatar(room, image)

    def render_detail(self):
        selected = self.ui.tree.selection()
        row = self.ui.rows_cache.get(selected[0], {}) if selected else {}
        self.detail_title.configure(text=(row.get("name", "选择主播") + " · 今日任务"))
        self.detail_phase.configure(text=phase_label(row))
        self.detail_live_title.configure(text=row.get("title", ""))
        self.detail_medal.configure(text=f"{row['medal_name']} Lv.{row.get('medal_level',0)}" if row.get("medal_name") else "暂无粉丝牌")
        self.detail_gain.configure(text=gain_label(row) if row.get("medal_name") else "")
        self.detail_exp.configure(text=f"等级经验 {row.get('intimacy',0)} / {row.get('next_intimacy',0)}" if not row.get("tasks_stale", True) else "经验数据待更新")
        for keyword, widget in self.task_labels:
            words = ("观看", "看播") if keyword == "看播" else (keyword,)
            task = next((t for t in row.get("tasks", []) if any(word in t.get("title", "") for word in words)), None)
            value = "待更新" if not task else "已完成" if task.get("is_done") else task.get("sub_title", "未完成")
            widget.configure(text=value, fg=ACCENT if task and task.get("is_done") else MUTED)
        heartbeat = row.get("last_heartbeat")
        import time
        last = time.strftime("%H:%M:%S", time.localtime(heartbeat)) if heartbeat else "暂无成功心跳"
        self.detail_heartbeat.configure(text=f"最近心跳：{last}" + ("\n"+row["task_error"] if row.get("task_error") else ""))
        enabled = row.get("live_status") == 1 and not self.snap.get("paused") and not self.snap.get("safety",{}).get("blocked")
        self.redo_button.configure(state="normal" if enabled else "disabled")
