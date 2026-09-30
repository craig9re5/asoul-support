"""Validate Bilibili credentials without printing secret values."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple
from .credentials import cookie_path
from .runtime import read_json
from .session_headers import session_headers
from .http import request_json

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _load_local_cookies() -> Tuple[Optional[str], Optional[str]]:
    path = cookie_path()
    if not path.exists():
        return (None, None)
    try:
        data = read_json(path, {})
    except (OSError, json.JSONDecodeError):
        return (None, None)
    return (data.get("SESSDATA"), data.get("bili_jct"))


def check_login(sessdata: str, bili_jct: str) -> Tuple[bool, str]:
    try:
        body = request_json(
            "https://api.bilibili.com/x/web-interface/nav",
            session_headers(sessdata, bili_jct),
            timeout=15,
            auth_probe=True,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return (False, f"认证接口请求失败: {type(exc).__name__}")
    if body.get("error_kind") == "network":
        return (False, "认证接口请求失败: network")
    data = body.get("data") or {}
    if body.get("code") == 0 and data.get("isLogin") is True:
        return (True, data.get("uname") or "已登录账号")
    return (False, f"{body.get('code', '?')} {body.get('message', '账号未登录')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 B 站 Cookie 登录态")
    parser.add_argument("--sessdata")
    parser.add_argument("--bili-jct")
    args = parser.parse_args()
    local_sessdata, local_bili_jct = _load_local_cookies()
    sessdata = args.sessdata or os.environ.get("SESSDATA") or local_sessdata
    bili_jct = args.bili_jct or os.environ.get("BILI_JCT") or local_bili_jct
    if not sessdata or not bili_jct:
        print("❌ 缺少 SESSDATA 或 BILI_JCT。", file=sys.stderr)
        return 1
    valid, message = check_login(sessdata, bili_jct)
    if not valid:
        print(
            f"❌ B 站登录态无效（{message}）。请在本机运行 setup_local_cookie.py 更新 Cookie。",
            file=sys.stderr,
        )
        return 1
    print(f"✅ B 站登录态有效：{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
