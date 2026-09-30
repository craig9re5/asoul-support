from .credentials import load_saved
from .http import get_json, post_form, post_empty, request_json, require_data

"\nA-SOUL 直播心跳挂机 — 检测成员开播 → 移动端心跳涨亲密度。\n使用 X25Kn E/X 协议（纯 Python HMAC 签名，无需外部服务）。\n严格遵循服务端下发的心跳间隔，避免 time check failed。\n需要成员正在直播才有效。\n"
import argparse
import hashlib
import json
import os
import random
import re
import string
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from .check_auth import check_login
from .credentials import cookie_path, parse_cookie_header
from .danmaku_pacing import send_paced
from .members import MEMBERS, load_members
from .videos import _sign_wbi, get_mixin_key
from .runtime import (
    data_dir,
    append_event,
    EVENT_CONTEXT,
    FileLock,
    account_key,
    task_day,
    read_json,
    write_json,
)
from .context import CURRENT, runtime_path
from .http import get_json, post_form, post_empty, request_json
from .session_headers import session_headers

_DISCORD_TARGET = os.environ.get("ASOUL_DISCORD_TARGET")


def _notify(msg: str):
    """发送 Discord 通知"""
    context = CURRENT.get()
    if context is not None:
        if context.notify is not None:
            context.notify(msg)
        return
    if not _DISCORD_TARGET:
        return
    try:
        subprocess.run(
            [
                "openclaw",
                "message",
                "send",
                "--channel",
                "discord",
                "--target",
                _DISCORD_TARGET,
                "--message",
                msg,
            ],
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log({"type": "notification_error", "error": type(exc).__name__})


_LOG_DIR = data_dir() / "logs"
_LOCK_DIR = data_dir() / "locks"
_LOG_FILE = _LOG_DIR / "activity.jsonl"
_TASK_STATE_DIR = data_dir() / "state" / "tasks"


def _log(event: dict):
    """追加一条活动记录到日志文件"""
    append_event(_runtime_path("_LOG_FILE"), event)


def _runtime_path(name):
    return runtime_path(name, globals()[name])


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_COOKIE_PATHS = [cookie_path()]


def load_cookies():
    return load_saved(_COOKIE_PATHS)


def _make_headers(sessdata: str, bili_jct: str, referer: str = "https://live.bilibili.com") -> dict:
    return {**session_headers(sessdata, bili_jct, referer), "Origin": "https://live.bilibili.com"}


def _get_json(url, headers, timeout=10):
    return get_json(url, headers, timeout)


def _post_form(url, data, headers, timeout=10):
    return post_form(url, data, headers, timeout)


def _post_json(url, data, timeout=10):
    return request_json(
        url,
        {"Content-Type": "application/json"},
        data=json.dumps(data).encode("utf-8"),
        timeout=timeout,
    )


def _send_danmaku(room_id: int, msg: str, sessdata: str, bili_jct: str) -> bool:
    """发送一条弹幕"""
    url = "https://api.live.bilibili.com/msg/send"
    data = {
        "bubble": "0",
        "msg": msg,
        "color": "16777215",
        "mode": "1",
        "fontsize": "25",
        "rnd": str(int(time.time())),
        "roomid": str(room_id),
        "csrf": bili_jct,
        "csrf_token": bili_jct,
    }
    headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    try:
        resp = send_paced(lambda: _post_form(url, data, headers))
    except (OSError, TimeoutError) as exc:
        resp = {"code": -1, "message": type(exc).__name__}
    if resp and resp.get("code") == 0:
        return True
    code = (resp or {}).get("code")
    message = str((resp or {}).get("message", "无响应"))[:120]
    print(f"    ⚠️  弹幕发送失败：[{code}] {message}", file=sys.stderr)
    _log({"type": "danmaku_send_error", "room_id": room_id, "code": code, "message": message})
    return False


def get_fans_club_task_info(room_id: int, anchor_uid: int, sessdata: str, bili_jct: str) -> Dict:
    """获取粉丝团任务信息及灯牌点亮状态"""
    params = {
        "csrf": bili_jct,
        "platform": "pc",
        "room_id": str(room_id),
        "scene": "club",
        "target_id": str(anchor_uid),
        "web_location": "444.260",
    }
    url = (
        "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/GetActivatedMedalInfo?"
        + urllib.parse.urlencode(params)
    )
    headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    resp = _get_json(url, headers)
    if resp and resp.get("code") == 0 and isinstance(resp.get("data"), dict):
        return resp["data"]
    return {}


def get_viewer_uid(sessdata: str, bili_jct: str) -> Optional[int]:
    """Get the logged-in viewer UID required by the live-like report API."""
    headers = _make_headers(sessdata, bili_jct, "https://www.bilibili.com/")
    resp = _get_json("https://api.bilibili.com/x/web-interface/nav", headers)
    if not resp or resp.get("code") != 0:
        return None
    data = resp.get("data") or {}
    if data.get("isLogin") is not True:
        return None
    try:
        uid = int(data.get("mid", 0))
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def _live_like_headers(
    room_id: int, viewer_uid: int, sessdata: str, bili_jct: str
) -> Optional[dict]:
    """Use one matching QR or legacy session for live-like requests."""
    saved = load_cookies() or {}
    context = saved.get("qr_login_context")
    if context is not None:
        from .login_fields import login_context

        try:
            context = login_context(context.get("cookies"), context.get("user_agent"))
        except (ValueError, AttributeError):
            return None
        parts = context["cookies"]
        if (
            saved.get("SESSDATA") != sessdata
            or saved.get("bili_jct") != bili_jct
            or parts.get("SESSDATA") != sessdata
            or parts.get("bili_jct") != bili_jct
            or parts.get("DedeUserID") != str(viewer_uid)
        ):
            return None
        headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
        headers.update(
            {
                "Cookie": "; ".join(f"{name}={value}" for name, value in sorted(parts.items())),
                "User-Agent": context["user_agent"],
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        return headers
    raw = saved.get("live_like_cookie", "")
    if not isinstance(raw, str):
        return None
    try:
        parts = parse_cookie_header(raw)
    except ValueError:
        return None
    if (
        parts.get("SESSDATA") != sessdata
        or parts.get("bili_jct") != bili_jct
        or parts.get("DedeUserID") != str(viewer_uid)
    ):
        return None
    headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    headers["Cookie"] = raw
    headers["Accept"] = "application/json, text/plain, */*"
    headers["Accept-Language"] = "zh-CN,zh;q=0.9"
    ua = saved.get("live_like_user_agent")
    if not isinstance(ua, str) or not ua or "\r" in ua or ("\n" in ua):
        return None
    headers["User-Agent"] = ua
    return headers


def _post_empty_json(url, headers, timeout=10):
    return post_empty(url, headers, timeout)


def check_live_status(room_ids, sessdata, bili_jct):
    members = load_members()
    selected = [m for m in members if m["room"] in room_ids]
    data = urllib.parse.urlencode([("uids[]", m["uid"]) for m in selected]).encode("utf-8")
    body = (
        request_json(
            "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            {
                **_make_headers(sessdata, bili_jct),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data,
        )
        if selected
        else {}
    )
    result = {}
    if body.get("code") == 0:
        uid_to_room = {m["uid"]: m["room"] for m in selected}
        for uid, info in (body.get("data") or {}).items():
            if int(uid) in uid_to_room and info.get("live_status") in (0, 1, 2):
                result[uid_to_room[int(uid)]] = {
                    "live_status": info["live_status"],
                    "title": info.get("title", ""),
                    "area_name": info.get("area_v2_name", ""),
                    "live_time": info.get("live_time", ""),
                }
    for room in room_ids:
        if room not in result:
            info = _get_room_info(room, sessdata, bili_jct)
            if info and info.get("live_status") in (0, 1, 2):
                result[room] = info
    return result


def _get_room_info(room_id: int, sessdata: str, bili_jct: str) -> Optional[Dict]:
    """获取直播间详细信息，包含 area_id / parent_area_id"""
    url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}"
    headers = _make_headers(sessdata, bili_jct)
    resp = _get_json(url, headers)
    if resp and resp.get("code") == 0:
        data = resp["data"]
        if not isinstance(data, dict) or data.get("live_status") not in (0, 1, 2):
            return None
        return {
            "live_status": data.get("live_status", 0),
            "title": data.get("title", ""),
            "area_name": data.get("area_name", ""),
            "live_time": data.get("live_time", ""),
            "area_id": data.get("area_id", 0),
            "parent_area_id": data.get("parent_area_id", 0),
        }
    return None


def _get_single_room_status(room_id: int, sessdata: str, bili_jct: str) -> Optional[Dict]:
    """简化版：只返回 live_status"""
    return _get_room_info(room_id, sessdata, bili_jct)


def enter_room(room_id: int, sessdata: str, bili_jct: str) -> bool:
    url = "https://api.live.bilibili.com/xlive/web-room/v1/index/roomEntryAction"
    headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    data = {"room_id": str(room_id), "platform": "pc", "csrf": bili_jct, "csrf_token": bili_jct}
    resp = _post_form(url, data, headers)
    return resp is not None and resp.get("code") == 0


_X25KN_E_URL = "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/E"
_X25KN_X_URL = "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/X"
_X25KN_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_X25KN_HMAC_FUNCS = ["md5", "sha1", "sha256", "sha224", "sha512", "sha384"]


def _fetch_live_buvid(sessdata, bili_jct):
    result = _get_json(
        "https://api.bilibili.com/x/frontend/finger/spi", _make_headers(sessdata, bili_jct)
    )
    return (result.get("data") or {}).get("b_3") if result and result.get("code") == 0 else None


def _ensure_live_buvid(
    sessdata: str, bili_jct: str, cookies_path: Optional[Path] = None
) -> Optional[str]:
    """Workers read credentials without overwriting another writer's changes."""
    cookies_path = cookies_path or _runtime_path("_COOKIE_PATHS")[0]
    try:
        saved = read_json(cookies_path, {})
        if saved.get("SESSDATA") == sessdata and saved.get("LIVE_BUVID"):
            return saved["LIVE_BUVID"]
        context = saved.get("qr_login_context") or {}
        cookies = context.get("cookies") or {}
        if cookies.get("SESSDATA") == sessdata and cookies.get("bili_jct") == bili_jct:
            return (
                cookies.get("LIVE_BUVID")
                or cookies.get("buvid3")
                or _fetch_live_buvid(sessdata, bili_jct)
            )
    except (OSError, ValueError) as exc:
        _log({"type": "credential_read_error", "error": type(exc).__name__})
    return _fetch_live_buvid(sessdata, bili_jct)


def _x25kn_post(url, form, sessdata, bili_jct, referer):
    headers = _make_headers(sessdata, bili_jct, referer)
    return _post_form(url, {**form, "ua": headers["User-Agent"]}, headers, timeout=15)


def send_web_heartbeat(room_id: int, sessdata: str, bili_jct: str) -> bool:
    """旧版心跳（fallback），不涨亲密度但维持在线"""
    url = "https://api.live.bilibili.com/User/userOnlineHeart"
    headers = _make_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room_id}")
    data = {"csrf": bili_jct, "csrf_token": bili_jct}
    resp = _post_form(url, data, headers)
    return resp is not None and resp.get("code") == 0


def wear_medal(medal_id: int, sessdata: str, bili_jct: str) -> bool:
    url = "https://api.live.bilibili.com/xlive/web-room/v1/fansMedal/wear"
    headers = _make_headers(sessdata, bili_jct)
    data = {"medal_id": str(medal_id), "csrf": bili_jct, "csrf_token": bili_jct}
    resp = _post_form(url, data, headers)
    return resp is not None and resp.get("code") == 0


def get_my_medals(sessdata, bili_jct):
    from .api.medals import entries

    medals = {}
    for item in entries(sessdata, bili_jct, sys.modules[__name__]):
        info = item.get("medal", item)
        target = info.get("target_id", 0)
        if target:
            medals[target] = {
                "medal_id": info.get("medal_id"),
                "medal_name": info.get("medal_name", ""),
                "level": info.get("level", 0),
                "today_intimacy": info.get("today_feed", info.get("today_intimacy", 0)),
                "day_limit": info.get("day_limit", 0),
                "is_lighted": info.get("is_lighted", 0),
            }
    return medals


def get_all_user_medals(sessdata, bili_jct):
    from .api.medals import entries

    results = []
    for item in entries(sessdata, bili_jct, sys.modules[__name__]):
        medal, room, anchor = (
            item.get("medal", {}),
            item.get("room_info", {}),
            item.get("anchor_info", {}),
        )
        uid = medal.get("target_id") or item.get("target_id", 0)
        room_id = room.get("room_id", 0)
        name = anchor.get("nick_name") or item.get("uname", "")
        if uid and room_id and name:
            results.append(
                {
                    "uid": uid,
                    "room": room_id,
                    "name": name,
                    "medal_name": medal.get("medal_name", ""),
                    "level": medal.get("level", 0),
                    "is_lighted": medal.get("is_lighted", 0),
                }
            )
    return results


def resolve_anchor_info(query: str, sessdata: str = "", bili_jct: str = "") -> Optional[Dict]:
    """根据输入的房间号、短号、UID 或直播间链接自动解析主播信息"""
    m = re.search("(\\d+)", str(query).strip())
    if not m:
        return None
    num = int(m.group(1))
    headers = (
        _make_headers(sessdata, bili_jct)
        if sessdata and bili_jct
        else {"User-Agent": "Mozilla/5.0"}
    )
    try:
        url = f"https://api.live.bilibili.com/room/v1/Room/get_info?room_id={num}"
        resp = _get_json(url, headers)
        if resp and resp.get("code") == 0 and resp.get("data", {}).get("uid"):
            uid = resp["data"]["uid"]
            real_room = resp["data"]["room_id"]
            url2 = f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={uid}"
            resp2 = _get_json(url2, headers)
            uname, medal_name = ("", "")
            if resp2 and resp2.get("code") == 0 and isinstance(resp2.get("data"), dict):
                d2 = resp2["data"]
                uname = d2.get("info", {}).get("uname", "")
                medal_name = d2.get("medal_name", "")
            return {
                "uid": uid,
                "room": real_room,
                "name": uname or f"主播_{uid}",
                "medal_name": medal_name,
            }
    except (KeyError, TypeError, ValueError) as exc:
        _log({"type": "response_data_error", "error": type(exc).__name__})
    try:
        url = f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={num}"
        resp = _get_json(url, headers)
        if resp and resp.get("code") == 0 and isinstance(resp.get("data"), dict):
            d = resp["data"]
            room_id = d.get("room_id", 0)
            uname = d.get("info", {}).get("uname", "")
            medal_name = d.get("medal_name", "")
            if room_id:
                return {
                    "uid": num,
                    "room": room_id,
                    "name": uname or f"主播_{num}",
                    "medal_name": medal_name,
                }
    except (KeyError, TypeError, ValueError) as exc:
        _log({"type": "response_data_error", "error": type(exc).__name__})
    return None


from .policies import *
from .policies import _DANMAKU_MSGS
from .binding import bind
from .services.danmaku import send_danmaku_batch as _impl_send_danmaku_batch

send_danmaku_batch = bind(_impl_send_danmaku_batch, sys.modules[__name__])
from .services.danmaku import light_up_medal as _impl_light_up_medal

light_up_medal = bind(_impl_light_up_medal, sys.modules[__name__])
from .services.danmaku import _danmaku_task_progress as _impl__danmaku_task_progress

_danmaku_task_progress = bind(_impl__danmaku_task_progress, sys.modules[__name__])
from .services.danmaku import send_medal_danmaku_tasks as _impl_send_medal_danmaku_tasks

send_medal_danmaku_tasks = bind(_impl_send_medal_danmaku_tasks, sys.modules[__name__])
from .services.likes import get_live_like_progress as _impl_get_live_like_progress

get_live_like_progress = bind(_impl_get_live_like_progress, sys.modules[__name__])
from .services.likes import report_live_likes as _impl_report_live_likes

report_live_likes = bind(_impl_report_live_likes, sys.modules[__name__])
from .services.likes import like_live_room as _impl_like_live_room

like_live_room = bind(_impl_like_live_room, sys.modules[__name__])
from .services.daily_tasks import redo_member_tasks as _impl_redo_member_tasks

redo_member_tasks = bind(_impl_redo_member_tasks, sys.modules[__name__])
from .services.daily_tasks import DailyTaskRunner as _DailyTaskRunner


class DailyTaskRunner(_DailyTaskRunner):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, _gateway=sys.modules[__name__], **kwargs)


