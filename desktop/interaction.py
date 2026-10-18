"""Shared action availability and recovery routes, independent of Tk widgets."""

import math
import time


def action_reason(snap, row, action, pending=False, now=None):
    now = time.time() if now is None else now
    if not row or not row.get("room"):
        return "请先选择主播。"
    if action == "open":
        return ""
    if snap.get("closing"):
        return "正在退出，当前不接受新操作。"
    if pending:
        return "该直播间已有操作正在执行，请等待结果。"
    hold = snap.get("safety", {})
    if snap.get("ui_error"):
        return "界面状态异常，请先点击“重试界面”。"
    if hold.get("blocked"):
        if hold.get("kind") in ("auth", "credentials"):
            return "登录已失效，请点击上方“重新扫码登录”。"
        if hold.get("until"):
            return "账号冷却中，到时自动恢复；可打开直播间核对。"
        return "账号保护暂停，请先点击上方“解除异常暂停”。"
    if snap.get("paused"):
        return "挂机已暂停，请先点击“恢复挂机”。"
    if snap.get("engine_busy"):
        return "后台操作执行中，等待状态刷新后再试。"
    if not snap.get("account_confirmed", bool(snap.get("account"))):
        return "登录状态尚未验证，请立即检查或前往账号管理扫码。"
    if action == "reconnect":
        if row.get("reconnecting"):
            return "正在重新建立连接，请等待成功心跳。"
        remaining = row.get("reconnect_cooldown_until", 0) - now
        if remaining > 0:
            return f"重连冷却中，约 {math.ceil(remaining)} 秒后可重试。"
        if row.get("reconnect_allowed"):
            return ""
    if row.get("live_status") is None and action != "wear":
        return "直播状态待确认，请点击“立即检查”。"
    if row.get("live_status") != 1 and action != "wear":
        return "主播已下播，开播后可以操作。"
    if action == "wear" and not row.get("medal_name"):
        return "没有可佩戴的粉丝牌，可先同步粉丝牌。"
    return "" if action != "reconnect" else "连接尚未就绪，请立即检查后重试。"


def recovery_route(snap):
    """Every advertised failure has a visible next step; no guessed risk reason."""
    hold = snap.get("safety", {})
    if snap.get("ui_error"):
        return {"action": "refresh", "label": "重试界面", "message": snap["ui_error"] + "；也可查看活动记录。"}
    if hold.get("blocked"):
        if hold.get("kind") in ("auth", "credentials"):
            return {"action": "login", "label": "重新扫码登录", "message": hold.get("reason", "登录失效，请扫码恢复。")}
        if hold.get("until"):
            until = time.strftime("%H:%M:%S", time.localtime(hold["until"]))
            return {"action": "safety", "label": "查看冷却说明", "message": f"{hold.get('reason', '账号冷却中')}；{until} 后自动恢复。"}
        return {"action": "safety", "label": "解除异常暂停", "message": hold.get("reason", "请先在 B 站处理账号异常，再恢复。")}
    if snap.get("paused"):
        return {"action": "resume", "label": "恢复挂机", "message": "挂机已暂停，点击“恢复挂机”继续。"}
    if snap.get("engine_busy"):
        return {"action": "logs", "label": "查看日志", "message": "后台操作执行中，界面可继续浏览；状态暂未刷新。"}
    if snap.get("error"):
        return {"action": "check", "label": "重试检查", "message": snap["error"] + "；可重试检查或查看活动记录。"}
    if not snap.get("account_confirmed", bool(snap.get("account"))):
        if snap.get("account"):
            return {"action": "check", "label": "验证登录状态", "message": "登录状态待验证，请立即检查；登录失效可在账号管理扫码。"}
        return {"action": "login", "label": "扫码登录", "message": "尚未确认登录，请扫码登录；已保存登录信息可点击立即检查。"}
    for field, label in (("connection_warning", "查看连接异常"), ("watch_warning", "核对观看收益"),
                         ("status_error", "重试直播查询"), ("task_error", "核对任务异常")):
        row = next((row for row in snap.get("rows", []) if row.get(field)), None)
        if row:
            action = "check" if field == "status_error" else "room"
            return {"action": action, "label": label, "room": row["room"],
                    "message": f"【{row['name']}】{row[field]}"}
    if any(row.get("status_stale") or row.get("tasks_stale") for row in snap.get("rows", [])):
        return {"action": "check", "label": "更新进度", "message": "部分状态或任务进度已过期，请立即检查。"}
    return {}
