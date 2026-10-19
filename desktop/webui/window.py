"""Local WebView2 host, tray commands and bounded background dispatch.

The page contains no remote assets. Desktop controls use the same bridge paths
as renderer calls, and a ready handshake keeps events queued until window.LS
has installed its handlers.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import math
import os
import queue
import threading
import time
from pathlib import Path

from desktop.storage import read_json

ASSETS = Path(__file__).resolve().parent / "assets"
INDEX = ASSETS / "index.html"
PUSH_INTERVAL = 0.75


class WebHost:
    """Own the native window, tray and Engine lifecycle."""

    def __init__(self, engine, *, show=True):
        from .api import Api

        self._engine = engine
        self._window = None
        self._tray = None
        self._show = show
        self._api = Api(engine, self)
        self._stop = threading.Event()
        self._closing = threading.Event()
        self._closed = threading.Event()
        self._ready = threading.Event()
        self._wake = threading.Event()
        self._tray_ready = threading.Event()
        self._lifecycle_lock = threading.RLock()
        self._queue = queue.Queue()
        self._commands = queue.Queue()
        self._control = ThreadPoolExecutor(max_workers=1, thread_name_prefix="web-control")
        self._pending_controls = set()
        self._pump_thread = None
        self._tray_thread = None
        self._shutdown_thread = None
        self._watch_notice_day = None
        self._watch_notices = set()
        self._last_tray_color = None

    def run(self, show=True, login=False):
        import webview

        try:
            self._window = webview.create_window(
                "LiveSupport · 直播助手", url=INDEX.as_uri(), js_api=self._api,
                width=1180, height=760, min_size=(900, 600), background_color="#faf9f7",
                text_select=False, hidden=not (show or login), zoomable=True,
            )
            self._window.events.closing += self._on_closing
            self._window.events.closed += self._on_closed
            self._window.events.loaded += self._on_loaded
            self._start_tray()
            self._engine.notify_callback = lambda name, title: self._commands.put(("notify", name, title))
            self._engine.start()
            self._pump_thread = threading.Thread(target=self._pump, name="web-push", daemon=True)
            self._pump_thread.start()
            if login:
                self.emit("open_login", {})
            webview.start(gui="edgechromium", debug=False, private_mode=False)
        finally:
            self.quit()
            self._closed.wait()
            if self._pump_thread is not None and self._pump_thread is not threading.current_thread():
                self._pump_thread.join(timeout=5)

    def _on_loaded(self):
        # loaded/shown can fire before React has created window.LS. The pump
        # checks the actual handlers; ready() also verifies them before pushing.
        self._ready.clear()
        self._wake.set()
        hook = getattr(self, "window_loaded_hook", None)
        if callable(hook):
            try:
                hook()
            except Exception:
                logging.exception("Window loaded hook failed")
                self._api._set_ui_error("界面初始化失败，请重试界面。")

    def renderer_ready(self):
        if self._closing.is_set() or self._window is None:
            return False
        ready = bool(self._eval("Boolean(window.LS && typeof window.LS.onSnapshot === 'function' "
                                "&& typeof window.LS.onEvent === 'function')"))
        if ready:
            self._ready.set()
            self._wake.set()
        return ready

    def _on_closing(self):
        # pywebview cancels a close when this handler returns False. Allow the
        # final destroy only after Engine.close and accepted IO have finished.
        if self._closed.is_set():
            return True
        self.close_window()
        return False

    def _on_closed(self):
        self.quit()

    def _has_tray(self):
        return (self._tray is not None and self._tray_ready.is_set()
                and self._tray_thread is not None and self._tray_thread.is_alive()
                and bool(self._tray.visible))

    def close_window(self):
        if not self._closing.is_set() and self._has_tray():
            return self.hide()
        self.quit()
        return True

    def hide(self):
        try:
            self._window.hide()
            return True
        except Exception:
            logging.exception("Hiding window failed")
            return False

    def show(self):
        try:
            self._window.show()
            self._window.restore()
            return True
        except Exception:
            logging.exception("Showing window failed")
            return False

    def minimize(self):
        try:
            self._window.minimize()
            return True
        except Exception:
            logging.exception("Minimizing window failed")
            return False

    def quit(self):
        with self._lifecycle_lock:
            if self._shutdown_thread is not None:
                return True
            self._closing.set()
            self._api._begin_shutdown()
            self._wake.set()
            self._shutdown_thread = threading.Thread(target=self._shutdown, name="web-exit", daemon=True)
            self._shutdown_thread.start()
        return True

    def _shutdown(self):
        try:
            # Stop Engine/Job before waiting for potentially long manual IO.
            # The bridge already cancelled QR generations and rejects new work.
            try:
                self._engine.close()
            except Exception:
                logging.exception("Engine shutdown failed")
                try:
                    self._engine.job.close()
                except Exception:
                    logging.exception("Worker job cleanup failed")
            self._api._wait_for_io()
            self._control.shutdown(wait=True, cancel_futures=True)
        finally:
            self._stop.set()
            self._wake.set()
            self._stop_tray()
            self._closed.set()
            if self._window is not None:
                try:
                    self._window.destroy()
                except Exception:
                    logging.exception("Window destruction failed")

    def emit(self, event, payload):
        """Queue a safe JSON event until the renderer has installed handlers."""
        if not self._stop.is_set():
            self._queue.put((event, payload))
            self._wake.set()

    def push_now(self):
        self._wake.set()

    def _pump(self):
        next_snapshot = 0.0
        while not self._stop.is_set():
            try:
                self._read_commands()
                if not self._ready.is_set():
                    self.renderer_ready()
                if self._ready.is_set():
                    self._drain()
                    now = time.monotonic()
                    if now >= next_snapshot:
                        snapshot = self._api.snapshot()
                        pushed = self._eval("(function(){if(!window.LS || typeof window.LS.onSnapshot !== 'function') "
                                            "return false; window.LS.onSnapshot(" + _js(snapshot) + "); return true;})()")
                        if pushed:
                            self._update_tray(snapshot)
                            self._notify_watch_warnings(snapshot)
                        else:
                            self._ready.clear()
                        next_snapshot = now + PUSH_INTERVAL
            except Exception:
                logging.exception("Web push failed")
                self._ready.clear()
                self._api._set_ui_error("界面刷新失败，正在自动重试；可重试界面或查看日志。")
            self._wake.wait(timeout=0.2)
            self._wake.clear()

    def _drain(self):
        while not self._stop.is_set():
            try:
                event, payload = self._queue.get_nowait()
            except queue.Empty:
                return
            pushed = self._eval("(function(){if(!window.LS || typeof window.LS.onEvent !== 'function') return false; "
                                "window.LS.onEvent(" + _js({"type": event, "payload": payload}) + "); return true;})()")
            if not pushed:
                self._queue.put((event, payload))
                self._ready.clear()
                return

    def _eval(self, script):
        if self._window is None:
            return None
        return self._window.evaluate_js(script)

    def apply_settings(self):
        self._engine.reload_settings()
        self.emit("settings_changed", self._api.settings())
        self.push_now()

    def _read_commands(self):
        for path in sorted((self._engine.root / "commands").glob("*.json")):
            try:
                request = read_json(path, {})
                if not isinstance(request, dict):
                    raise ValueError("Command must be an object")
                created = request.get("created")
                if type(created) not in (int, float) or not math.isfinite(created):
                    raise ValueError("Invalid command time")
                if 0 <= time.time() - created < 60:
                    command = request.get("command")
                    if command in {"show", "login", "pause", "resume", "check", "exit"}:
                        self._commands.put(command)
            except (OSError, ValueError, TypeError):
                logging.warning("Ignoring unreadable desktop command")
            finally:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logging.exception("Cannot remove processed desktop command")
        while not self._commands.empty():
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            if isinstance(command, tuple) and command[0] == "notify":
                _, name, title = command
                self._notify(f"【{name}】开播了：{title}", "LiveSupport · 开播提醒")
                continue
            if self._closing.is_set() and command not in {"show", "logs", "exit"}:
                continue
            if command == "exit":
                self.quit()
            elif command == "show":
                self.show()
            elif command in {"login", "settings", "add_member", "sync_medals", "safety"}:
                self.show()
                event, payload = {
                    "login": ("open_login", {}), "settings": ("show_page", {"page": "automation"}),
                    "add_member": ("add_member", {}), "sync_medals": ("sync_medals", {}),
                    "safety": ("show_page", {"page": "account"}),
                }[command]
                self.emit(event, payload)
            elif command in {"pause", "resume", "toggle", "check", "logs"}:
                operation = {
                    "pause": lambda: self._api.set_paused(True), "resume": lambda: self._api.set_paused(False),
                    "toggle": self._api.toggle_pause, "check": self._api.check_now, "logs": self._api.open_logs,
                }[command]
                self._submit_control(command, operation)

    def _submit_control(self, key, operation):
        with self._lifecycle_lock:
            if self._closing.is_set() or key in self._pending_controls:
                return
            self._pending_controls.add(key)

            def run():
                try:
                    result = operation()
                    if not result.get("ok"):
                        self.emit("action_result", result)
                except Exception:
                    logging.exception("Desktop command failed command=%s", key)
                    self.emit("action_result", {"ok": False, "error": "操作失败，请重试或查看日志。"})
                finally:
                    with self._lifecycle_lock:
                        self._pending_controls.discard(key)
                    self.push_now()

            try:
                self._control.submit(run)
            except RuntimeError:
                self._pending_controls.discard(key)
                logging.exception("Desktop command was not submitted")

    def _start_tray(self):
        try:
            import pystray
            # The existing icon is the only dependency on Tk presentation code.
            from desktop.widgets import icon_image

            def item(label, command, default=False):
                return pystray.MenuItem(label, lambda: self._commands.put(command), default=default)

            menu = pystray.Menu(
                item("查看状态", "show", default=True),
                item(lambda _: "恢复挂机" if self._engine.paused else "暂停挂机", "toggle"),
                item("立即检查", "check"), item("处理账号保护暂停", "safety"),
                item("添加主播", "add_member"), item("同步粉丝牌", "sync_medals"),
                item("系统设置", "settings"), item("账号登录", "login"), item("查看日志", "logs"),
                pystray.Menu.SEPARATOR, item("退出（停止全部挂机）", "exit"),
            )
            self._tray = pystray.Icon("LiveSupport", icon_image(), "LiveSupport · 正在启动", menu)

            def setup(icon):
                icon.visible = True
                self._tray_ready.set()

            def run():
                try:
                    self._tray.run(setup=setup)
                except Exception:
                    logging.exception("Tray start failed")
                finally:
                    self._tray_ready.clear()
                    if not self._closing.is_set():
                        self._commands.put("show")
                        self._wake.set()

            self._tray_thread = threading.Thread(target=run, name="tray", daemon=True)
            self._tray_thread.start()
        except Exception:
            logging.exception("Tray unavailable")
            self._tray = None
            self._commands.put("show")

    def _stop_tray(self):
        self._tray_ready.clear()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                logging.exception("Tray shutdown failed")
        if self._tray_thread is not None and self._tray_thread is not threading.current_thread():
            self._tray_thread.join(timeout=5)

    def _notify(self, message, title):
        if not self._has_tray():
            return False
        from .api import _public

        try:
            self._tray.notify(_public(message), title=title)
            return True
        except Exception:
            logging.exception("Desktop notification failed")
            return False

    def _update_tray(self, snap):
        if not self._has_tray():
            return
        rows = snap.get("rows", [])
        active = sum(bool(row.get("heartbeat_healthy")) for row in rows)
        warnings = bool(snap.get("error") or snap.get("ui_error") or any(
            row.get("connection_warning") or row.get("watch_warning") for row in rows))
        title = "需要处理" if warnings else "已暂停" if snap.get("paused") else f"{active} 个直播间挂机中" if active else "等待开播"
        self._tray.title = "LiveSupport · " + title
        color = "#f2ab55" if warnings else "#9ca9af" if snap.get("paused") else "#63d4b2"
        if color != self._last_tray_color:
            from desktop.widgets import icon_image

            self._tray.icon = icon_image(color)
            self._last_tray_color = color
        self._tray.update_menu()

    def _notify_watch_warnings(self, snap):
        from asoul_support.runtime import task_day

        day = task_day()
        if self._watch_notice_day != day:
            self._watch_notice_day = day
            self._watch_notices.clear()
        # Match TrayUI: a neutral watch_note (rotation) is never a warning.
        for row in snap.get("rows", []):
            connection = row.get("connection_warning")
            warning = connection or row.get("watch_warning")
            if not warning:
                continue
            watch = row.get("watch_progress", {})
            key = (row["room"], row.get("session_id") or row.get("started"),
                   ("connection", row.get("last_heartbeat")) if connection else
                   (watch.get("status"), watch.get("warning_since")))
            if key in self._watch_notices:
                continue
            if self._notify(f"【{row['name']}】{warning}",
                            "LiveSupport · 连接提醒" if connection else "LiveSupport · 看播收益提醒"):
                self._watch_notices.add(key)


def _js(value):
    from .api import _public

    text = json.dumps(_public(value), ensure_ascii=False, allow_nan=False)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def available():
    """Detect installed user/machine runtimes without initializing WinForms."""
    if os.name != "nt" or not INDEX.is_file():
        return False
    try:
        import webview
        import winreg

        if webview.settings.get("WEBVIEW2_RUNTIME_PATH"):
            return Path(webview.settings["WEBVIEW2_RUNTIME_PATH"]).is_dir()
        clients = ("{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                   "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
                   "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
                   "{65C35B14-6C1D-4122-AC46-7148CC9D6497}")
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                for client in clients:
                    try:
                        with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{client}",
                                            0, winreg.KEY_READ | view) as key:
                            version, _ = winreg.QueryValueEx(key, "pv")
                        if int(str(version).split(".")[0]) >= 86:
                            return True
                    except (OSError, ValueError):
                        continue
        candidates = [Path(base) / "Microsoft/EdgeWebView/Application" for base in (
            os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
            os.environ.get("LOCALAPPDATA", "")) if base]
        return any(path.is_dir() for path in candidates)
    except ImportError:
        return False
    except Exception:
        logging.exception("WebView2 runtime detection failed")
        return False