from .services.watch import intimacy_change as _impl_intimacy_change

intimacy_change = bind(_impl_intimacy_change, sys.modules[__name__])
from .services.watch import watch_room as _impl_watch_room

watch_room = bind(_impl_watch_room, sys.modules[__name__])
from .services.protocol import _random_string as _impl__random_string

_random_string = bind(_impl__random_string, sys.modules[__name__])
from .services.protocol import _now_ms as _impl__now_ms

_now_ms = bind(_impl__now_ms, sys.modules[__name__])
from .services.protocol import _wait_for_heartbeat_window as _impl__wait_for_heartbeat_window

_wait_for_heartbeat_window = bind(_impl__wait_for_heartbeat_window, sys.modules[__name__])
from .services.protocol import _x25kn_sign as _impl__x25kn_sign

_x25kn_sign = bind(_impl__x25kn_sign, sys.modules[__name__])
from .services.protocol import x25kn_enter_room as _impl_x25kn_enter_room

x25kn_enter_room = bind(_impl_x25kn_enter_room, sys.modules[__name__])
from .services.protocol import x25kn_heartbeat as _impl_x25kn_heartbeat

x25kn_heartbeat = bind(_impl_x25kn_heartbeat, sys.modules[__name__])
from .cli.heartbeat import format_output as _impl_format_output

format_output = bind(_impl_format_output, sys.modules[__name__])
from .cli.heartbeat import main as _impl_main

main = bind(_impl_main, sys.modules[__name__])
