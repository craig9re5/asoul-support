#!/usr/bin/env python3
"""Prompt for Bilibili credentials locally and store them for asoul-support."""

import getpass
import argparse
import sys

from asoul_support.application import AppContext
from asoul_support.credentials import cookie_path
from asoul_support.runtime import save_login


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print("B 站 Cookie 仅在本机输入；输入时不会回显。")
    sessdata = getpass.getpass("SESSDATA: ").strip()
    bili_jct = getpass.getpass("bili_jct: ").strip()
    if not sessdata or not bili_jct:
        print("缺少 SESSDATA 或 bili_jct，未保存。", file=sys.stderr)
        return 1

    valid, message = AppContext().validate_credentials(sessdata, bili_jct)
    if not valid:
        print(f"登录验证失败：{message}。未保存。", file=sys.stderr)
        return 1

    path = cookie_path()
    save_login(sessdata, bili_jct, path)

    print(f"登录验证通过，Cookie 已保存至 {path}")
    print("登录会话由当前系统用户的凭据保护机制保存。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
