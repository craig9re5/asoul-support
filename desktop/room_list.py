"""Scrollable room cards with the selection/item contract used by desktop actions."""

import tkinter as tk
from tkinter import font as tkfont
from .avatars import round_avatar
from .presentation import gain_label
from .widgets import FONT_FAMILY, SlimScrollbar

BACKGROUND = "#ffffff"
SELECTED = "#edf3f1"
LIVE = "#f0fdf4"
LIVE_DOT = "#22c55e"
INK = "#253638"
MUTED = "#657477"
PLACEHOLDER = "#94a3b8"
ROW_HEIGHT = 70

# Measuring a string costs ~0.15ms, but emoji fall back through the font stack and
# cost ~5ms. The list re-elides every row on each refresh, so cache by (font, text).
_MEASURE_CACHE = {}
_FONT_CACHE = {}


def font_for(widget):
    """Reuse one Font object per spec; constructing one per row is not free."""
    spec = widget.cget("font")
    key = spec if isinstance(spec, str) else tuple(spec)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = tkfont.Font(font=spec)
        _FONT_CACHE[key] = font
    return font


def measure(font, text):
    key = (tuple(sorted(font.actual().items())), text)
    width = _MEASURE_CACHE.get(key)
    if width is None:
        width = font.measure(text)
        if len(_MEASURE_CACHE) > 20000:
            _MEASURE_CACHE.clear()
        _MEASURE_CACHE[key] = width
    return width


