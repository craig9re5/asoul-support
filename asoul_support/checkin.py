from .credentials import load_saved
from .http import get_json, post_form, post_empty, request_json, require_data

"\nA-SOUL 直播间粉丝牌点亮 + 日常应援。\n自动佩戴对应粉丝牌 → 发送 10 条弹幕点亮牌子（保持 3 天可见）。\n零外部依赖，纯标准库。\n"
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, List
from .credentials import cookie_path
from .danmaku_pacing import send_paced
from .members import MEMBERS, load_members
from .runtime import save_login

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_SEND_URL = "https://api.live.bilibili.com/msg/send"
LIGHT_UP_COUNT = 10
INTIMACY_COUNT = 5
DEFAULT_MESSAGES = [
    "？",
    "dnys",
    "咋这样",
    "OK",
    "3",
    "不赖",
    "做人真的可以",
    "好吧",
    "呃呃",
    "考",
    "+3",
    "+6",
    "+9",
]
_COOKIE_PATHS = [cookie_path()]


def load_cookies():
    return load_saved(_COOKIE_PATHS)


def save_cookies(sessdata: str, bili_jct: str):
    path = _COOKIE_PATHS[0]
    save_login(sessdata, bili_jct, path)
    print(f"💾 Cookie 已保存到 {path}")


def check_live_status(members, sessdata, bili_jct):
    from .heartbeat import check_live_status as query

    statuses = query([m["room"] for m in members], sessdata, bili_jct)
    missing = [m["name"] for m in members if m["room"] not in statuses]
    if missing:
        raise RuntimeError("直播状态查询失败：" + "、".join(missing))
    return {room: value["live_status"] == 1 for room, value in statuses.items()}


def _get_json(url, headers, timeout=10):
    return get_json(url, headers, timeout)


def _post_form(url, data, headers, timeout=10):
    return post_form(url, data, headers, timeout)


def get_my_medals(sessdata, bili_jct):
    from .heartbeat import get_my_medals as get_medals

    return get_medals(sessdata, bili_jct)


def wear_medal(medal_id, sessdata, bili_jct):
    from .heartbeat import wear_medal as wear

    return wear(medal_id, sessdata, bili_jct)


def send_danmaku(room_id, msg, sessdata, bili_jct):
    from .heartbeat import _send_danmaku

    ok = _send_danmaku(room_id, msg, sessdata, bili_jct)
    return {"code": 0 if ok else -1, "message": "OK" if ok else "弹幕发送失败"}


from .binding import bind
from .services.checkin import _pick_messages as _impl__pick_messages

_pick_messages = bind(_impl__pick_messages, sys.modules[__name__])
from .services.checkin import batch_checkin as _impl_batch_checkin

batch_checkin = bind(_impl_batch_checkin, sys.modules[__name__])
from .services.checkin import format_output as _impl_format_output

format_output = bind(_impl_format_output, sys.modules[__name__])
from .cli.checkin import main as _impl_main

main = bind(_impl_main, sys.modules[__name__])
