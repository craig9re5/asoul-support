import sys
import time
import uuid
from typing import Optional, Dict
from ..policies import *
from .. import safety


def intimacy_change(before, after, start_day, end_day, *, _gateway):
    result = {"intimacy_before": before, "intimacy_after": after, "intimacy_delta": None}
    if start_day != end_day:
        result["intimacy_note"] = "跨日，今日亲密度计数重置，无法直接计算本轮增量"
    elif before is None or after is None:
        result["intimacy_note"] = "未取得完整亲密度数据"
    elif after < before:
        result["intimacy_note"] = "今日计数回退，无法确认本轮增量"
    else:
        result["intimacy_delta"] = after - before
    return result


def watch_room(
    member: Dict,
    sessdata: str,
    bili_jct: str,
    duration_min: int = WATCH_MINUTES,
    interval: int = HEARTBEAT_INTERVAL,
    until_offline: bool = False,
    title: str = "",
    send_danmaku: bool = True,
    send_live_likes: bool = False,
    medal_info: Optional[Dict] = None,
    auto_revive: bool = True,
    auto_intimacy: bool = True,
    *,
    _gateway,
) -> Dict:
    """对一个直播间进行 X25Kn 心跳挂机。until_offline=True 时持续到下播为止。"""
    room_id = member["room"]
    up_id = member["uid"]
    name = member["name"]
    entered = _gateway.enter_room(room_id, sessdata, bili_jct)
    if not entered:
        return {
            "name": name,
            "room": room_id,
            "success": False,
            "error": "进入直播间失败",
            "beats_ok": 0,
            "beats_total": 0,
            "minutes": 0,
        }
    room_info = _gateway._get_room_info(room_id, sessdata, bili_jct)
    area_id = room_info.get("area_id", 0) if room_info else 0
    parent_area_id = room_info.get("parent_area_id", 0) if room_info else 0
    buvid = _gateway._ensure_live_buvid(sessdata, bili_jct)
    task_runner = _gateway.DailyTaskRunner(
        room_id,
        up_id,
        sessdata,
        bili_jct,
        auto_revive=send_danmaku and auto_revive,
        auto_intimacy=send_danmaku and auto_intimacy,
        auto_like=send_live_likes,
    )
    if not buvid:
        return {
            "name": name,
            "room": room_id,
            "success": False,
            "error": "无法取得服务器设备会话，本轮停止连接",
            "beats_ok": 0,
            "beats_total": 0,
            "minutes": 0,
            "stopped_reason": "session",
        }
    uuid_str = str(uuid.uuid4())
    e_data = _gateway.x25kn_enter_room(
        room_id, parent_area_id, area_id, up_id, buvid, uuid_str, sessdata, bili_jct
    )
    if not e_data:
        return {
            "name": name,
            "room": room_id,
            "success": False,
            "error": "X25Kn E 失败",
            "beats_ok": 0,
            "beats_total": 0,
            "minutes": 0,
        }
    chain = HeartbeatChain(
        room_id,
        parent_area_id,
        area_id,
        up_id,
        buvid,
        uuid_str,
        sessdata,
        bili_jct,
        e_data,
        interval,
        _gateway,
    )
    print(
        f"    📱 X25Kn 心跳已就绪（服务端间隔 {chain.heartbeat_interval}s，看播涨亲密度）",
        file=sys.stderr,
    )
    if until_offline:
        return _watch_until_offline(
            chain,
            task_runner,
            name,
            room_id,
            title,
            interval,
            duration_min,
            send_danmaku,
            send_live_likes,
            sessdata,
            bili_jct,
            _gateway,
        )
    else:
        return _watch_duration(
            chain,
            task_runner,
            name,
            room_id,
            title,
            interval,
            duration_min,
            send_danmaku,
            send_live_likes,
            sessdata,
            bili_jct,
            _gateway,
        )


