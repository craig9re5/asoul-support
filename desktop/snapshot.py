import os
import time
from asoul_support.runtime import APP_VERSION, task_day


def project_snapshot(engine, states, now):
    import datetime

    rows = []
    for member in engine.members:
        rows.append(project_row(engine, member, states[member["room"]], now))
    return {
        "paused": engine.paused,
        "safety": getattr(engine, "safety", {"blocked": False}),
        "checking": engine.probe is not None,
        "error": engine.error,
        "account": engine.account,
        "rows": rows,
        "account_confirmed": bool(
            engine.account
            and engine.account_checked_at
            and (
                now - engine.account_checked_at
                <= max(180, engine.config.get("check_minutes", 30) * 60 + 180)
            )
        ),
        "account_checked_at": engine.account_checked_at,
        "medals": engine.medals,
        "tasks": engine.tasks,
        "last_check": engine.last_check,
        "next_check": engine.next_check,
        "pid": os.getpid(),
        "updated": time.time(),
        "running": True,
        "stale": False,
        "version": APP_VERSION,
    }


def project_row(engine, member, state, now):
    room = member["room"]
    uid = member.get("uid")
    room_str = str(room)
    medal = engine.medals.get(uid) or engine.medals.get(str(uid)) or {}
    task_entry = engine.tasks.get(room_str, {})
    live_info = engine.statuses.get(room_str, {})
    ttl = max(180, engine.config.get("check_minutes", 30) * 60 + 180)
    observed = engine.status_times.get(room_str, 0)
    status_stale = not observed or now - observed > ttl
    query_error = engine.status_errors.get(room_str, "")
    live_status = live_info.get("live_status") if not status_stale and (not query_error) else None
    tasks_stale = (
        status_stale
        or bool(query_error)
        or task_entry.get("day") != task_day()
        or (now - task_entry.get("updated", 0) > ttl)
        or bool(engine.task_errors.get(room_str))
    )
    live_time_val = live_info.get("live_time")
    live_duration = elapsed_label(live_status, live_time_val, now)
    task_result = state.get("task_result", {})
    task_errors = [task_result.get("error")] + [
        (task_result.get(k) or {}).get("error") for k in ("danmaku", "like")
    ]
    task_error = (
        "；".join((str(e) for e in task_errors if e))
        if task_result.get("day") == task_day()
        else ""
    )
    active = room in engine.workers and engine.workers[room].poll() is None
    heartbeat_stale = active and now - state.get("last_heartbeat", state.get("started", now)) > max(
        180, state.get("interval", 60) * 2 + 90
    )
    phase = (
        "心跳已过期，等待恢复"
        if heartbeat_stale
        else (
            state.get("phase", "正在连接")
            if active
            else (
                "已暂停"
                if engine.paused
                else (
                    "查询失败"
                    if query_error
                    else (
                        "状态已过期"
                        if status_stale and observed
                        else (
                            "等待重试"
                            if state.get("phase") == "运行失败"
                            else (
                                "直播中，等待检查"
                                if live_status == 1
                                else "未开播" if live_status in (0, 2) else "等待检查"
                            )
                        )
                    )
                )
            )
        )
    )
    safety = getattr(engine, "safety", {})
    if safety.get("blocked"):
        phase = "账号保护暂停"
        task_error = safety.get("reason", "需要处理账号异常")
    return {
        **member,
        "phase": phase,
        "active": active,
        "status_stale": status_stale,
        "status_error": query_error,
        "status_updated": observed,
        "heartbeat_stale": heartbeat_stale,
        "tasks_stale": tasks_stale,
        "session_id": state.get("session_id"),
        "task_error": task_error,
        "started": state.get("started"),
        "beats": state.get("beats", 0),
        "last_heartbeat": state.get("last_heartbeat"),
        "error": state.get("error", "") if active else "",
        "title": live_info.get("title", ""),
        "area_name": live_info.get("area_name", ""),
        "live_status": live_status,
        "live_time": live_time_val or "",
        "live_duration": live_duration,
        "medal_name": medal.get("medal_name", ""),
        "medal_level": medal.get("level", 0),
        "is_lighted": medal.get("is_lighted", 0),
        "today_intimacy": medal.get("today_intimacy", 0),
        "day_limit": medal.get("day_limit", 0),
        "tasks": [] if tasks_stale else task_entry.get("tasks", []),
        "intimacy": task_entry.get("intimacy", 0),
        "next_intimacy": task_entry.get("next_intimacy", 0),
        "task_light_days": task_entry.get("task_light_days", 0),
    }


def elapsed_label(live_status, live_time_val, now):
    import datetime

    live_duration = ""
    if live_status == 1 and live_time_val and (live_time_val != "0000-00-00 00:00:00"):
        try:
            if isinstance(live_time_val, (int, float)) and live_time_val > 0:
                t = float(live_time_val)
            else:
                t = time.mktime(
                    datetime.datetime.strptime(str(live_time_val), "%Y-%m-%d %H:%M:%S").timetuple()
                )
            diff = max(0, int(now - t))
            live_duration = (
                f"已播 {diff / 3600:.1f}h" if diff >= 3600 else f"已播 {max(1, diff // 60)}m"
            )
        except Exception:
            pass
    return live_duration
