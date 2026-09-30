from .content_filters import filter_month, filter_days, parse_month as parse_content_month
from .credentials import load_saved
from .http import get_json, post_form, post_empty, request_json, require_data
from .session_headers import session_headers

"\nA-SOUL 动态点赞 — 批量给成员的动态（图文/视频/转发）点赞。\n零外部依赖，纯标准库。\n"
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from .credentials import cookie_path
from .members import MEMBERS, load_members
from .context import CURRENT
from .public_session import PublicSession

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _ensure_cookies():
    """访问 bilibili.com 获取 buvid3 等反爬 cookie"""
    context = CURRENT.get()
    session = context.public_sessions.current() if context is not None else PublicSession()
    return session.cookies(_UA)


_COOKIE_PATHS = [cookie_path()]
CST = timezone(timedelta(hours=8))
DYN_TYPE_NAMES = {
    "DYNAMIC_TYPE_AV": "视频",
    "DYNAMIC_TYPE_DRAW": "图文",
    "DYNAMIC_TYPE_WORD": "文字",
    "DYNAMIC_TYPE_FORWARD": "转发",
    "DYNAMIC_TYPE_LIVE_RCMD": "直播",
    "DYNAMIC_TYPE_ARTICLE": "专栏",
}


def load_cookies():
    return load_saved(_COOKIE_PATHS)


def _make_headers(sessdata: str, bili_jct: str, referer: str = "https://www.bilibili.com") -> dict:
    return session_headers(sessdata, bili_jct, referer)


def _get(url, headers, timeout=10):
    return get_json(url, headers, timeout)


def _post(url, data, headers, timeout=10):
    return post_form(url, data, headers, timeout)


def fetch_user_dynamics(
    uid: int,
    sessdata: str,
    bili_jct: str,
    max_pages: int = 3,
    *,
    require_complete=False,
    since=None,
) -> List[Dict]:
    """获取 UP 主的动态列表"""
    headers = _make_headers(sessdata, bili_jct, f"https://space.bilibili.com/{uid}/dynamic")
    dynamics = []
    offset = ""
    seen_offsets = set()
    for _ in range(max_pages):
        url = f"https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space?host_mid={uid}&features=itemOpusStyle"
        if offset:
            url += f"&offset={offset}"
        resp = _get(url, headers)
        require_data(resp, "获取动态")
        items = resp.get("data", {}).get("items", [])
        if not items:
            break
        for item in items:
            dyn_id = item.get("id_str", "")
            dyn_type = item.get("type", "")
            pub_ts_raw = item.get("modules", {}).get("module_author", {}).get("pub_ts", 0)
            pub_ts = int(pub_ts_raw) if pub_ts_raw else 0
            desc_text = ""
            major = item.get("modules", {}).get("module_dynamic", {})
            desc = major.get("desc", {})
            if desc:
                desc_text = desc.get("text", "")
            opus = major.get("major", {})
            if opus and opus.get("type") == "MAJOR_TYPE_ARCHIVE":
                archive = opus.get("archive", {})
                desc_text = desc_text or archive.get("title", "")
            elif opus and opus.get("type") == "MAJOR_TYPE_OPUS":
                opus_summary = opus.get("opus", {}).get("summary", {})
                if opus_summary and opus_summary.get("text"):
                    desc_text = desc_text or opus_summary["text"]
            dynamics.append(
                {
                    "dyn_id": dyn_id,
                    "type": dyn_type,
                    "type_name": DYN_TYPE_NAMES.get(dyn_type, dyn_type),
                    "pub_ts": pub_ts,
                    "text": desc_text[:60],
                }
            )
        ordinary = [
            item
            for item in items
            if item.get("modules", {}).get("module_tag", {}).get("text") != "置顶"
        ]
        timestamps = [
            int(item.get("modules", {}).get("module_author", {}).get("pub_ts") or 0)
            for item in ordinary
        ]
        if since is not None and timestamps and all((0 < stamp < since for stamp in timestamps)):
            break
        offset = resp.get("data", {}).get("offset", "")
        has_more = resp.get("data", {}).get("has_more", False)
        if not has_more or not offset:
            break
        if offset in seen_offsets:
            raise RuntimeError("动态分页重复，无法确认完整范围")
        seen_offsets.add(offset)
    else:
        if require_complete:
            raise RuntimeError("动态分页超过上限，未执行本成员点赞操作")
    return dynamics


def filter_by_days(items, days):
    return filter_days(items, days, "pub_ts")


def filter_by_month(items, year, month):
    return filter_month(items, year, month, "pub_ts")


def like_dynamic(dyn_id: str, sessdata: str, bili_jct: str) -> Dict:
    url = "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb"
    data = {"dynamic_id": dyn_id, "up": "1", "csrf": bili_jct, "csrf_token": bili_jct}
    headers = _make_headers(sessdata, bili_jct, "https://t.bilibili.com")
    headers["Origin"] = "https://t.bilibili.com"
    resp = _post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True}
    already = resp and resp.get("code") == 65006
    return {
        "success": already,
        "already_done": already,
        "error": None if already else resp.get("message", "未知错误") if resp else "请求失败",
    }


def parse_month(value):
    return parse_content_month(value)


from .binding import bind
from .services.dynamics import process_member_dynamics as _impl_process_member_dynamics

process_member_dynamics = bind(_impl_process_member_dynamics, sys.modules[__name__])
from .services.dynamics import format_output as _impl_format_output

format_output = bind(_impl_format_output, sys.modules[__name__])
from .cli.dynamics import main as _impl_main

main = bind(_impl_main, sys.modules[__name__])