class RoomList(tk.Frame):
    def __init__(self, parent, ui):
        super().__init__(parent, bg=BACKGROUND, takefocus=True)
        self.ui, self.items, self.order = ui, {}, []
        self.selected, self.focused = "", ""
        self.canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0)
        self.scrollbar = SlimScrollbar(self, self.canvas, ui.px)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.canvas, bg=BACKGROUND)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _: self._sync_scroll())
        self.canvas.bind("<Configure>", self._resize)
        self.bind("<Return>", lambda _: ui.on_open_room())
        self.bind("<Delete>", lambda _: ui.on_remove_member())
        self.bind("<Up>", lambda _: self._step(-1))
        self.bind("<Down>", lambda _: self._step(1))

    def _sync_scroll(self):
        """Size the scroll region from the rows, not from a stale bbox.

        Removing rows shrinks content without a Configure on the inner frame,
        which used to leave the old, taller scroll region in place and let the
        list scroll past its last row into blank space.
        """
        width = self.canvas.winfo_width()
        height = sum(item["frame"].winfo_height() for item in self.items.values())
        if width <= 1 or height <= 0:
            self.canvas.configure(scrollregion=(0, 0, max(1, width), 1))
            return
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if height <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        for item in self.items.values():
            self._fit_headline(item, event.width)
        self._sync_scroll()

    def _fit_headline(self, item, width):
        available = max(1, width - self.ui.px(66))
        dot_width = self.ui.px(13) if item["live_dot"].cget("text") else 0
        available = max(1, available - dot_width)
        name_font = font_for(item["name"])
        name = self._elide(item.get("name_text", ""), name_font, int(available * 0.48))
        item["name"].configure(text=name)
        title_font = font_for(item["title"])
        item["title"].configure(text=self._elide(item.get("title_text", ""), title_font,
                                               available - measure(name_font, name) - self.ui.px(14)))
        column_width = max(1, available // 3)
        for column in range(3):
            item["metadata"].columnconfigure(column, minsize=column_width, weight=1, uniform="metadata")
        for key, text in item.get("metadata_text", {}).items():
            font = font_for(item[key])
            item[key].configure(text=self._elide(text, font, column_width - self.ui.px(8)))
        # Task badge and heartbeat share one row; reserve the badge its natural width.
        heartbeat_font = font_for(item["heartbeat"])
        item["heartbeat"].configure(text=item.get("heartbeat_text", ""))
        badge_width = available - measure(heartbeat_font, item.get("heartbeat_text", "")) - self.ui.px(12)
        badge_font = font_for(item["tasks"])
        item["tasks"].configure(text=self._elide(item.get("tasks_text", ""), badge_font, badge_width))

    @staticmethod
    def _elide(text, font, width):
        text = " ".join(str(text).split())
        if measure(font, text) <= width:
            return text
        if measure(font, "…") > width:
            return ""
        left, right = 0, len(text)
        while left < right:
            middle = (left + right + 1) // 2
            if measure(font, text[:middle] + "…") <= width:
                left = middle
            else:
                right = middle - 1
        return text[:left] + "…"

    def _step(self, step):
        if not self.order:
            return
        current = self.order.index(self.selected) if self.selected in self.order else 0
        self.selection_set(self.order[min(len(self.order) - 1, max(0, current + step))])
        self.focused = self.selected

    def _pick(self, iid):
        self.selection_set(iid)
        self.focused = iid
        self.focus_set()

    def _context(self, iid, event):
        self._pick(iid)
        if iid != "_empty":
            self.ui.menu.post(event.x_root, event.y_root)

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def get_children(self):
        return tuple(self.order)

    def exists(self, iid):
        return iid in self.items

    def selection(self):
        return (self.selected,) if self.selected else ()

    def selection_set(self, iid):
        if isinstance(iid, (list, tuple)):
            iid = iid[0] if iid else ""
        self.selected = iid if iid in self.items else ""
        for key in self.items:
            self._paint(key)
        self.event_generate("<<TreeviewSelect>>")

    def selection_remove(self, _):
        self.selection_set("")

    def focus(self, iid=None):
        if iid is not None:
            self.focused = iid
        return self.focused

    def identify_row(self, y):
        for iid, item in self.items.items():
            top = item["frame"].winfo_rooty() - self.winfo_rooty()
            if top <= y < top + item["frame"].winfo_height():
                return iid
        return ""

    def insert(self, _parent, _position, *, iid, values, tags=()):
        p = self.ui.px
        frame = tk.Frame(self.content, bg=BACKGROUND, padx=p(12), pady=p(2), height=p(ROW_HEIGHT))
        frame.pack(fill="x")
        frame.grid_propagate(False)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(0, minsize=p(42))
        avatar = tk.Label(frame, text="", bg=SELECTED, fg=MUTED, width=0,
                          font=(FONT_FAMILY, 12), anchor="center")
        avatar.grid(row=0, column=0, rowspan=2, padx=(0, p(10)), sticky="n")
        headline = tk.Frame(frame, bg=BACKGROUND)
        headline.grid(row=0, column=1, sticky="ew")
        headline.columnconfigure(1, weight=1)
        labels = {}
        # A single dot carries the live state; the name stays plain text.
        labels["live_dot"] = tk.Label(headline, bg=BACKGROUND, fg=LIVE_DOT, text="",
                                      font=(FONT_FAMILY, 10), padx=0, pady=0)
        labels["live_dot"].grid(row=0, column=0, sticky="w", padx=(0, p(5)))
        for column, (name, size, color) in enumerate((("name", 10, INK), ("title", 9, MUTED)), start=1):
            label = tk.Label(headline, bg=BACKGROUND, fg=color, anchor="e" if name == "title" else "w", justify="left", padx=0, pady=0,
                             font=(FONT_FAMILY, size, "bold" if name == "name" else "normal"))
            label.grid(row=0, column=column, sticky="ew", padx=(0, p(8) if name == "name" else 0))
            labels[name] = label
        headline.columnconfigure(1, weight=0)
        headline.columnconfigure(2, weight=1)
        metadata = tk.Frame(frame, bg=BACKGROUND)
        metadata.grid(row=1, column=1, sticky="ew")
        for column, (name, color) in enumerate((("phase", MUTED), ("medal", INK), ("gain", "#2d6763"))):
            metadata.columnconfigure(column, weight=1, uniform="metadata")
            labels[name] = tk.Label(metadata, bg=BACKGROUND, fg=color,
                                    anchor="e" if name == "gain" else "w", font=(FONT_FAMILY, 9), width=1, padx=0, pady=0)
            labels[name].grid(row=0, column=column, sticky="ew", padx=(0, p(8) if column < 2 else 0))
        progress = tk.Frame(frame, bg=BACKGROUND)
        progress.grid(row=2, column=1, sticky="ew")
        progress.columnconfigure(0, weight=1)
        labels["tasks"] = tk.Label(progress, bg=BACKGROUND, fg=MUTED, anchor="w",
                                   font=(FONT_FAMILY, 8), width=1, padx=0, pady=0)
        labels["tasks"].grid(row=0, column=0, sticky="ew")
        labels["heartbeat"] = tk.Label(progress, bg=BACKGROUND, fg=MUTED, anchor="e",
                                       font=(FONT_FAMILY, 8), padx=0, pady=0)
        labels["heartbeat"].grid(row=0, column=1, sticky="e", padx=(p(8), 0))
        line = tk.Frame(frame, height=1, bg="#e2e8e6")
        line.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(p(1), 0))
        self.items[iid] = {"frame": frame, "avatar": avatar, "metadata": metadata, "headline": headline,
                           "progress": progress, "values": values, "tags": tags, **labels}
        self.order.append(iid)
        for widget in (frame, avatar, headline, metadata, progress, *labels.values()):
            widget.bind("<Button-1>", lambda _, key=iid: self._pick(key))
            widget.bind("<Double-1>", lambda _, key=iid: (self._pick(key), self.ui.on_open_room()))
            widget.bind("<Button-3>", lambda event, key=iid: self._context(key, event))
            widget.bind("<MouseWheel>", self._wheel)
        self.item(iid, values=values, tags=tags)
        self._sync_scroll()
        return iid

    def _paint(self, iid):
        item = self.items[iid]
        if iid == self.selected:
            bg = SELECTED
        elif "live" in item.get("tags", ()):
            bg = LIVE
        else:
            bg = BACKGROUND
        for key in ("frame", "name", "title", "headline", "metadata", "progress",
                    "phase", "medal", "gain", "tasks", "heartbeat", "live_dot"):
            item[key].configure(bg=bg)
        if item.get("photo"):
            item["avatar"].configure(bg=bg)

    def item(self, iid, **changes):
        item = self.items[iid]
        item.update(changes)
        if not changes:
            return {"values": item["values"], "tags": item["tags"]}
        values = item["values"]
        row = self.ui.rows_cache.get(iid, {})
        item["name_text"] = values[0] or row.get("name", "")
        item["title_text"] = values[1]
        item["metadata_text"] = {"phase": values[4], "medal": values[2].split("\n")[0],
                                 "gain": gain_label(row) if row.get("medal_name") else ""}
        item["live_dot"].configure(text="●" if row.get("live_status") == 1 else "")
        item["tasks_text"] = "" if values[3] == "—" else values[3]
        item["heartbeat_text"] = "" if values[5] == "—" else values[5]
        self._fit_headline(item, self.canvas.winfo_width())
        item["phase"].configure(fg="#a65c00" if row.get("watch_warning") or row.get("connection_warning") else MUTED)
        if "placeholder" in item.get("tags", ()):
            for key in ("name", "title", "phase", "medal", "gain", "tasks", "heartbeat"):
                item[key].configure(fg=PLACEHOLDER)
            item["live_dot"].configure(fg=PLACEHOLDER)
        if not item.get("photo"):
            item["avatar"].configure(text=row.get("name", "?")[:1])
        self._paint(iid)

    def set_avatar(self, iid, image):
        from PIL import ImageTk
        if iid not in self.items:
            return
        item = self.items[iid]
        photo = ImageTk.PhotoImage(round_avatar(image, self.ui.px(32)), master=self.ui.root)
        item["photo"] = photo
        item["avatar"].configure(image=photo, text="", width=0, bg=item["frame"].cget("bg"))

    def delete(self, iid):
        self.items.pop(iid)["frame"].destroy()
        self.order.remove(iid)
        if self.selected == iid:
            self.selected = ""
        self._sync_scroll()

    def move(self, iid, _parent, index):
        if self.order[index] == iid:
            return
        self.order.remove(iid)
        self.order.insert(index, iid)
        for key in self.order:
            self.items[key]["frame"].pack_forget()
            self.items[key]["frame"].pack(fill="x")
        self._sync_scroll()
