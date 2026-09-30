"""Explicit account/watch experiment; danmaku opt-in, live likes always excluded."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def task_summary(club):
    return {
        "available": bool(club),
        "intimacy": club.get("intimacy"),
        "is_lighted": club.get("is_lighted"),
        "tasks": [
            {key: task.get(key) for key in ("title", "sub_title", "is_done")}
            for task in club.get("task_info", [])
        ],
    }


def main():
    from asoul_support.application import AppContext
    from asoul_support.runtime import data_dir, read_json, FileLock
    import urllib.request

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=data_dir())
    parser.add_argument("--room", type=int)
    parser.add_argument("--watch-minutes", type=int, default=0)
    parser.add_argument(
        "--danmaku-tasks",
        action="store_true",
        help="显式启用已配置的自动点亮/每日弹幕任务；不发送直播点赞",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "build/account-experiment.json")
    args = parser.parse_args()
    if not 0 <= args.watch_minutes <= 20:
        parser.error("watch-minutes must be 0..20")
    if args.watch_minutes and not args.room:
        parser.error("watch experiments require one explicit --room")
    if args.danmaku_tasks and not args.watch_minutes:
        parser.error("danmaku tasks require a bounded watch experiment")
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "requests": {},
        "rooms": [],
        "task_checks": [],
    }

    def observe(event):
        if event.get("type") == "task_check":
            report["task_checks"].append(
                {key: event.get(key) for key in ("room_id", "ts", "success", "danmaku", "like")}
            )

    app = AppContext(args.data_dir, observer=observe)
    credentials = app.credentials()
    members = read_json(args.data_dir / "members.json", [])
    if args.room:
        members = [m for m in members if m["room"] == args.room]
        if not members:
            parser.error("room must be in the configured member list")
    policy = read_json(args.data_dir / "settings.json", {})
    auto_revive = args.danmaku_tasks and policy.get("auto_revive", True)
    auto_intimacy = args.danmaku_tasks and policy.get("auto_danmaku_intimacy", True)
    report["policy"] = {
        "auto_revive": bool(auto_revive),
        "auto_intimacy": bool(auto_intimacy),
        "live_likes": False,
    }
    original_open = urllib.request.OpenerDirector.open

    def guarded_open(opener, request, *positional, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else request
        parsed = urlsplit(url)
        method = request.get_method() if hasattr(request, "get_method") else "GET"
        # Small explicit allowlist: no reaction, speech, gifts, medal or content writes.
        allowed_post = {
            # This endpoint uses POST to read a batch of live statuses.
            "/room/v1/Room/get_status_info_by_uids",
            "/xlive/web-room/v1/index/roomEntryAction",
            "/xlive/data-interface/v1/x25Kn/E",
            "/xlive/data-interface/v1/x25Kn/X",
        }
        if auto_revive or auto_intimacy:
            allowed_post.add("/msg/send")
        if parsed.scheme != "https" or parsed.hostname not in {
            "api.bilibili.com",
            "api.live.bilibili.com",
            "www.bilibili.com",
            "live-trace.bilibili.com",
        }:
            raise RuntimeError("Experiment blocked an unexpected host")
        if "like" in parsed.path.lower() or (method != "GET" and parsed.path not in allowed_post):
            raise RuntimeError("Experiment blocked an unexpected action")
        label = method + " " + parsed.hostname + parsed.path
        report["requests"][label] = report["requests"].get(label, 0) + 1
        return original_open(opener, request, *positional, **kwargs)

    with patch.object(urllib.request.OpenerDirector, "open", guarded_open):
        valid, login_message = app.validate_credentials(*credentials)
        report["login_valid"] = valid
        if valid:
            statuses = app.call("check_live_status", [m["room"] for m in members], *credentials)
            medals = app.call("get_my_medals", *credentials)
            report["medal_count"] = len(medals)
            for member in members:
                room = member["room"]
                status = statuses.get(room, {})
                before = app.call("get_fans_club_task_info", room, member["uid"], *credentials)
                row = {
                    "room": room,
                    "name": member["name"],
                    "live_status": status.get("live_status"),
                    "before": task_summary(before),
                }
                report["rooms"].append(row)
                if args.watch_minutes and status.get("live_status") == 1:
                    with FileLock(args.data_dir / "locks" / f"{room}.watch.lock") as lease:
                        if lease.acquired:
                            row["watch"] = app.call(
                                "watch_room",
                                member,
                                *credentials,
                                duration_min=args.watch_minutes,
                                send_danmaku=bool(auto_revive or auto_intimacy),
                                send_live_likes=False,
                                auto_revive=bool(auto_revive),
                                auto_intimacy=bool(auto_intimacy),
                            )
                            row["after"] = task_summary(
                                app.call(
                                    "get_fans_club_task_info", room, member["uid"], *credentials
                                )
                            )
                        else:
                            row["watch"] = {"skipped": True, "reason": "existing room session"}
                elif args.watch_minutes:
                    row["watch"] = {"skipped": True, "reason": "room is not live"}
        else:
            report["error"] = login_message
    report["success"] = (
        valid
        and bool(report["rooms"])
        and all(
            row["live_status"] in (0, 1, 2)
            and row["before"]["available"]
            and (not args.watch_minutes or row.get("watch", {}).get("success", False))
            for row in report["rooms"]
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
