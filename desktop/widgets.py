import re
import tkinter as tk

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None


def format_task_result(name, result):
    if result.get("success"):
        return f"【{name}】所选任务已确认完成"
    errors = [result.get("error")] + [
        (result.get(key) or {}).get("error") for key in ("danmaku", "like")
    ]
    detail = "；".join((str(error) for error in errors if error)) or "任务进度尚未确认完成"
    return f"【{name}】任务未完成：{detail}"


BG_WINDOW = "#f8fafc"
BG_CARD = "#ffffff"
BORDER_CARD = "#e2e8f0"
BORDER_LIGHT = "#f1f5f9"
TEXT_MAIN = "#0f172a"
TEXT_MUTED = "#64748b"
ACCENT_GREEN = "#10b981"
ACCENT_GREEN_HOVER = "#059669"
ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_HOVER = "#2563eb"
BTN_BG = "#f1f5f9"
BTN_BG_HOVER = "#e2e8f0"
BTN_FG = "#334155"
FONT_FAMILY = "Microsoft YaHei UI"


def icon_image(color="#63d4b2"):
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=17, fill="#16262d")
    draw.line([(13, 34), (23, 34), (28, 20), (35, 46), (41, 29), (51, 29)], fill=color, width=5)
    return image


def format_task_mini_badge(tasks, is_lighted=1, has_medal=True):
    """格式化任务简报微型标签：💬2/5 👍0/5 ⏱3/5 🏮✓"""
    if not has_medal:
        return "无勋章"
    if not is_lighted:
        return "⚪待复活(0/10)"
    if not tasks:
        return "—"
    danmu = next((t for t in tasks if "弹幕" in t.get("title", "")), None)
    like = next((t for t in tasks if "点赞" in t.get("title", "")), None)
    watch = next((t for t in tasks if "观看" in t.get("title", "")), None)
    feed = next((t for t in tasks if "灯牌" in t.get("title", "")), None)
    done_all = all((t.get("is_done") for t in (danmu, like, watch, feed) if t))
    if done_all and any((danmu, like, watch, feed)):
        return "✅ 全部完成"
    parts = []
    if danmu:
        prog = re.search("(\\d+/\\d+)", danmu.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if danmu.get("is_done") else "0/5"
        parts.append(f"💬{val}")
    if like:
        prog = re.search("(\\d+/\\d+)", like.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if like.get("is_done") else "0/5"
        parts.append(f"👍{val}")
    if watch:
        prog = re.search("(\\d+/\\d+)", watch.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if watch.get("is_done") else "0/5"
        parts.append(f"⏱{val}")
    if feed:
        parts.append("🏮✓" if feed.get("is_done") else "🏮0/1")
    return " ".join(parts) if parts else "—"


class ModernButton(tk.Button):
    """现代无边框/圆角交互按钮，带平滑鼠标悬停效果"""

    def __init__(
        self,
        parent,
        text,
        command=None,
        primary=False,
        accent=ACCENT_GREEN,
        accent_hover=ACCENT_GREEN_HOVER,
        px=None,
        **kwargs,
    ):
        p = px or (lambda v: v)
        self.primary = primary
        self.accent = accent
        self.accent_hover = accent_hover
        if primary:
            bg = self.accent
            fg = "#ffffff"
            active_bg = self.accent_hover
            border_color = self.accent
            hl_thick = 0
        else:
            bg = BTN_BG
            fg = BTN_FG
            active_bg = BTN_BG_HOVER
            border_color = BORDER_CARD
            hl_thick = 1
        font = (FONT_FAMILY, 9, "bold" if primary else "normal")
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=hl_thick,
            highlightbackground=border_color,
            font=font,
            cursor="hand2",
            padx=p(14),
            pady=p(5),
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if self.cget("state") == "disabled":
            return
        self.configure(bg=self.accent_hover if self.primary else BTN_BG_HOVER)

    def _on_leave(self, _):
        if self.cget("state") == "disabled":
            return
        self.configure(bg=self.accent if self.primary else BTN_BG)


class ToggleSwitch(tk.Canvas):
    """现代胶囊拨钮开关 (iOS/Win11 风格)"""

    def __init__(self, parent, variable=None, command=None, width=42, height=22, px=None, **kwargs):
        p = px or (lambda v: v)
        self.px = p
        self.w = p(width)
        self.h = p(height)
        super().__init__(
            parent,
            width=self.w,
            height=self.h,
            bg=parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kwargs,
        )
        self.var = variable if variable is not None else tk.BooleanVar(value=False)
        self.command = command
        self.bind("<Button-1>", self.toggle)
        self.var.trace_add("write", lambda *_: self.render())
        self.render()

    def toggle(self, _=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def render(self):
        self.delete("all")
        p = self.px
        w, h = (self.w, self.h)
        r = h // 2
        val = bool(self.var.get())
        bg_color = ACCENT_GREEN if val else "#cbd5e1"
        self.create_arc((0, 0, h, h), start=90, extent=180, fill=bg_color, outline="")
        self.create_arc((w - h, 0, w, h), start=270, extent=180, fill=bg_color, outline="")
        self.create_rectangle((r, 0, w - r, h), fill=bg_color, outline="")
        pad = p(2)
        diameter = h - pad * 2
        knob_x = w - pad - diameter if val else pad
        self.create_oval(
            (knob_x, pad, knob_x + diameter, pad + diameter), fill="#ffffff", outline=""
        )


class CardFrame(tk.Frame):
    """纯白卡片容器，带淡雅边框与内边距"""

    def __init__(self, parent, px=None, padx=16, pady=12, **kwargs):
        p = px or (lambda v: v)
        super().__init__(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER_CARD,
            highlightthickness=1,
            padx=p(padx),
            pady=p(pady),
            **kwargs,
        )


def create_setting_row(parent, title, desc, widget_factory, px=None):
    """生成标准卡片设置行：左侧主副文案，右侧开关/输入"""
    p = px or (lambda v: v)
    row = tk.Frame(parent, bg=BG_CARD)
    row.pack(fill="x", pady=p(6))
    left = tk.Frame(row, bg=BG_CARD)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(left, text=title, font=(FONT_FAMILY, 9, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(
        anchor="w"
    )
    if desc:
        tk.Label(left, text=desc, font=(FONT_FAMILY, 8), bg=BG_CARD, fg=TEXT_MUTED).pack(
            anchor="w", pady=(p(1), 0)
        )
    right = widget_factory(row)
    right.pack(side="right")
    return right


def create_divider(parent, px=None):
    """卡片内部平滑细分割线"""
    p = px or (lambda v: v)
    div = tk.Frame(parent, height=1, bg=BORDER_LIGHT)
    div.pack(fill="x", pady=p(6))
    return div


def center_window(window, parent=None, width=None, height=None, px=None):
    """使窗口居中于父窗口或屏幕，避免靠边生硬"""
    window.update_idletasks()
    p = px or (lambda v: v)
    w = width or window.winfo_width() or p(400)
    h = height or window.winfo_height() or p(300)
    if parent and parent.winfo_ismapped():
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
    else:
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
    window.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


class Tooltip:
    """浮层悬浮提示卡"""

    def __init__(self, tree, get_data_func, px=None):
        self.tree = tree
        self.get_data = get_data_func
        self.px = px or (lambda v: v)
        self.tip_window = None
        self.last_iid = None
        self.after_id = None
        tree.bind("<Motion>", self.on_motion)
        tree.bind("<Leave>", self.on_leave)
        tree.bind("<MouseWheel>", lambda _: self.hide(), add="+")
        tree.bind("<Button-1>", lambda _: self.hide(), add="+")

    def on_motion(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.hide()
            return
        if iid != self.last_iid:
            self.hide()
            self.last_iid = iid
            self.after_id = self.tree.after(
                280, lambda: self.show(event.x_root + 15, event.y_root + 10, iid)
            )

    def on_leave(self, _):
        self.hide()

    def show(self, x, y, iid):
        if self.tip_window or not iid or iid == "_empty":
            return
        data = self.get_data(iid)
        if not data:
            return
        p = self.px
        self.tip_window = tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER_CARD, padx=1, pady=1)
        frame = tk.Frame(tw, bg=BG_CARD, padx=p(12), pady=p(10))
        frame.pack(fill="both", expand=True)
        lines = [f"【{data['name']} · 亲密度与今日任务】"]
        if data.get("live_status") == 1:
            dur = data.get("live_duration", "")
            title = data.get("title", "")
            area = data.get("area_name", "")
            dur_str = f" ({dur})" if dur else ""
            lines.append(f"正在直播: [{area or '直播'}] {title or '直播中'}{dur_str}")
        medal_name = data.get("medal_name")
        level = data.get("medal_level", 0)
        is_lit = data.get("is_lighted", 0)
        light_days = data.get("task_light_days", 0)
        intimacy = data.get("intimacy", 0)
        next_int = data.get("next_intimacy", 0)
        today_int = data.get("today_intimacy", 0)
        limit = data.get("day_limit", 20000)
        if medal_name:
            status_lit = f"已点亮 (余 {light_days} 天)" if is_lit else "已熄灭 (需点亮)"
            lines.append(f"勋章: {medal_name} Lv{level} · {status_lit}")
            if next_int and next_int > 0:
                pct = int(intimacy / next_int * 100)
                need = max(0, next_int - intimacy)
                lines.append(
                    f"升级经验: {intimacy}/{next_int} ({pct}%) · 距 Lv{level + 1} 还需 {need} 经验"
                )
            lines.append(f"今日已得亲密度: {today_int} / {limit}")
        else:
            lines.append("勋章: 未拥有该主播粉丝勋章")
            lines.append("💡 提示：前往该主播直播间投喂 1 电池或赠送灯牌即可获取勋章")
        lines.append("─" * 32)
        tasks = data.get("tasks", [])
        if tasks:
            for t in tasks:
                title = t.get("title", "")
                sub = t.get("sub_title", "")
                done = " [已达成]" if t.get("is_done") else ""
                lines.append(f"• {title}: {sub}{done}")
        else:
            lines.append("• 暂无详细任务数据，巡检后自动刷新")
        lines.append("─" * 32)
        lines.append("💡 双击进入直播间 · 右键可补齐弹幕/点赞")
        text = "\n".join(lines)
        label = tk.Label(
            frame,
            text=text,
            justify="left",
            bg=BG_CARD,
            fg=TEXT_MAIN,
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        label.pack()
        tw.update_idletasks()
        tw_w = tw.winfo_width()
        tw_h = tw.winfo_height()
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        target_x = max(10, min(x, sw - tw_w - p(15)))
        target_y = max(10, min(y, sh - tw_h - p(45)))
        tw.wm_geometry(f"+{target_x}+{target_y}")

    def hide(self):
        if self.after_id:
            self.tree.after_cancel(self.after_id)
            self.after_id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
        self.last_iid = None
