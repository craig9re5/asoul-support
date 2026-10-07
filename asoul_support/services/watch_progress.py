"""Verify watch rewards independently of heartbeat acceptance and reaction tasks."""

import re
import sys
import time

CHECK_INTERVAL = 10 * 60
MIN_STALL_SECONDS = 30 * 60


def parse_watch_task(club):
    tasks = club.get("task_info", []) if isinstance(club, dict) else []
    task = next((t for t in tasks if isinstance(t, dict) and t.get("jump_type") == "watchLive"), None)
    if not task:
        return None
    match = re.search(r"(\d+)\s*/\s*(\d+)", task.get("sub_title") or "")
    if not match:
        return {"done": True} if task.get("is_done") else None
    current, limit = map(int, match.groups())
    if limit < 1 or current > limit:
        return None
    minutes = re.search(r"(\d+)\s*分钟", task.get("title") or "")
    round_minutes = int(minutes[1]) if minutes else 15
    if not 1 <= round_minutes <= 120:
        round_minutes = 15
    return {"current": current, "limit": limit, "done": bool(task.get("is_done")) or current >= limit,
            "threshold": max(MIN_STALL_SECONDS, 2 * round_minutes * 60)}


class ProgressTracker:
    """A fresh baseline, elapsed time and accepted heartbeats are all required."""

    def __init__(self):
        self.day = None
        self.baseline = None
        self.baseline_at = None
        self.accepted_at = 0
        self.last_valid = None
        self.valid = None

    def observe(self, club, day, now, accepted_seconds):
        if day != self.day:
            self.__init__()
            self.day = day
            self.baseline_at = now
            self.accepted_at = accepted_seconds
        progress = parse_watch_task(club)
        if progress is None:
            age = max(0, now - (self.last_valid if self.last_valid is not None else self.baseline_at))
            warning = ("长时间无法核验看播任务，心跳成功不能证明亲密度到账，请点击立即检查或在 B 站核对。"
                       if age >= MIN_STALL_SECONDS else "")
            return {"status": "unavailable", "warning": warning, "progress": self.valid,
                    "unchanged_minutes": int(age / 60)}
        self.last_valid = now
        self.valid = progress
        if progress["done"]:
            return {"status": "complete", "warning": "", "progress": progress}
        if club.get("reach_free_intimacy_limit"):
            self.baseline = None
            self.baseline_at = now
            self.accepted_at = accepted_seconds
            return {"status": "limited", "warning": "储蓄亲密度已达上限，看播可能无法继续获得亲密度，请在 B 站核对。",
                    "progress": progress}
        key = (progress["current"], progress["limit"])
        # A rollback, target change or delayed credit establishes a new baseline.
        if self.baseline != key:
            self.baseline, self.baseline_at, self.accepted_at = key, now, accepted_seconds
        unchanged = max(0, now - self.baseline_at)
        stalled = (unchanged >= progress["threshold"]
                   and accepted_seconds - self.accepted_at >= progress["threshold"])
        warning = (f"看播进度已约 {int(unchanged / 60)} 分钟未增长（{progress['current']}/{progress['limit']}），"
                   "虽有成功心跳，奖励尚未确认；可能延迟结算，请在 B 站核对。" if stalled else "")
        return {"status": "stalled" if stalled else "tracking", "warning": warning,
                "progress": progress, "unchanged_minutes": int(unchanged / 60)}


class WatchProgressMonitor:
    def __init__(self, room, uid, name, sessdata, bili_jct, gateway):
        self.room, self.uid, self.name = room, uid, name
        self.credentials = (sessdata, bili_jct)
        self.gateway = gateway
        self.tracker = ProgressTracker()
        self.next_check = 0
        self.accepted_seconds = 0
        self.warning_kind = ""
        self.warning_since = None
        self.result = {}
        self.verified = {}

    def heartbeat(self, interval):
        self.accepted_seconds += interval
        self.check()

    def check(self, force=False):
        now = time.monotonic()
        if (not force and self.result.get("status") == "complete"
                and self.result.get("day") == self.gateway.task_day()):
            return
        if not force and now < self.next_check:
            return
        self.next_check = now + CHECK_INTERVAL
        try:
            club = self.gateway.get_fans_club_task_info(self.room, self.uid, *self.credentials)
        except (OSError, ValueError, RuntimeError) as exc:
            self.gateway._log({"type": "watch_progress_query_error", "room_id": self.room,
                               "error": type(exc).__name__})
            club = {}
        self.result = self.tracker.observe(club, self.gateway.task_day(), now, self.accepted_seconds)
        self.result.update(day=self.tracker.day, checked_at=time.time())
        if self.verified.get("day") != self.tracker.day:
            self.verified = {}
        if parse_watch_task(club) is not None:
            # Only a validated read can supply fresh task rows to the desktop.
            self.verified = {"day": self.tracker.day, "verified_at": time.time(),
                             "tasks": [{key: task.get(key) for key in
                                        ("jump_type", "title", "sub_title", "is_done")}
                                       for task in club.get("task_info", []) if isinstance(task, dict)],
                             "intimacy": club.get("intimacy", 0),
                             "next_intimacy": club.get("next_intimacy", 0)}
        self.result.update(self.verified)
        kind = self.result["status"] if self.result["warning"] else ""
        if kind and kind != self.warning_kind:
            self.warning_since = time.time()
        elif not kind and self.result["status"] != "unavailable":
            self.warning_since = None
        self.result["warning_since"] = self.warning_since
        event = {"type": "watch_progress", "room_id": self.room, **self.result}
        self.gateway._log(event)
        if kind and kind != self.warning_kind:
            print("    ⚠️  " + self.result["warning"], file=sys.stderr)
            self.gateway._log({**event, "type": "watch_progress_warning"})
            self.gateway._notify(f"⚠️ **{self.name}**：{self.result['warning']}")
        elif self.warning_kind and not kind and self.result["status"] != "unavailable":
            self.gateway._log({**event, "type": "watch_progress_recovered"})
        # Short read failures must not re-arm notifications for the same stall.
        if kind or self.result["status"] != "unavailable":
            self.warning_kind = kind
