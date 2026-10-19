"""Deliberate JSON-only endpoints for the local WebView renderer.

pywebview recursively inspects public attributes, so every object owned by this
bridge is private. Network calls stay in AppContext and accepted IO is drained
before the host closes the Engine.
"""

import base64
from collections import OrderedDict
from contextlib import nullcontext
import copy
import io
import json
import logging
import math
import os
import re
import threading
import time
import webbrowser
from pathlib import Path

from asoul_support.redaction import redact
from asoul_support.runtime import read_json, update_json
from asoul_support.secret_store import is_envelope
from desktop.interaction import action_reason, recovery_route
from desktop.storage import load_config


_EXCEPTION_NAME = re.compile(r"[（(][\w.]*?(?:Error|Exception)[）)]|[：:]\s*[\w.]*?(?:Error|Exception)\b")
_SECRET_FIELDS = {
    "sessdata", "bili_jct", "cookie", "cookies", "set-cookie", "authorization",
    "qrcode_key", "qr_login_context", "live_like_cookie", "pushplus_token",
    "access_token", "refresh_token", "secret_key",
}
_SETTING_FLAGS = (
    "auto_revive", "auto_danmaku_intimacy", "auto_like", "notify_on_live", "autostart", "paused",
)
_PENDING_MESSAGES = {
    "redo": "正在补齐任务", "wear": "正在佩戴粉丝牌", "reconnect": "正在请求重连",
    "remove": "正在移除主播", "settings": "正在保存并应用设置", "pause": "正在调整挂机状态",
    "check": "正在请求检查", "safety": "正在检查账号并解除保护暂停", "logout": "正在退出登录",
    "add": "正在添加主播", "import": "正在导入粉丝牌主播",
}


