"""Cancellable QR login UI; phone confirmation remains a user action."""

import threading
import tkinter as tk
from PIL import ImageTk
import qrcode
from qrcode.image.pil import PilImage

from asoul_support.qr_login import QrLoginSession, POLL_INTERVAL
from .widgets import BG_WINDOW, TEXT_MAIN, TEXT_MUTED, FONT_FAMILY, ModernButton, center_window


class QrLoginDialog(tk.Toplevel):
    def __init__(self, parent, engine, px, on_login, session_factory=QrLoginSession):
        super().__init__(parent)
        self.engine, self.px, self.on_login = engine, px, on_login
        self.session_factory = session_factory
        self.cancelled = threading.Event()
        self.closed = False
        self.title("B 站扫码登录 · LiveSupport")
        self.configure(bg=BG_WINDOW)
        w, h = px(410), px(500)
        self.geometry(f"{w}x{h}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Destroy>", self.on_destroy)
        center_window(self, parent, w, h, px)
        tk.Label(
            self,
            text="使用 B 站 App 扫码登录",
            font=(FONT_FAMILY, 15, "bold"),
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
        ).pack(pady=(px(20), px(8)))
        tk.Label(
            self,
            text="在手机上确认后，验证并保存本机登录信息",
            font=(FONT_FAMILY, 9),
            bg=BG_WINDOW,
            fg=TEXT_MUTED,
        ).pack()
        self.qr_label = tk.Label(self, text="正在申请二维码…", bg="white", width=32, height=16)
        self.qr_label.pack(pady=px(16))
        self.status = tk.StringVar(value="正在连接 B 站登录服务…")
        tk.Label(
            self,
            textvariable=self.status,
            bg=BG_WINDOW,
            fg=TEXT_MAIN,
            font=(FONT_FAMILY, 10),
            wraplength=px(370),
        ).pack()
        self.refresh_button = ModernButton(
            self, text="刷新二维码", command=self.refresh_code, px=px
        )
        self.refresh_button.pack(pady=px(12))
        self.refresh_code()

    def current(self, cancelled):
        return not self.closed and not cancelled.is_set()

    def on_destroy(self, event):
        if event.widget is self:
            self.closed = True
            self.cancelled.set()

    def post(self, cancelled, callback):
        self.engine.dispatcher.post(lambda: callback() if self.current(cancelled) else None)

    def refresh_code(self):
        self.cancelled.set()
        self.cancelled = cancelled = threading.Event()
        self.refresh_button.configure(state="disabled")
        self.qr_label.configure(image="", text="正在申请二维码…", width=32, height=16)
        self.qr_image = None
        self.status.set("正在连接 B 站登录服务…")
        self.engine.dispatcher.submit(lambda: self.run_session(cancelled))

    def run_session(self, cancelled):
        session = self.session_factory()
        try:
            url = session.generate()
            image = (
                qrcode.make(url, box_size=1, border=4, image_factory=PilImage)
                .get_image()
                .convert("RGB")
            )
            # Preserve whole modules and the quiet zone; integer nearest-neighbor scaling.
            size = max(1, self.px(250) // image.width) * image.width
            from PIL import Image

            image = image.resize((size, size), Image.Resampling.NEAREST)
            self.post(cancelled, lambda: self.show_qr(image))
            while not cancelled.wait(POLL_INTERVAL):
                result = session.poll()
                if cancelled.is_set():
                    return
                if result.state == "confirmed":
                    cookies = result.credentials
                    valid, account = self.engine.application.validate_credentials(
                        cookies["SESSDATA"], cookies["bili_jct"]
                    )
                    if not valid:
                        raise RuntimeError("扫码已确认，但登录验证未通过，请重新扫码")
                    self.post(cancelled, lambda: self.complete(cookies, account, result.context))
                    return
                self.post(cancelled, lambda state=result.state: self.show_state(state))
                if result.state == "expired":
                    return
        except Exception:
            self.post(cancelled, self.show_error)
        finally:
            session.cancel()

    def show_qr(self, image):
        self.qr_image = ImageTk.PhotoImage(image)
        self.qr_label.configure(
            image=self.qr_image, text="", width=image.width, height=image.height
        )
        self.status.set("请用 B 站 App 扫码（有效期约 3 分钟）")
        self.refresh_button.configure(state="normal")

    def show_state(self, state):
        messages = {
            "waiting": "等待扫码…",
            "scanned": "已扫码，请在手机上确认登录",
            "expired": "二维码已过期，请点击刷新",
        }
        self.status.set(messages.get(state, "请刷新二维码"))
        if state == "expired":
            self.qr_label.configure(image="", text="二维码已过期", width=32, height=16)
            self.qr_image = None

    def show_error(self):
        self.status.set("扫码登录失败，请检查网络或刷新二维码重试")
        self.refresh_button.configure(state="normal")

    def complete(self, cookies, account, context=None):
        try:
            self.on_login(cookies, account, context=context)
        except (OSError, ValueError, RuntimeError):
            self.status.set("登录已验证，但本机保存失败，请重试或检查文件权限")
            return
        self.close()

    def close(self):
        self.closed = True
        self.cancelled.set()
        self.qr_image = None
        self.destroy()
        if self.master.winfo_exists():
            self.master.grab_set()
