from .content_filters import filter_month, filter_days, parse_month as parse_content_month
from .credentials import load_saved
from .http import get_json, post_form, post_empty, request_json, require_data

"\nA-SOUL 视频三连助手 — 批量点赞/投币/收藏成员新发布的视频。\n需要 WBI 签名来访问 B站 Space API。\n零外部依赖，纯标准库。\n"
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from .credentials import cookie_path
from .members import MEMBERS, load_members
from .session_headers import session_headers

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_COOKIE_PATHS = [cookie_path()]
MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]
CST = timezone(timedelta(hours=8))


def load_cookies():
    return load_saved(_COOKIE_PATHS)


def _make_headers(sessdata: str, bili_jct: str, referer: str = "https://www.bilibili.com") -> dict:
    return session_headers(sessdata, bili_jct, referer)


def _get(url, headers, timeout=10):
    return get_json(url, headers, timeout)


def _post(url, data, headers, timeout=10):
    return post_form(url, data, headers, timeout)


def _get_wbi_keys(sessdata: str, bili_jct: str) -> Tuple[str, str]:
    """从 nav API 获取 WBI img_key 和 sub_key"""
    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = _make_headers(sessdata, bili_jct)
    resp = _get(url, headers)
    if not resp or resp.get("code") != 0:
        raise RuntimeError(f"获取 WBI keys 失败: {resp}")
    wbi_img = resp["data"]["wbi_img"]
    img_url = wbi_img["img_url"]
    sub_url = wbi_img["sub_url"]
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    return (img_key, sub_key)


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    orig = img_key + sub_key
    return "".join((orig[i] for i in MIXIN_KEY_ENC_TAB))[:32]


def _sign_wbi(params: dict, mixin_key: str) -> dict:
    params["wts"] = int(time.time())
    params.pop("w_rid", None)
    filtered = {k: "".join((c for c in str(v) if c not in "!'()*")) for k, v in params.items()}
    query = urllib.parse.urlencode(sorted(filtered.items()))
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


def get_mixin_key(sessdata, bili_jct):
    img_key, sub_key = _get_wbi_keys(sessdata, bili_jct)
    return _get_mixin_key(img_key, sub_key)


def fetch_user_videos(
    uid: int, sessdata: str, bili_jct: str, page_size: int = 30, page: int = 1
) -> List[Dict]:
    """获取 UP 主的视频列表（按发布时间倒序）"""
    mixin_key = get_mixin_key(sessdata, bili_jct)
    params = {
        "mid": str(uid),
        "ps": str(page_size),
        "pn": str(page),
        "order": "pubdate",
        "tid": "0",
    }
    signed = _sign_wbi(params, mixin_key)
    query = urllib.parse.urlencode(signed)
    url = f"https://api.bilibili.com/x/space/wbi/arc/search?{query}"
    headers = _make_headers(sessdata, bili_jct, f"https://space.bilibili.com/{uid}/video")
    resp = _get(url, headers)
    require_data(resp, "获取视频")
    vlist = resp.get("data", {}).get("list", {}).get("vlist", [])
    videos = []
    for v in vlist:
        videos.append(
            {
                "aid": v.get("aid"),
                "bvid": v.get("bvid", ""),
                "title": v.get("title", ""),
                "created": v.get("created", 0),
                "length": v.get("length", ""),
                "play": v.get("play", 0),
                "comment": v.get("comment", 0),
            }
        )
    return videos


def filter_by_month(items, year, month):
    return filter_month(items, year, month, "created")


def filter_recent_days(items, days):
    return filter_days(items, days, "created")


def like_video(aid: int, sessdata: str, bili_jct: str) -> Dict:
    url = "https://api.bilibili.com/x/web-interface/archive/like"
    data = {"aid": str(aid), "like": "1", "csrf": bili_jct}
    headers = _make_headers(sessdata, bili_jct)
    resp = _post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True, "action": "like"}
    already = resp and resp.get("code") == 65006
    return {
        "success": already,
        "action": "like",
        "already_done": already,
        "error": None if already else resp.get("message", "未知错误") if resp else "请求失败",
    }


def coin_video(aid: int, sessdata: str, bili_jct: str, multiply: int = 1) -> Dict:
    url = "https://api.bilibili.com/x/web-interface/coin/add"
    data = {"aid": str(aid), "multiply": str(multiply), "select_like": "0", "csrf": bili_jct}
    headers = _make_headers(sessdata, bili_jct)
    resp = _post(url, data, headers)
    if resp and resp.get("code") == 0:
        return {"success": True, "action": "coin", "multiply": multiply}
    already = resp and resp.get("code") == 34005
    return {
        "success": already,
        "action": "coin",
        "already_done": already,
        "error": None if already else resp.get("message", "未知错误") if resp else "请求失败",
    }


def fav_video(aid: int, sessdata: str, bili_jct: str, fav_id: Optional[int] = None) -> Dict:
    if not fav_id:
        fav_id = _get_default_fav(sessdata, bili_jct)
    if not fav_id:
        return {"success": False, "action": "fav", "error": "无法获取默认收藏夹"}
    url = "https://api.bilibili.com/x/v3/fav/resource/deal"
    data = {"rid": str(aid), "type": "2", "add_media_ids": str(fav_id), "csrf": bili_jct}
    headers = _make_headers(sessdata, bili_jct)
    resp = _post(url, data, headers)
    if resp and resp.get("code") == 0:
        prompt = resp.get("data", {}).get("prompt", False)
        return {"success": True, "action": "fav", "already_done": prompt}
    already = resp and resp.get("code") == 11201
    return {
        "success": already,
        "action": "fav",
        "already_done": already,
        "error": None if already else resp.get("message", "未知错误") if resp else "请求失败",
    }


def _get_default_fav(sessdata: str, bili_jct: str) -> Optional[int]:
    """获取用户默认收藏夹 ID"""
    nav_url = "https://api.bilibili.com/x/web-interface/nav"
    headers = _make_headers(sessdata, bili_jct)
    resp = _get(nav_url, headers)
    if not resp or resp.get("code") != 0:
        return None
    my_uid = resp.get("data", {}).get("mid")
    if not my_uid:
        return None
    fav_url = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={my_uid}&type=2"
    resp = _get(fav_url, headers)
    if not resp or resp.get("code") != 0:
        return None
    folders = resp.get("data", {}).get("list", [])
    if not folders:
        return None
    return folders[0].get("id")


def parse_month(value):
    return parse_content_month(value)


from .binding import bind
from .services.videos import process_member_videos as _impl_process_member_videos

process_member_videos = bind(_impl_process_member_videos, sys.modules[__name__])
from .services.videos import format_output as _impl_format_output

format_output = bind(_impl_format_output, sys.modules[__name__])
from .cli.videos import main as _impl_main

main = bind(_impl_main, sys.modules[__name__])
