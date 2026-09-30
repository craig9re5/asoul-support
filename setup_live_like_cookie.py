#!/usr/bin/env python3
"""Store the browser session used by the live-like task, without echoing it."""

import getpass
import json
import sys
from pathlib import Path

from asoul_support.credentials import cookie_path, parse_cookie_header
from asoul_support.runtime import update_json, read_json
from asoul_support.login_fields import login_context


def main() -> int:
    path = cookie_path()
    if not path.exists():
        print("请先运行 setup_local_cookie.py 保存并验证登录 Cookie。", file=sys.stderr)
        return 1
    try:
        saved = read_json(path, {})
        if not isinstance(saved, dict):
            raise ValueError("Cookie 文件格式错误")
    except (OSError, ValueError) as exc:
        print(f"无法读取本地 Cookie 文件：{exc}", file=sys.stderr)
        return 1

    print("请从已登录的直播间点赞请求中复制 Request Headers 的 Cookie 值。")
    print("输入仅保存在本机现有 Cookie 文件中，不会回显；不要把它发到聊天或提交到仓库。")
    raw = getpass.getpass("完整 Cookie 请求头: ").strip()
    try:
        parsed = parse_cookie_header(raw)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if parsed.get("SESSDATA") != saved.get("SESSDATA") or parsed.get("bili_jct") != saved.get(
        "bili_jct"
    ):
        print("浏览器 Cookie 与本机已保存的账号不一致；请先更新登录 Cookie。", file=sys.stderr)
        return 1
    if not parsed.get("DedeUserID", "").isdigit():
        print("Cookie 缺少有效的 DedeUserID。", file=sys.stderr)
        return 1

    ua = input("同一请求的 User-Agent: ").strip()
    if not ua or "\r" in ua or "\n" in ua:
        print("需要同一浏览器请求的有效 User-Agent。", file=sys.stderr)
        return 1
    try:
        context = login_context(parsed, ua)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    saved["live_like_cookie"] = raw
    saved["live_like_user_agent"] = ua

    def change(current):
        if (
            current.get("SESSDATA") != parsed["SESSDATA"]
            or current.get("bili_jct") != parsed["bili_jct"]
        ):
            raise ValueError("账号已发生变化，请重新获取浏览器上下文")
        return {**current, "qr_login_context": context}

    try:
        update_json(path, change, {})
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"保存失败：{exc}", file=sys.stderr)
        return 1
    print("直播点赞使用的浏览器上下文已保存在本机。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
