import argparse
import json
import os
import sys
import time
import uuid
from typing import Dict, List
from ..policies import *
from .. import safety


def format_output(
    live_results: List[Dict],
    offline_members: List[str],
    medal_info: Dict[int, Dict],
    members: List[Dict],
    *,
    _gateway,
) -> str:
    lines = ["🌟 A-SOUL 直播心跳挂机结果", ""]
    if live_results:
        lines.append("  📺 在播成员：")
        for r in live_results:
            uid = next((m["uid"] for m in members if m["name"] == r["name"]), 0)
            medal = medal_info.get(uid)
            medal_str = f"  🏅{medal['medal_name']}Lv{medal['level']}" if medal else ""
            intimacy_str = ""
            if medal:
                intimacy_str = f"  今日亲密度:{medal['today_intimacy']}"
            mode_str = "X25Kn" if r.get("x25kn") else "旧版"
            if r["success"]:
                delta = r.get("intimacy_delta")
                delta_str = (
                    f"  亲密度:+{delta}"
                    if isinstance(delta, int)
                    else f"  {r.get('intimacy_note', '')}"
                )
                lines.append(
                    f"    ✅ {r['name']}{medal_str}  — 挂机 {r['minutes']}min  💓{r['beats_ok']}/{r['beats_total']}({mode_str}){intimacy_str}{delta_str}"
                )
            else:
                lines.append(f"    ❌ {r['name']}  — {r.get('error', '心跳失败')}")
    if offline_members:
        lines.append("")
        lines.append(f"  💤 未开播：{', '.join(offline_members)}")
    lines.append("")
    if live_results:
        ok_count = sum((1 for r in live_results if r["success"]))
        lines.append(f"📊 在播 {len(live_results)} 人，挂机成功 {ok_count} 人")
    else:
        lines.append("ℹ️  当前没有成员在播，本次跳过")
    return "\n".join(lines)


