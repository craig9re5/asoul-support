from desktop.health import number, heartbeat_timeout
from datetime import datetime, timezone, timedelta
import os
import time
from asoul_support.runtime import APP_VERSION, task_day
from asoul_support.services.watch_progress import CHECK_INTERVAL, parse_watch_task


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
    medals_stale = tasks_stale
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
    heartbeat_stale = active and now - number(
        state.get("last_heartbeat"), number(state.get("started"), now)
    ) > heartbeat_timeout(state)
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
    if state.get("state_error"):
        phase = "状态记录异常"
        task_error = state["state_error"]
    safety = getattr(engine, "safety", {})
    if safety.get("blocked"):
        phase = "账号保护暂停"
        task_error = safety.get("reason", "需要处理账号异常")
    recovery = getattr(engine, "manual_reconnects", {}).get(room, {})
    recovering = recovery.get("state") == "checking"
    if recovering and not safety.get("blocked") and not engine.paused:
        phase = "重连中，正在确认直播"
    heartbeat_healthy = bool(active and state.get("last_heartbeat") and not heartbeat_stale
                             and not safety.get("blocked") and not engine.paused)
    connection_warning = ""
    if heartbeat_stale and not engine.paused and not safety.get("blocked"):
        connection_warning = "长时间没有成功心跳，看播收益可能中断。可点击下方“重连此直播间”恢复连接。"
        if state.get("task_started"):
            connection_warning += " 当前任务仍在执行，重连会停止该任务并只恢复看播。"
    elif recovery.get("state") == "failed" and not engine.paused and not safety.get("blocked"):
        connection_warning = recovery.get("message", "重连失败，请稍后再试。")
    reconnect_allowed = bool((active or live_status == 1 or connection_warning)
                             and not engine.paused and not safety.get("blocked") and not recovering
                             and now >= recovery.get("cooldown_until", 0))
    watch, watch_warning, task_entry, tasks_stale = watch_observation(
        state, task_entry, active, tasks_stale, now
    )
    if safety.get("blocked") or engine.paused or heartbeat_stale:
        watch_warning = ""
    today_value = medal.get("today_intimacy")
    checked = engine.account_checked_at
    medal_day = (datetime.fromtimestamp(checked, timezone(timedelta(hours=8))).date().isoformat()
                 if checked else "")
    gain = (today_value if not medals_stale and medal_day == task_day()
            and isinstance(today_value, int) and not isinstance(today_value, bool)
            and today_value >= 0 else None)
    return {
        **member,
        "phase": phase,
        "active": active,
        "status_stale": status_stale,
        "status_error": query_error,
        "status_updated": observed,
        "heartbeat_stale": heartbeat_stale,
        "heartbeat_healthy": heartbeat_healthy,
        "connection_warning": connection_warning,
        "reconnect_allowed": reconnect_allowed,
        "reconnecting": recovering or (recovery.get("state") == "starting" and not heartbeat_healthy and active),
        "reconnect_message": ("重连成功，已收到服务端心跳。" if recovery.get("state") == "starting"
                              and heartbeat_healthy else recovery.get("message", "")),
        "tasks_stale": tasks_stale,
        "session_id": state.get("session_id"),
        "task_error": task_error,
        "watch_warning": watch_warning,
        "watch_progress": watch,
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
        "intimacy_gain": gain,
        "avatar_url": live_info.get("face", ""),
        "day_limit": medal.get("day_limit", 0),
        "tasks": [] if tasks_stale else task_entry.get("tasks", []),
        "intimacy": task_entry.get("intimacy", 0),
        "next_intimacy": task_entry.get("next_intimacy", 0),
        "task_light_days": task_entry.get("task_light_days", 0),
    }


def watch_observation(state, task_entry, active, tasks_stale, now):
    """Project verified task rows without making an old medal counter look fresh."""
    watch = state.get("watch_progress", {}) if active else {}
    if watch.get("day") != task_day():
        return {}, "", task_entry, tasks_stale
    warning = ""
    ttl = CHECK_INTERVAL * 2 + 180
    if 0 <= now - number(watch.get("checked_at")) <= ttl:
        warning = watch.get("warning", "")
        if (number(watch.get("verified_at")) >= task_entry.get("updated", 0)
                and 0 <= now - number(watch.get("verified_at")) <= ttl
                and isinstance(watch.get("tasks"), list)):
            task_entry = {**task_entry, **{key: watch[key] for key in
                                         ("tasks", "intimacy", "next_intimacy") if key in watch}}
            tasks_stale = False
    else:
        warning = "看播进度核验已过期，无法确认亲密度是否到账，请点击立即检查。"
    progress = parse_watch_task({"task_info": task_entry.get("tasks", [])})
    if (not tasks_stale and progress and (progress.get("done")
            or progress.get("current", -1) > (watch.get("progress") or {}).get("current", -1))):
        warning = ""
    return watch, warning, task_entry, tasks_stale


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