def _watch_until_offline(
    chain,
    task_runner,
    name,
    room_id,
    title,
    interval,
    duration_min,
    send_danmaku,
    send_live_likes,
    sessdata,
    bili_jct,
    _gateway,
):
    title_str = f"「{title}」" if title else ""
    start_clock = time.strftime("%H:%M")
    _gateway._notify(f"🔴 **{name}** 开播啦！{title_str}\n开始时间：{start_clock}，自动挂机中...")
    if send_danmaku or send_live_likes:
        print("    💬 检查已启用的每日任务...", file=sys.stderr)
        _check_tasks(task_runner, room_id, _gateway)
    next_danmaku_check = time.monotonic() + _gateway.DANMAKU_RECHECK_INTERVAL
    print(f"    ⏱  开始挂机直到下播（每 {interval}s 心跳一次）...", file=sys.stderr)
    beats_ok = 0
    beat_num = 0
    consecutive_fail = 0
    start_time = time.time()
    while True:
        hold = safety.status(sessdata)
        if hold["blocked"]:
            return {
                "name": name,
                "room": room_id,
                "success": False,
                "error": hold["reason"],
                "stopped_reason": "safety",
                "beats_ok": beats_ok,
                "beats_total": beat_num,
                "minutes": int((time.time() - start_time) / 60),
                "x25kn": True,
            }
        beat_num += 1
        result = chain.beat()
        if result:
            beats_ok += 1
            consecutive_fail = 0
        else:
            consecutive_fail += 1
        elapsed_min = int((time.time() - start_time) / 60)
        if beat_num % 5 == 0:
            print(
                f"    💓 心跳 {beat_num}(X25Kn)  已挂 {elapsed_min} 分钟  ok:{beats_ok}",
                file=sys.stderr,
            )
        status = _gateway._get_single_room_status(room_id, sessdata, bili_jct)
        if status and status.get("live_status") != 1:
            elapsed_min = int((time.time() - start_time) / 60)
            end_clock = time.strftime("%H:%M")
            h, m = divmod(elapsed_min, 60)
            dur_str = f"{h}小时{m}分钟" if h else f"{m}分钟"
            _gateway._notify(
                f"📴 **{name}** 下播了\n直播时长：{start_clock} - {end_clock}（{dur_str}）"
            )
            print(f"    📴 检测到下播，共挂机 {elapsed_min} 分钟", file=sys.stderr)
            return {
                "name": name,
                "room": room_id,
                "success": beats_ok > 0,
                "beats_ok": beats_ok,
                "beats_total": beat_num,
                "minutes": elapsed_min,
                "stopped_reason": "offline",
                "x25kn": True,
            }
        if consecutive_fail >= 10:
            elapsed_min = int((time.time() - start_time) / 60)
            print(f"    ❌ 连续 {consecutive_fail} 次心跳失败，退出", file=sys.stderr)
            return {
                "name": name,
                "room": room_id,
                "success": False,
                "error": "连续心跳失败",
                "beats_ok": beats_ok,
                "beats_total": beat_num,
                "minutes": elapsed_min,
                "stopped_reason": "error",
                "x25kn": True,
            }
        if (send_danmaku or send_live_likes) and (
            _gateway.task_day() != task_runner.day or time.monotonic() >= next_danmaku_check
        ):
            next_danmaku_check = time.monotonic() + _gateway.DANMAKU_RECHECK_INTERVAL
            _check_tasks(task_runner, room_id, _gateway)


