import argparse
import json
import sys
from ..members import MEMBERS


def main(argv=None, *, _gateway):
    parser = argparse.ArgumentParser(description="A-SOUL 粉丝牌点亮 + 直播间弹幕应援")
    parser.add_argument(
        "--msg",
        action="append",
        dest="msgs",
        help="自定义弹幕内容（可多次指定，如 --msg 签到 --msg 加油）",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="本轮最多尝试的弹幕条数；仍按任务缺额发送，并受每日预算约束",
    )
    parser.add_argument("--members", help="指定成员（逗号分隔，如：嘉然,贝拉）默认全部")
    parser.add_argument("--sessdata", help="SESSDATA cookie")
    parser.add_argument("--bili-jct", help="bili_jct cookie")
    parser.add_argument("--save-cookie", action="store_true", help="保存 cookie")
    parser.add_argument("--no-medal", action="store_true", help="不自动佩戴粉丝牌")
    parser.add_argument(
        "--live-only", action="store_true", help="只对正在直播的成员发弹幕（需要开播才能点亮牌子）"
    )
    parser.add_argument("--delay", type=float, default=8, help="成员之间的间隔秒数（默认 8）")
    parser.add_argument(
        "--danmaku-delay", type=float, default=3, help="同一直播间内弹幕之间的间隔秒数（默认 3）"
    )
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--list", action="store_true", help="列出所有成员")
    args = parser.parse_args(argv)
    MEMBERS = _gateway.load_members()
    if args.list:
        print("🌟 当前监控成员：")
        for m in MEMBERS:
            print(
                f"  {m['name']}  UID:{m['uid']}  直播间:{m['room']}  https://live.bilibili.com/{m['room']}"
            )
        return
    sessdata = args.sessdata
    bili_jct = args.bili_jct
    if args.save_cookie:
        if not sessdata or not bili_jct:
            print("❌ --save-cookie 需要同时提供 --sessdata 和 --bili-jct")
            return 1
        _gateway.save_cookies(sessdata, bili_jct)
        return
    if not sessdata or not bili_jct:
        saved = _gateway.load_cookies()
        if saved:
            sessdata = saved["SESSDATA"]
            bili_jct = saved["bili_jct"]
        else:
            print("❌ 没有找到 Cookie。请先设置：")
            print(
                '  python3 checkin.py --save-cookie --sessdata "你的SESSDATA" --bili-jct "你的bili_jct"'
            )
            print("")
            print("或在 bilibili-live-checkin skill 中已保存的 Cookie 会自动复用。")
            return 1
    targets = MEMBERS
    if args.members:
        names = [n.strip() for n in args.members.split(",")]
        targets = [m for m in MEMBERS if m["name"] in names]
        if not targets:
            print(f"❌ 未找到指定成员：{args.members}")
            print(f"   可用成员：{', '.join((m['name'] for m in MEMBERS))}")
            return 1
    if args.live_only:
        print("  📡 正在检测直播状态...", file=sys.stderr)
        live_status = _gateway.check_live_status(targets, sessdata, bili_jct)
        live_targets = [m for m in targets if live_status.get(m["room"], False)]
        offline = [m["name"] for m in targets if not live_status.get(m["room"], False)]
        if offline:
            print(f"  💤 未开播（跳过）：{', '.join(offline)}", file=sys.stderr)
        if not live_targets:
            print("\nℹ️  当前没有成员在播，本次跳过")
            return
        targets = live_targets
        print(f"  🔴 在播：{', '.join((m['name'] for m in targets))}", file=sys.stderr)
    msgs = args.msgs if args.msgs else _gateway.DEFAULT_MESSAGES
    results = _gateway.batch_checkin(
        targets,
        msgs,
        sessdata,
        bili_jct,
        auto_medal=not args.no_medal,
        count=args.count,
        delay=args.delay,
        danmaku_delay=args.danmaku_delay,
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(_gateway.format_output(results))
    return 1 if any(not result.get("success") for result in results) else 0
