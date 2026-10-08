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


BG_WINDOW = "#f5f6f5"
BG_CARD = "#ffffff"
BORDER_CARD = "#e2e8f0"
BORDER_LIGHT = "#f1f5f9"
TEXT_MAIN = "#253638"
TEXT_MUTED = "#657477"
ACCENT_GREEN = "#2d6763"
ACCENT_GREEN_HOVER = "#245550"
ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_HOVER = "#2563eb"
BTN_BG = "#f1f5f9"
BTN_BG_HOVER = "#e2e8f0"
BTN_FG = "#334155"
FONT_FAMILY = "Microsoft YaHei UI"


def icon_image(color="#63d4b2", size=64):
    scale = 4
    image = Image.new("RGBA", (64 * scale, 64 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(tuple(v * scale for v in (3, 3, 61, 61)), radius=17 * scale, fill="#16262d")
    points = [(x * scale, y * scale) for x, y in [(13, 34), (23, 34), (28, 20), (35, 46), (41, 29), (51, 29)]]
    draw.line(points, fill=color, width=5 * scale, joint="curve")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def navigation_icon(kind, size, color="#aac1b9"):
    scale = 4
    image = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(image)
    def line(points):
        draw.line([(x * scale, y * scale) for x, y in points], fill=color, width=2 * scale, joint="curve")
    def ellipse(box):
        draw.ellipse(tuple(v * scale for v in box), outline=color, width=2 * scale)
    if kind == "monitor":
        draw.rounded_rectangle(tuple(v * scale for v in (3, 4, 21, 17)), radius=2 * scale,
                               outline=color, width=2 * scale)
        line([(8, 21), (16, 21)])
        line([(12, 17), (12, 21)])
    elif kind == "automation":
        for y, x in ((6, 9), (12, 16), (18, 7)):
            line([(3, y), (x - 3, y)])
            line([(x + 3, y), (21, y)])
            ellipse((x - 3, y - 3, x + 3, y + 3))
    elif kind == "account":
        ellipse((8, 3, 16, 11))
        draw.arc(tuple(v * scale for v in (4, 13, 20, 27)), start=180, end=360,
                 fill=color, width=2 * scale)
        line([(4, 20), (20, 20)])
    else:
        ellipse((3, 3, 21, 21))
        line([(12, 7), (12, 12), (16, 14)])
    return image.resize((size, size), Image.Resampling.LANCZOS)


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
    """Native keyboard/accessibility behavior with rounded bitmap backgrounds."""

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
        self.px = p
        self.hovered = self.focused = False
        self._fills = (self.accent, self.accent_hover) if primary else (BTN_BG, BTN_BG_HOVER)
        font = (FONT_FAMILY, 9, "bold" if primary else "normal")
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=parent.cget("bg"),
            fg="#ffffff" if primary else BTN_FG,
            activebackground=parent.cget("bg"),
            activeforeground="#ffffff" if primary else BTN_FG,
            disabledforeground="#89979a",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=font,
            cursor="hand2",
            padx=0,
            pady=0,
            compound="center",
            takefocus=True,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", lambda _: self._focus(True))
        self.bind("<FocusOut>", lambda _: self._focus(False))
        self._render_background()

    def _focus(self, focused):
        self.focused = focused
        self._render_background()

    def _render_background(self):
        from tkinter import font as tkfont
        from PIL import ImageTk
        font = tkfont.Font(font=self.cget("font"))
        size = (max(1, font.measure(self.cget("text"))) + self.px(28), font.metrics("linespace") + self.px(10))
        self._photos = []
        for fill in (*self._fills, "#e8eeec"):
            picture = Image.new("RGBA", size)
            draw = ImageDraw.Draw(picture)
            draw.rounded_rectangle((0, 0, size[0]-1, size[1]-1), radius=self.px(8), fill=fill,
                                   outline=self.accent if self.focused else (fill if self.primary else BORDER_CARD), width=1)
            self._photos.append(ImageTk.PhotoImage(picture, master=self))
        self._select_background()

    def _select_background(self):
        index = 2 if self.cget("state") == "disabled" else int(self.hovered)
        super().configure(image=self._photos[index])

    def configure(self, cnf=None, **kwargs):
        options = {**(cnf or {}), **kwargs} if isinstance(cnf, (dict, type(None))) else kwargs
        redraw = any(key in options and str(options[key]) != str(self.cget(key)) for key in ("text", "font"))
        result = super().configure(cnf, **kwargs)
        if redraw and hasattr(self, "_photos"):
            self._render_background()
        elif "state" in options and hasattr(self, "_photos"):
            self._select_background()
        return result

    config = configure

    def _on_enter(self, _):
        if self.cget("state") == "disabled":
            return
        self.hovered = True
        super().configure(image=self._photos[1])

    def _on_leave(self, _):
        self.hovered = False
        self._select_background()


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
        self.hovered = self.focused = False
        self.configure(takefocus=True)
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<Enter>", lambda _: self._appearance(hovered=True))
        self.bind("<Leave>", lambda _: self._appearance(hovered=False))
        self.bind("<FocusIn>", lambda _: self._appearance(focused=True))
        self.bind("<FocusOut>", lambda _: self._appearance(focused=False))
        self.trace_id = self.var.trace_add("write", lambda *_: self.render())
        self.bind("<Destroy>", self._remove_trace)
        self.render()

    def toggle(self, _=None):
        if self.cget("state") == "disabled":
            return "break"
        self.focus_set()
        self.var.set(not self.var.get())
        if self.command:
            self.command()
        return "break"

    def _appearance(self, **values):
        self.__dict__.update(values)
        self.render()

    def _remove_trace(self, event):
        if event.widget is self:
            self.var.trace_remove("write", self.trace_id)

    def render(self):
        self.delete("all")
        from PIL import ImageTk
        scale = 4
        w, h = self.w, self.h
        image = Image.new("RGBA", (w * scale, h * scale))
        draw = ImageDraw.Draw(image)
        val = bool(self.var.get())
        fill = (ACCENT_GREEN_HOVER if self.hovered else ACCENT_GREEN) if val else ("#b8c6c5" if self.hovered else "#d5dfdd")
        margin = scale
        draw.rounded_rectangle((margin, margin, w * scale - margin - 1, h * scale - margin - 1),
                               radius=h * scale / 2, fill=fill,
                               outline="#71b6a6" if self.focused else (fill if val else "#c4d1ce"),
                               width=scale)
        pad = max(2, self.px(3)) * scale
        diameter = h * scale - 2 * pad
        x = w * scale - pad - diameter if val else pad
        draw.ellipse((x, pad + scale / 2, x + diameter, pad + diameter + scale / 2), fill="#9eafab")
        draw.ellipse((x, pad, x + diameter, pad + diameter), fill="white")
        self.photo = ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS), master=self)
        self.create_image(0, 0, anchor="nw", image=self.photo)


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