def _watch_duration(
    chain,
    task_runner,
    name,
    room_id,
    title,
    interval,
    duration_min,
    send_danmaku,
    send_live_likes,
    sessdata,
    bili_jct,
    _gateway,
):
    started = time.monotonic()
    deadline = started + max(0, duration_min) * 60
    if send_danmaku or send_live_likes:
        _check_tasks(task_runner, room_id, _gateway)
    next_check = time.monotonic() + _gateway.DANMAKU_RECHECK_INTERVAL
    print(
        f"    ⏱  开始挂机 {duration_min} 分钟（当前服务端间隔 {chain.heartbeat_interval}s）...",
        file=sys.stderr,
    )
    beats_ok = 0
    beats_total = 0
    for _ in range(max(0, int(duration_min * 60 // 5)) + 1):
        if safety.status(sessdata)["blocked"]:
            break
        now = time.monotonic()
        ready_at = max(now, chain.last_response_at + chain.heartbeat_interval)
        if ready_at > deadline or now >= deadline:
            break
        result = chain.beat()
        beats_total += 1
        if result:
            beats_ok += 1
        elapsed_min = int((time.monotonic() - started) / 60)
        if beats_total % 5 == 0:
            print(f"    💓 心跳 {beats_total}(X25Kn)  已挂 {elapsed_min} 分钟", file=sys.stderr)
        if (
            (send_danmaku or send_live_likes)
            and time.monotonic() < deadline
            and (_gateway.task_day() != task_runner.day or time.monotonic() >= next_check)
        ):
            _check_tasks(task_runner, room_id, _gateway)
            next_check = time.monotonic() + _gateway.DANMAKU_RECHECK_INTERVAL
    actual_minutes = int((time.monotonic() - started) / 60)
    hold = safety.status(sessdata)
    return {
        "name": name,
        "room": room_id,
        "success": beats_ok > 0 and not hold["blocked"],
        "beats_ok": beats_ok,
        "beats_total": beats_total,
        "minutes": actual_minutes,
        "x25kn": True,
        **({"error": hold["reason"], "stopped_reason": "safety"} if hold["blocked"] else {}),
    }


class HeartbeatChain:

    def __init__(
        self,
        room_id,
        parent_area_id,
        area_id,
        up_id,
        buvid,
        uuid_str,
        sessdata,
        bili_jct,
        e_data,
        interval,
        gateway,
    ):
        self.room_id, self.parent_area_id, self.area_id, self.up_id = (
            room_id,
            parent_area_id,
            area_id,
            up_id,
        )
        self.buvid, self.uuid_str, self.sessdata, self.bili_jct = (
            buvid,
            uuid_str,
            sessdata,
            bili_jct,
        )
        self.gateway = gateway
        self.secret_key = e_data["secret_key"]
        self.secret_rule = e_data["secret_rule"]
        self.ets = e_data["timestamp"]
        self.heartbeat_interval = int(e_data.get("heartbeat_interval") or interval)
        if self.heartbeat_interval < 5 or self.heartbeat_interval > 300:
            self.heartbeat_interval = self.gateway.HEARTBEAT_INTERVAL
        self.protocol_seq = 0
        self.last_response_at = time.monotonic()
        print(f"    📡 X25Kn E 已通过，rule={self.secret_rule}", file=sys.stderr)

    def restart(self) -> bool:
        """X 失败后重新发送 E，避免用过期时间戳连续失败。"""
        restarted = self.gateway.x25kn_enter_room(
            self.room_id,
            self.parent_area_id,
            self.area_id,
            self.up_id,
            self.buvid,
            self.uuid_str,
            self.sessdata,
            self.bili_jct,
        )
        self.last_response_at = time.monotonic()
        if not restarted:
            return False
        self.secret_key = restarted["secret_key"]
        self.secret_rule = restarted["secret_rule"]
        self.ets = restarted["timestamp"]
        self.heartbeat_interval = int(
            restarted.get("heartbeat_interval") or self.gateway.HEARTBEAT_INTERVAL
        )
        if self.heartbeat_interval < 5 or self.heartbeat_interval > 300:
            self.heartbeat_interval = self.gateway.HEARTBEAT_INTERVAL
        self.protocol_seq = 0
        print("    🔄 已重建 X25Kn 心跳链", file=sys.stderr)
        return True

    def beat(self):
        """按服务端时间窗口发一次 X，并递推下一轮协议状态。"""
        self.gateway._wait_for_heartbeat_window(self.last_response_at, self.heartbeat_interval)
        next_seq = self.protocol_seq + 1
        result = self.gateway.x25kn_heartbeat(
            self.room_id,
            self.parent_area_id,
            self.area_id,
            self.up_id,
            next_seq,
            self.buvid,
            self.uuid_str,
            self.ets,
            self.secret_key,
            self.secret_rule,
            self.heartbeat_interval,
            self.sessdata,
            self.bili_jct,
        )
        self.last_response_at = time.monotonic()
        if result:
            self.protocol_seq = next_seq
            self.secret_key = result.get("secret_key", self.secret_key)
            self.secret_rule = result.get("secret_rule", self.secret_rule)
            self.ets = result.get("timestamp", self.ets)
            next_interval = int(result.get("heartbeat_interval") or self.heartbeat_interval)
            if 5 <= next_interval <= 300:
                self.heartbeat_interval = next_interval
            self.gateway._log(
                {
                    "type": "x25kn_x_success",
                    "room_id": self.room_id,
                    "seq": self.protocol_seq,
                    "interval": self.heartbeat_interval,
                }
            )
        else:
            if not safety.status(self.sessdata)["blocked"]:
                self.restart()
        return result


def _check_tasks(task_runner, room_id, _gateway):
    try:
        result = task_runner.check()
        if not result["success"]:
            errors = [result.get("error")] + [
                (result.get(k) or {}).get("error") for k in ("danmaku", "like")
            ]
            print("    ⚠️  " + "；".join((e for e in errors if e)), file=sys.stderr)
    except Exception as exc:
        _gateway._log({"type": "task_check_error", "room_id": room_id, "error": type(exc).__name__})