def _public(value):
    """Only JSON data crosses the boundary; secrets and raw exception names do not."""
    value = redact(value)
    if isinstance(value, dict):
        return {str(key): _public(item) for key, item in value.items()
                if str(key).lower() not in _SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    if isinstance(value, str):
        return _EXCEPTION_NAME.sub("（详情见日志）", value)
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    raise TypeError("Bridge responses must contain JSON data")


def _positive_id(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    raise ValueError("Invalid identifier")


def _signature(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def _png_uri(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _qr_data_uri(url):
    import qrcode
    from qrcode.image.pil import PilImage

    return _png_uri(qrcode.make(url, box_size=8, border=3, image_factory=PilImage))


class Api:
    """Exposed as window.pywebview.api; public members are endpoints only."""

    def __init__(self, engine, ui):
        self._engine, self._ui, self._root = engine, ui, Path(engine.root)
        self._mutations = threading.RLock()
        self._control_mutations = threading.RLock()
        self._state = threading.Condition(threading.RLock())
        self._closing = threading.Event()
        self._active = 0
        self._room_operations, self._controls = {}, {}
        self._snapshot_lock = threading.Lock()
        self._cache_lock = threading.RLock()
        self._last_snapshot = None
        self._ui_error = ""
        self._settings_signature = object()
        self._settings_cache = {}
        self._credentials_signature = object()
        self._credentials_cache = (False, "")
        self._medals_cache = None
        self._avatars = OrderedDict()
        self._qr_lock = threading.RLock()
        self._qr_generation = 0
        self._qr_session = None
        self._qr_cancel_event = None

    # Snapshot construction never waits for the Engine's monitor/control lock.
    def snapshot(self):
        busy, failed = True, False
        if self._snapshot_lock.acquire(blocking=False):
            try:
                try:
                    fresh = self._engine.snapshot(blocking=False)
                    if fresh is not None:
                        with self._cache_lock:
                            self._last_snapshot = copy.deepcopy(fresh)
                        busy = False
                except Exception:
                    logging.exception("Web snapshot failed")
                    failed = True
            finally:
                self._snapshot_lock.release()
        with self._cache_lock:
            snap = copy.deepcopy(self._last_snapshot) if self._last_snapshot is not None else {
                "account": "", "account_confirmed": False, "account_checked_at": 0,
                "paused": bool(self._engine.paused), "safety": {"blocked": False},
                "rows": [], "checking": False, "error": "",
            }
        with self._state:
            controls = copy.deepcopy(self._controls)
            rooms = copy.deepcopy(self._room_operations)
            ui_error = self._ui_error
        if failed:
            ui_error = "界面刷新失败，正在自动重试。"
        snap.update(engine_busy=busy, closing=self._closing.is_set(), ui_error=ui_error)
        try:
            snap["settings"] = self.settings()
        except Exception:
            logging.exception("Web settings read failed")
            snap["settings"] = dict(self._settings_cache)
            snap["ui_error"] = "设置无法读取，请检查本机配置后重试界面。"
        snap["accountInfo"] = self._account_info(snap)
        snap["operations"] = {"controls": controls, "rooms": {str(k): v for k, v in rooms.items()}}
        for row in snap.get("rows", []):
            operation = rooms.get(row.get("room"), {})
            row["operation"] = operation
            row["actions"] = {action: self._room_reason(snap, row, action, operation.get("pending", False))
                              for action in ("open", "redo", "reconnect", "wear", "remove")}
        snap["recovery"] = recovery_route(snap)
        snap["notifications"] = {
            "available": False, "experimental": True,
            "message": "尚未实测成功，功能暂不可用；不会发送任何消息。",
        }
        return _public(snap)

    def settings(self):
        with self._cache_lock:
            signature = (_signature(self._root / "settings.json"), _signature(self._root / "members.json"))
            if signature != self._settings_signature:
                config, _ = load_config(self._root)
                value = {key: config.get(key, False) for key in _SETTING_FLAGS}
                value["check_minutes"] = config.get("check_minutes", 30)
                try:
                    from desktop.windows import is_autostart_enabled

                    value["autostart"] = bool(is_autostart_enabled())
                except Exception:
                    logging.exception("Cannot read Windows autostart status")
                self._settings_cache = value
                self._settings_signature = signature
            return dict(self._settings_cache)

    def _account_info(self, snap):
        # Inspect only the protected envelope/presence. Refreshing a page must not
        # unseal a login, migrate it, or repeatedly register secrets.
        error = ""
        try:
            with self._cache_lock:
                path = self._root / "credentials.json"
                signature = _signature(path)
                if signature != self._credentials_signature:
                    saved = json.loads(path.read_text(encoding="utf-8-sig")) if signature else {}
                    if not isinstance(saved, dict):
                        raise ValueError("Invalid credentials object")
                    present = (bool(saved.get("payload") or saved.get("reference")) if is_envelope(saved)
                               else bool(saved.get("SESSDATA") and saved.get("bili_jct")))
                    self._credentials_cache = present, ""
                    self._credentials_signature = signature
                present, error = self._credentials_cache
        except (OSError, ValueError):
            logging.exception("Cannot inspect saved login")
            present, error = False, "登录信息无法读取，请重新扫码登录。"
        hold = snap.get("safety", {})
        if hold.get("kind") == "credentials":
            error = "登录信息无法读取，请重新扫码登录。"
        return {
            "signed_in": present, "name": snap.get("account", "") or "",
            "confirmed": bool(snap.get("account_confirmed")),
            "checked_at": snap.get("account_checked_at", 0), "safety": hold,
            "credentials_error": error,
        }

    def account(self):
        with self._cache_lock:
            snap = copy.deepcopy(self._last_snapshot)
        if snap is None:
            return self.snapshot()["accountInfo"]
        return _public(self._account_info(snap))

    def ready(self):
        try:
            return {"ok": bool(self._ui.renderer_ready())}
        except Exception:
            logging.exception("Renderer ready handshake failed")
            return {"ok": False, "error": "界面尚未就绪，请重试界面。"}

    def refresh(self):
        with self._state:
            self._ui_error = ""
        self._ui.push_now()
        return {"ok": True}

    # Room writes and controls have separate serial lanes. Reservations happen
    # first so duplicate room actions cannot queue behind a slow network call.
    def _run(self, kind, operation, *, room=None, policy=None, mutating=True):
        with self._state:
            if self._closing.is_set():
                return {"ok": False, "error": "正在退出，当前不接受新操作。"}
            states, key = (self._room_operations, room) if room is not None else (self._controls, kind)
            if states.get(key, {}).get("pending"):
                return {"ok": False, "error": "该直播间已有操作正在执行，请等待结果。" if room is not None
                        else "该操作正在执行，请等待结果。"}
            states[key] = {"kind": kind, "pending": True,
                           "message": _PENDING_MESSAGES.get(kind, "正在处理，请稍候"), "started": time.time()}
            self._active += 1
        self._ui.push_now()
        result = {"ok": False, "error": "操作未成功，请重试或查看活动记录。"}
        try:
            # Pause/reconnect/check remain usable while a room task waits on IO.
            # Engine and task services own the actual shared-data locks.
            control = kind in {"pause", "check", "settings", "safety", "reconnect", "remove", "logout"}
            lock = self._control_mutations if control else self._mutations
            with lock if mutating else nullcontext():
                if self._closing.is_set():
                    result = {"ok": False, "error": "程序正在退出，尚未开始的操作已取消。"}
                else:
                    row = None
                    reason = ""
                    if room is not None:
                        snap = self.snapshot()
                        row = next((item for item in snap.get("rows", []) if item.get("room") == room), {})
                        reason = self._room_reason(snap, row, policy or kind)
                    returned = ({"ok": False, "error": reason} if reason else
                                operation(row) if room is not None else operation())
                    result = _public(returned)
        except Exception:
            logging.exception("Web action failed action=%s room=%s", kind, room)
            result = {"ok": False, "error": "操作未成功，请重试或查看活动记录。"}
        finally:
            with self._state:
                states[key].update(pending=False, ok=bool(result.get("ok")),
                                   message=result.get("message") or result.get("error", ""))
                # Reads need no persistent operation history, and avatar queries
                # must not grow controls without bound.
                if not mutating:
                    states.pop(key, None)
                self._active -= 1
                self._state.notify_all()
            self._ui.push_now()
        return result

    @staticmethod
    def _room_reason(snap, row, action, pending=False):
        if action != "remove":
            return action_reason(snap, row, action, pending=pending)
        if not row or not row.get("room"):
            return "请先选择主播。"
        if snap.get("closing"):
            return "正在退出，当前不接受新操作。"
        return "该直播间已有操作正在执行，请等待结果。" if pending else ""

    def _room_action(self, room, kind, operation):
        try:
            room = _positive_id(room)
        except ValueError:
            return {"ok": False, "error": "直播间编号无效，请重新选择主播。"}
        return self._run(kind, operation, room=room)

    def save_settings(self, changes):
        if not isinstance(changes, dict) or set(changes) - {*_SETTING_FLAGS, "check_minutes"}:
            return {"ok": False, "error": "设置格式无效，请重新打开设置。"}
        for key in _SETTING_FLAGS:
            if key in changes and type(changes[key]) is not bool:
                return {"ok": False, "error": "设置开关必须为 true 或 false。"}
        payload = dict(changes)
        if "check_minutes" in payload:
            value = payload["check_minutes"]
            if isinstance(value, str) and value.isascii() and value.isdigit():
                value = int(value)
            if type(value) is not int or not 1 <= value <= 1440:
                return {"ok": False, "error": "检查间隔需为 1 到 1440 之间的整数分钟。"}
            payload["check_minutes"] = value

        def save():
            def change(_):
                # Normalize legacy danmaku/live_likes before removing their keys.
                config, _members = load_config(self._root)
                return {**config, **payload}

            try:
                update_json(self._root / "settings.json", change, {})
            except (OSError, ValueError, RuntimeError):
                logging.exception("Saving web settings failed")
                return {"ok": False, "error": "设置未能保存，请检查本机文件权限和配置。"}
            warning = ""
            if "autostart" in payload:
                try:
                    from desktop.windows import set_autostart

                    if not set_autostart(payload["autostart"]):
                        warning = "设置已保存并应用，但 Windows 自启动未能修改。"
                except Exception:
                    logging.exception("Autostart change failed")
                    warning = "设置已保存并应用，但 Windows 自启动未能修改。"
            try:
                self._ui.apply_settings()
            except Exception:
                logging.exception("Applying saved web settings failed")
                return {"ok": False, "saved": True, "error": "设置已保存，但应用失败，请重试保存或查看活动记录。"}
            result = {"ok": True}
            if warning:
                result["warning"] = warning
            return result

        return self._run("settings", save)

    def set_paused(self, paused):
        if type(paused) is not bool:
            return {"ok": False, "error": "暂停状态必须为 true 或 false。"}
        return self._pause(paused)

    def toggle_pause(self):
        return self._pause(None)

    def _pause(self, value):
        def change():
            paused = not bool(self._engine.paused) if value is None else value
            self._engine.set_paused(paused)
            return {"ok": True, "paused": paused}

        return self._run("pause", change)

    def check_now(self):
        def check():
            self._engine.check_now()
            return {"ok": True}

        return self._run("check", check)

    def resume_safety(self):
        def resume():
            ok, message = self._engine.resume_safety(confirmed=True)
            return {"ok": bool(ok), "message" if ok else "error": message}

        return self._run("safety", resume)

    def redo(self, room, task_type="all"):
        if task_type not in ("all", "danmaku", "like"):
            return {"ok": False, "error": "未知任务类型，请重新选择。"}

        def redo(row):
            result = self._engine.application.redo(row["room"], row.get("uid"), task_type) or {}
            ok = bool(result.get("success"))
            errors = [result.get("error")] + [(result.get(key) or {}).get("error") for key in ("danmaku", "like")]
            detail = "；".join(str(error) for error in errors if error) or "任务进度尚未确认完成"
            message = f"【{row.get('name', room)}】" + ("所选任务已确认完成" if ok else "任务未完成：" + detail)
            if ok:
                self._engine.check_now()
            return {"ok": ok, "message" if ok else "error": message}

        return self._room_action(room, "redo", redo)

    def reconnect(self, room):
        def reconnect(row):
            ok, message = self._engine.reconnect_room(row["room"])
            return {"ok": bool(ok), "message" if ok else "error": message}

        return self._room_action(room, "reconnect", reconnect)

    def wear_medal(self, room):
        def wear(row):
            result = self._engine.application.wear(row.get("uid"))
            if result == "ok":
                self._engine.check_now()
                return {"ok": True, "message": "粉丝牌已佩戴。"}
            return {"ok": False, "error": "没有可佩戴的粉丝牌，请先同步粉丝牌。" if result == "no_medal"
                    else "佩戴失败，请核对登录状态后重试。"}

        return self._room_action(room, "wear", wear)

    def remove_member(self, room):
        def remove(row):
            self._engine.application.remove_member(row["room"])
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True}

        return self._room_action(room, "remove", remove)

    def open_room(self, room):
        try:
            room = _positive_id(room)
            ok = webbrowser.open(f"https://live.bilibili.com/{room}")
        except Exception:
            logging.exception("Opening live room failed")
            ok = False
        return {"ok": bool(ok), **({} if ok else {"error": "无法打开直播间，请检查默认浏览器。"})}

    def open_logs(self):
        try:
            os.startfile(str(self._root / "logs"))
        except (OSError, AttributeError):
            logging.exception("Opening log directory failed")
            return {"ok": False, "error": "无法打开日志目录。"}
        return {"ok": True}

    def resolve_member(self, query):
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "请输入房间号、短号、UID 或直播间链接。"}

        def resolve():
            info = self._engine.application.resolve(query.strip())
            return {"ok": True, "member": info} if info else {
                "ok": False, "error": "没有找到对应主播，请核对房间号或链接。"}

        return self._run("resolve", resolve, mutating=False)

    def add_member(self, query):
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "请输入房间号、短号、UID 或直播间链接。"}

        def add():
            info = self._engine.application.resolve(query.strip())
            if not info:
                return {"ok": False, "error": "没有找到对应主播，请核对房间号或链接。"}
            self._engine.application.add_members([info])
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True, "member": info}

        return self._run("add", add)

    def _fetch_medals(self):
        signature = _signature(self._root / "credentials.json")
        medals = self._engine.application.medals()
        if signature != _signature(self._root / "credentials.json"):
            raise ValueError("Login changed while fetching medals")
        members = read_json(self._root / "members.json", [])
        watched = {member["room"] for member in members}
        rows = [{**member, "watched": member["room"] in watched} for member in medals]
        rows.sort(key=lambda row: (row["watched"], -int(row.get("level") or 0), row["room"]))
        with self._cache_lock:
            self._medals_cache = signature, rows
        return rows

    def medals(self):
        def fetch():
            try:
                return {"ok": True, "medals": self._fetch_medals()}
            except (ValueError, RuntimeError):
                logging.exception("Fetching medal list failed")
                return {"ok": False, "need_login": True, "error": "粉丝牌读取失败，请检查登录和网络后重试。"}

        return self._run("medals", fetch, mutating=False)

    def import_medals(self, uids):
        try:
            if not isinstance(uids, list) or not uids:
                raise ValueError("No selection")
            selected = {_positive_id(uid) for uid in uids}
        except ValueError:
            return {"ok": False, "error": "请选择有效的粉丝牌主播。"}

        def import_selected():
            with self._cache_lock:
                cached = self._medals_cache
            rows = (cached[1] if cached and cached[0] == _signature(self._root / "credentials.json")
                    else self._fetch_medals())
            members = read_json(self._root / "members.json", [])
            watched = {member["room"] for member in members}
            additions = [member for member in rows if member["uid"] in selected and member["room"] not in watched]
            if not additions:
                return {"ok": False, "error": "没有可导入的新主播。"}
            self._engine.application.add_members(additions)
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True, "count": len(additions)}

        return self._run("import", import_selected)

    def avatar(self, uid, url=""):
        try:
            uid = _positive_id(uid)
        except ValueError:
            return {"ok": False, "error": "主播编号无效。"}

        def fetch():
            # The renderer cannot turn this endpoint into arbitrary URL/UID IO.
            _config, members = load_config(self._root)
            if not any(member.get("uid") == uid for member in members):
                return {"ok": False, "error": "该主播已不在关注列表中。"}
            with self._cache_lock:
                cached = self._avatars.get(uid)
                snap = self._last_snapshot or {}
                public_url = next((row.get("avatar_url", "") for row in snap.get("rows", [])
                                   if row.get("uid") == uid), "")
                if cached and time.monotonic() - cached[0] < 86400:
                    self._avatars.move_to_end(uid)
                    return {"ok": True, "data_uri": cached[1]}
            from desktop.avatars import load_avatar

            image = load_avatar(self._root, uid, public_url)
            try:
                data_uri = _png_uri(image)
            finally:
                image.close()
            with self._cache_lock:
                self._avatars[uid] = time.monotonic(), data_uri
                while len(self._avatars) > 64:
                    self._avatars.popitem(last=False)
            return {"ok": True, "data_uri": data_uri}

        return self._run(f"avatar:{uid}", fetch, mutating=False)

    # Cancellation invalidates a generation before waiting for any network IO.
    def _cancel_qr(self):
        with self._qr_lock:
            self._qr_generation += 1
            cancel, session = self._qr_cancel_event, self._qr_session
            if cancel is not None:
                cancel.set()
            self._qr_session = self._qr_cancel_event = None
            generation = self._qr_generation
        if session is not None:
            self._dispose_qr(session)
        return generation

    @staticmethod
    def _dispose_qr(session):
        try:
            session.cancel()
        except Exception:
            logging.exception("QR session cleanup failed")

    def _qr_current(self, generation, session, cancel):
        return (not self._closing.is_set() and not cancel.is_set()
                and generation == self._qr_generation and session is self._qr_session)

    def qr_start(self):
        with self._state:
            if self._closing.is_set():
                return {"ok": False, "error": "正在退出，当前不接受新操作。"}
            self._active += 1
        generation = self._cancel_qr()
        session = None
        started = False
        cancel = threading.Event()
        try:
            from asoul_support.qr_login import QrLoginSession

            session = QrLoginSession()
            with self._qr_lock:
                if self._closing.is_set() or generation != self._qr_generation:
                    return {"ok": False, "cancelled": True, "generation": generation}
                self._qr_session, self._qr_cancel_event = session, cancel
            data_uri = _qr_data_uri(session.generate())
            with self._qr_lock:
                if not self._qr_current(generation, session, cancel):
                    return {"ok": False, "cancelled": True, "generation": generation}
                with self._state:
                    self._active += 1
                try:
                    threading.Thread(target=self._qr_poll, args=(generation, session, cancel),
                                     name="web-qr", daemon=True).start()
                    started = True
                except Exception:
                    self._io_finished()
                    raise
            return {"ok": True, "data_uri": data_uri, "generation": generation}
        except Exception:
            logging.exception("QR session creation failed")
            return {"ok": False, "generation": generation,
                    "error": "无法连接 B 站登录服务，请检查网络后刷新二维码。"}
        finally:
            if session is not None and not started:
                with self._qr_lock:
                    if session is self._qr_session:
                        self._qr_session = self._qr_cancel_event = None
                self._dispose_qr(session)
            self._io_finished()

    def qr_refresh(self):
        return self.qr_start()

    def _emit_qr(self, generation, session, cancel, payload):
        with self._qr_lock:
            if self._qr_current(generation, session, cancel):
                self._ui.emit("qr_state", _public({"generation": generation, **payload}))

    def _qr_poll(self, generation, session, cancel):
        from asoul_support.qr_login import POLL_INTERVAL

        try:
            while not cancel.wait(POLL_INTERVAL):
                result = session.poll()
                with self._qr_lock:
                    if not self._qr_current(generation, session, cancel):
                        return
                if result.state == "confirmed":
                    cookies = result.credentials
                    valid, account = self._engine.application.validate_credentials(
                        cookies["SESSDATA"], cookies["bili_jct"])
                    if not valid:
                        self._emit_qr(generation, session, cancel, {
                            "state": "error", "message": "扫码已确认，但登录验证未通过，请重新扫码。"})
                        return
                    with self._mutations:
                        with self._qr_lock:
                            if not self._qr_current(generation, session, cancel):
                                return
                            from asoul_support.runtime import save_login

                            options = {"context": result.context} if result.context else {}
                            save_login(cookies["SESSDATA"], cookies["bili_jct"],
                                       self._root / "credentials.json", **options)
                        self._ui.apply_settings()
                        self._emit_qr(generation, session, cancel,
                                      {"state": "confirmed", "account": account})
                    return
                if result.state not in ("waiting", "scanned", "expired"):
                    raise ValueError("Unexpected QR state")
                self._emit_qr(generation, session, cancel, {"state": result.state})
                if result.state == "expired":
                    return
        except Exception:
            logging.exception("QR polling failed")
            self._emit_qr(generation, session, cancel, {
                "state": "error", "message": "扫码登录失败，请刷新二维码重试。"})
        finally:
            self._dispose_qr(session)
            self._io_finished()

    def qr_cancel(self):
        return {"ok": True, "generation": self._cancel_qr()}

    def logout(self):
        self._cancel_qr()

        def logout():
            self._cancel_qr()
            from asoul_support.runtime import save_login

            save_login("", "", self._root / "credentials.json")
            self._ui.apply_settings()
            return {"ok": True}

        return self._run("logout", logout)

    def _set_ui_error(self, message):
        with self._state:
            self._ui_error = message

    def _io_finished(self):
        with self._state:
            self._active -= 1
            self._state.notify_all()

    def _begin_shutdown(self):
        # Match _run's admission lock so shutdown cannot overlook an accepted call.
        with self._state:
            self._closing.set()
        self._cancel_qr()

    def _wait_for_io(self):
        with self._state:
            self._state.wait_for(lambda: self._active == 0)

    def window(self, action):
        try:
            methods = {"minimize": self._ui.minimize, "close": self._ui.close_window,
                       "show": self._ui.show, "exit": self._ui.quit, "quit": self._ui.quit}
            method = methods.get(action)
            if method is None:
                return {"ok": False, "error": "未知窗口操作。"}
            result = method()
            return {"ok": result is not False}
        except Exception:
            logging.exception("Window action failed")
            return {"ok": False, "error": "窗口操作失败，请重试。"}

    def quit(self):
        return self.window("quit")

    def version(self):
        from asoul_support.runtime import APP_VERSION

        return {"version": APP_VERSION}
