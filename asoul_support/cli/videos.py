import argparse
import json
import sys
from datetime import timezone, timedelta
from ..members import MEMBERS


def main(argv=None, *, _gateway):
    parser = argparse.ArgumentParser(
        description="A-SOUL 视频点赞/投币/收藏",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n示例:\n  # 给 A-SOUL 3月新视频全部点赞（默认）\n  python3 videos.py --month 3\n\n  # 给最近7天视频点赞+投币+收藏\n  python3 videos.py --days 7 --coin --fav\n\n  # 只给嘉然和贝拉的视频点赞\n  python3 videos.py --month 3 --members 嘉然,贝拉\n\n  # 不点赞，只投币\n  python3 videos.py --month 3 --no-like --coin\n",
    )
    parser.add_argument("--month", help="指定月份（如 3、03、2026-03）")
    parser.add_argument("--days", type=int, help="最近 N 天的视频")
    parser.add_argument(
        "--like", dest="do_like", action="store_true", default=True, help="点赞（默认开启）"
    )
    parser.add_argument("--no-like", dest="do_like", action="store_false", help="不点赞")
    parser.add_argument("--coin", action="store_true", default=False, help="投币（默认关闭）")
    parser.add_argument("--fav", action="store_true", default=False, help="收藏（默认关闭）")
    parser.add_argument("--members", help="指定成员（逗号分隔）")
    parser.add_argument("--delay", type=float, default=8, help="视频之间的间隔秒数（默认 8）")
    parser.add_argument("--sessdata", help="SESSDATA cookie")
    parser.add_argument("--bili-jct", help="bili_jct cookie")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)
    MEMBERS = _gateway.load_members()
    if not args.month and (not args.days):
        print("❌ 请指定 --month 或 --days 参数")
        print("   例: --month 3  或  --days 7")
        return 1
    sessdata = args.sessdata
    bili_jct = args.bili_jct
    if not sessdata or not bili_jct:
        saved = _gateway.load_cookies()
        if saved:
            sessdata = saved["SESSDATA"]
            bili_jct = saved["bili_jct"]
        else:
            print("❌ 没有找到 Cookie。请先在 bilibili-live-checkin 中保存 Cookie。")
            return 1
    targets = MEMBERS
    if args.members:
        names = [n.strip() for n in args.members.split(",")]
        targets = [m for m in MEMBERS if m["name"] in names]
        if not targets:
            print(f"❌ 未找到成员: {args.members}")
            return 1
    fav_id = None
    if args.fav:
        fav_id = _gateway._get_default_fav(sessdata, bili_jct)
        if not fav_id:
            print("❌ 无法获取默认收藏夹，本次未执行视频操作", file=sys.stderr)
            return 1
    all_results = []
    for member in targets:
        print(f"  📡 正在获取 {member['name']} 的视频...", file=sys.stderr)
        from ..services.content import video_window

        videos = video_window(member["uid"], args, sessdata, bili_jct, _gateway)
        if args.month:
            year, month = _gateway.parse_month(args.month)
            videos = _gateway.filter_by_month(videos, year, month)
        elif args.days:
            videos = _gateway.filter_recent_days(videos, args.days)
        if not videos:
            print(f"  ℹ️  {member['name']} 在指定时间段内没有新视频", file=sys.stderr)
            continue
        print(f"  📹 找到 {len(videos)} 个视频，开始处理...", file=sys.stderr)
        results = _gateway.process_member_videos(
            member,
            videos,
            sessdata,
            bili_jct,
            do_like=args.do_like,
            do_coin=args.coin,
            do_fav=args.fav,
            fav_id=fav_id,
            delay=args.delay,
        )
        all_results.extend(results)
    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
    elif all_results:
        print(_gateway.format_output(all_results, args.do_like, args.coin, args.fav))
    else:
        print("ℹ️  指定时间段内没有找到任何视频")
    return (
        1
        if any(
            not action.get("success")
            for result in all_results
            for action in result.get("actions", [])
        )
        else 0
    )