def main(argv=None, *, _gateway):
    args = build_parser(_gateway).parse_args(argv)
    MEMBERS = _gateway.load_members()
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
    if args.safety_status:
        hold = safety.status(sessdata)
        print(json.dumps(hold, ensure_ascii=False, indent=2))
        return 1 if hold["blocked"] else 0
    if args.resume_safety:
        if not args.confirm_account_reviewed:
            print(
                "请先在平台处理异常或核对任务，再加 --confirm-account-reviewed 确认。",
                file=sys.stderr,
            )
            return 1
        hold = safety.status(sessdata)
        if hold.get("until") and hold["blocked"]:
            print("冷却期间不能提前恢复。", file=sys.stderr)
            return 1
        valid, message = _gateway.check_login(sessdata, bili_jct)
        if not valid:
            print("登录或平台验证未通过，保护暂停保留。", file=sys.stderr)
            return 1
        ok, message = safety.resume(sessdata, confirmed=True)
        print(message)
        return 0 if ok else 1
    targets = MEMBERS
    if args.members:
        names = [n.strip() for n in args.members.split(",")]
        targets = [m for m in MEMBERS if m["name"] in names]
        if not targets:
            print(f"❌ 未找到成员: {args.members}")
            return 1
    statuses, live_members, offline_names, unknown_names = discover(
        targets, sessdata, bili_jct, _gateway
    )
    if args.check_only:
        return print_check(args, statuses, live_members, offline_names, unknown_names)
    if not live_members:
        print("\nℹ️  当前没有成员在播，本次跳过")
        return 1 if unknown_names else 0
    login_valid, login_message = _gateway.check_login(sessdata, bili_jct)
    if not login_valid:
        print(f"\n❌ B 站登录态无效（{login_message}），本次不启动挂机。", file=sys.stderr)
        _gateway._log({"type": "auth_error", "message": login_message})
        return 1
    if args.likes_only:
        return run_likes(live_members, sessdata, bili_jct, _gateway)
    print("  🏅 正在获取粉丝牌信息...", file=sys.stderr)
    medals = _gateway.get_my_medals(sessdata, bili_jct)
    if args.until_offline:
        _gateway._runtime_path("_LOCK_DIR").mkdir(parents=True, exist_ok=True)
    live_results = []
    for i, m in enumerate(live_members):
        result = watch_member(
            m, i, live_members, args, statuses, medals, sessdata, bili_jct, _gateway
        )
        live_results.append(result)
        if i < len(live_members) - 1:
            time.sleep(3)
    if args.json:
        print(
            json.dumps(
                {"results": live_results, "offline": offline_names, "unknown": unknown_names},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("")
        print(_gateway.format_output(live_results, offline_names, medals, targets))
    return 1 if unknown_names or any((not r["success"] for r in live_results)) else 0


def build_parser(_gateway):
    parser = argparse.ArgumentParser(
        description="A-SOUL 直播心跳挂机（检测开播 → XL心跳涨亲密度）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n示例:\n  # 检测所有成员，在播的自动挂机 25 分钟\n  python3 heartbeat.py\n\n  # 只检测嘉然和贝拉\n  python3 heartbeat.py --members 嘉然,贝拉\n\n  # 只检测开播状态，不挂机\n  python3 heartbeat.py --check-only\n\n  # 自定义挂机时长\n  python3 heartbeat.py --duration 30\n",
    )
    parser.add_argument("--members", help="指定成员（逗号分隔）")
    parser.add_argument(
        "--duration",
        type=int,
        default=_gateway.WATCH_MINUTES,
        help=f"挂机时长（分钟，默认 {_gateway.WATCH_MINUTES}）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=_gateway.HEARTBEAT_INTERVAL,
        help=f"心跳间隔（秒，默认 {_gateway.HEARTBEAT_INTERVAL}）",
    )
    parser.add_argument(
        "--until-offline", action="store_true", help="持续挂机直到主播下播（忽略 --duration）"
    )
    parser.add_argument(
        "--no-danmaku", action="store_true", help="长期挂机时不自动发送点亮粉丝牌的弹幕"
    )
    parser.add_argument("--no-revive", action="store_true", help="关闭自动点亮阶段")
    parser.add_argument("--no-intimacy-danmaku", action="store_true", help="关闭每日弹幕亲密度阶段")
    parser.add_argument(
        "--live-likes",
        action="store_true",
        help="尝试完成剩余粉丝团点赞轮次（实验性；复用扫码会话）",
    )
    parser.add_argument(
        "--likes-only",
        action="store_true",
        help="仅尝试一轮直播点赞并检查任务进度，不启动挂机或发送弹幕",
    )
    parser.add_argument("--sessdata", help="SESSDATA cookie")
    parser.add_argument("--bili-jct", help="bili_jct cookie")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--check-only", action="store_true", help="只检测开播状态，不挂机")
    parser.add_argument("--safety-status", action="store_true", help="只读取本机账号保护状态")
    parser.add_argument(
        "--resume-safety", action="store_true", help="处理账号异常后恢复，保留当日预算"
    )
    parser.add_argument(
        "--confirm-account-reviewed", action="store_true", help="确认已在平台处理异常或核对结果"
    )
    return parser


def discover(targets, sessdata, bili_jct, _gateway):
    print("  📡 正在检测直播状态...", file=sys.stderr)
    room_ids = [m["room"] for m in targets]
    statuses = _gateway.check_live_status(room_ids, sessdata, bili_jct)
    live_members = []
    offline_names = []
    unknown_names = []
    for m in targets:
        status = statuses.get(m["room"])
        if not status or status.get("live_status") not in (0, 1, 2):
            unknown_names.append(m["name"])
            print(f"  ⚠️ {m['name']} 直播状态查询失败", file=sys.stderr)
            continue
        if status.get("live_status") == 1:
            live_members.append(m)
            title = status.get("title", "")
            print(f"  🔴 {m['name']} 正在直播：{title}", file=sys.stderr)
        else:
            offline_names.append(m["name"])
            print(f"  ⚫ {m['name']} 未开播", file=sys.stderr)
    _gateway._log(
        {
            "type": "check",
            "live": [
                {"name": m["name"], "title": statuses.get(m["room"], {}).get("title", "")}
                for m in live_members
            ],
            "offline": offline_names,
            "unknown": unknown_names,
        }
    )
    return (statuses, live_members, offline_names, unknown_names)


def print_check(args, statuses, live_members, offline_names, unknown_names):
    if args.json:
        result = {
            "live": [
                {
                    "name": m["name"],
                    "room": m["room"],
                    "title": statuses.get(m["room"], {}).get("title", ""),
                }
                for m in live_members
            ],
            "offline": offline_names,
            "unknown": unknown_names,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if live_members:
            print(f"\n🔴 在播：{', '.join((m['name'] for m in live_members))}")
        if offline_names:
            print(f"⚫ 未开播：{', '.join(offline_names)}")
    return 1 if unknown_names else 0


def run_likes(live_members, sessdata, bili_jct, _gateway):
    failed = False
    for m in live_members:
        task = _gateway.DailyTaskRunner(
            m["room"],
            m["uid"],
            sessdata,
            bili_jct,
            auto_revive=False,
            auto_intimacy=False,
            auto_like=True,
            like_batches=1,
        ).check()
        result = task.get("like") or {
            "success": False,
            "reported": 0,
            "error": task.get("error", "点赞任务失败"),
        }
        _gateway._log(
            {
                "type": "live_like",
                "room_id": m["room"],
                "reported": result["reported"],
                "success": result["success"],
                "error": result.get("error"),
            }
        )
        if result["success"]:
            print(f"{m['name']}：上报 {result['reported']} 次，任务进度 {result['progress']}")
        else:
            failed = True
            print(
                f"{m['name']}：{result['error']}（已上报 {result['reported']} 次）", file=sys.stderr
            )
    if failed:
        return 1
    return


def watch_member(m, i, live_members, args, statuses, medals, sessdata, bili_jct, _gateway):
    lock_file = (
        _gateway._runtime_path("_LOCK_DIR") / f"{m['room']}.lock" if args.until_offline else None
    )
    lease = _gateway.FileLock(_gateway._runtime_path("_LOCK_DIR") / f"{m['room']}.watch.lock")
    if not lease.acquired:
        lease.close()
        print(f"\n  ⏭  {m['name']} 已有挂机在运行，跳过", file=sys.stderr)
        return {
            "name": m["name"],
            "room": m["room"],
            "success": True,
            "skipped": True,
            "beats_ok": 0,
            "beats_total": 0,
            "minutes": 0,
        }
    print(f"\n  📺 [{i + 1}/{len(live_members)}] {m['name']} 直播间 {m['room']}", file=sys.stderr)
    session_id = str(uuid.uuid4())
    start_day = _gateway.task_day()
    started = time.time()
    token = _gateway.EVENT_CONTEXT.set(
        {
            "session_id": session_id,
            "account_key": _gateway.account_key(sessdata),
            "room_id": m["room"],
            "source": "heartbeat",
        }
    )
    live_title = statuses.get(m["room"], {}).get("title", "")
    result = {
        "name": m["name"],
        "room": m["room"],
        "success": False,
        "error": "挂机进程异常退出",
        "beats_ok": 0,
        "beats_total": 0,
        "minutes": 0,
    }
    before_intimacy = medals.get(m["uid"], {}).get("today_intimacy")
    try:
        _gateway._log(
            {"type": "watch_start", "member": m["name"], "room": m["room"], "day": start_day}
        )
        if lock_file:
            lock_file.write_text(str(os.getpid()))
        if m["uid"] in medals:
            medal = medals[m["uid"]]
            if _gateway.wear_medal(medal["medal_id"], sessdata, bili_jct):
                print(f"    🏅 已佩戴 {medal['medal_name']}Lv{medal['level']}", file=sys.stderr)
            time.sleep(1)
        result = _gateway.watch_room(
            m,
            sessdata,
            bili_jct,
            duration_min=args.duration,
            interval=args.interval,
            until_offline=args.until_offline,
            title=live_title,
            send_danmaku=not args.no_danmaku,
            auto_revive=not args.no_revive,
            auto_intimacy=not args.no_intimacy_danmaku,
            send_live_likes=args.live_likes,
            medal_info=medals.get(m["uid"]),
        )
    except Exception as exc:
        result["error"] = f"挂机异常（{type(exc).__name__}）"
        print(f"    ❌ {result['error']}", file=sys.stderr)
        _gateway._log(
            {
                "type": "watch_exception",
                "member": m["name"],
                "room": m["room"],
                "error": result["error"],
            }
        )
    finally:
        try:
            finish_watch(
                m,
                result,
                medals,
                before_intimacy,
                start_day,
                session_id,
                started,
                sessdata,
                bili_jct,
                _gateway,
            )
        finally:
            _gateway.EVENT_CONTEXT.reset(token)
            if (
                lock_file
                and lock_file.exists()
                and (lock_file.read_text().strip() == str(os.getpid()))
            ):
                lock_file.unlink(missing_ok=True)
            lease.close()
    return result


def finish_watch(
    m, result, medals, before_intimacy, start_day, session_id, started, sessdata, bili_jct, _gateway
):
    try:
        refreshed_medals = _gateway.get_my_medals(sessdata, bili_jct)
    except Exception:
        refreshed_medals = {}
    after = refreshed_medals.get(m["uid"], {}).get("today_intimacy")
    result.update(_gateway.intimacy_change(before_intimacy, after, start_day, _gateway.task_day()))
    if m["uid"] in refreshed_medals:
        medals[m["uid"]] = refreshed_medals[m["uid"]]
    result["session_id"] = session_id
    _gateway._log(
        {
            "type": "watch_end",
            "member": m["name"],
            "room": m["room"],
            "minutes": (
                result.get("minutes", 0)
                if result.get("success")
                else max(result.get("minutes", 0), int((time.time() - started) / 60))
            ),
            "beats_ok": result.get("beats_ok", 0),
            "success": result.get("success", False),
            "stopped_reason": result.get("stopped_reason", "error"),
            "intimacy_before": result.get("intimacy_before"),
            "intimacy_after": result.get("intimacy_after"),
            "intimacy_delta": result.get("intimacy_delta"),
            "intimacy_note": result.get("intimacy_note", ""),
        }
    )
