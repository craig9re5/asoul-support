import argparse
import json
import sys
from datetime import timezone, timedelta
from ..members import MEMBERS


def main(argv=None, *, _gateway):
    parser = argparse.ArgumentParser(
        description="A-SOUL 动态点赞",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n示例:\n  # 给本月动态全部点赞\n  python3 dynamics.py --month 3\n\n  # 给最近7天动态点赞\n  python3 dynamics.py --days 7\n\n  # 只给嘉然的动态点赞\n  python3 dynamics.py --month 3 --members 嘉然\n",
    )
    parser.add_argument("--month", help="指定月份（如 3、03、2026-03）")
    parser.add_argument("--days", type=int, help="最近 N 天的动态")
    parser.add_argument("--members", help="指定成员（逗号分隔）")
    parser.add_argument("--delay", type=float, default=8, help="动态之间的间隔秒数（默认 8）")
    parser.add_argument("--sessdata", help="SESSDATA cookie")
    parser.add_argument("--bili-jct", help="bili_jct cookie")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)
    MEMBERS = _gateway.load_members()
    if not args.month and (not args.days):
        print("❌ 请指定 --month 或 --days")
        return 1
    sessdata = args.sessdata
    bili_jct = args.bili_jct
    if not sessdata or not bili_jct:
        saved = _gateway.load_cookies()
        if saved:
            sessdata = saved["SESSDATA"]
            bili_jct = saved["bili_jct"]
        else:
            print("❌ 没有找到 Cookie。")
            return 1
    targets = MEMBERS
    if args.members:
        names = [n.strip() for n in args.members.split(",")]
        targets = [m for m in MEMBERS if m["name"] in names]
        if not targets:
            print(f"❌ 未找到成员: {args.members}")
            return 1
    all_results = []
    for member in targets:
        print(f"  📡 正在获取 {member['name']} 的动态...", file=sys.stderr)
        from ..services.content import cutoff_for, MAX_CONTENT_PAGES

        dynamics = _gateway.fetch_user_dynamics(
            member["uid"],
            sessdata,
            bili_jct,
            max_pages=MAX_CONTENT_PAGES,
            require_complete=True,
            since=cutoff_for(args, _gateway),
        )
        if args.month:
            year, month = _gateway.parse_month(args.month)
            dynamics = _gateway.filter_by_month(dynamics, year, month)
        elif args.days:
            dynamics = _gateway.filter_by_days(dynamics, args.days)
        if not dynamics:
            print(f"  ℹ️  {member['name']} 在指定时间段内没有新动态", file=sys.stderr)
            continue
        print(f"  💬 找到 {len(dynamics)} 条动态，开始点赞...", file=sys.stderr)
        results = _gateway.process_member_dynamics(
            member, dynamics, sessdata, bili_jct, delay=args.delay
        )
        all_results.extend(results)
    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
    elif all_results:
        print(_gateway.format_output(all_results))
    else:
        print("ℹ️  指定时间段内没有找到任何动态")
    return 1 if any(not result.get("success") for result in all_results) else 0
