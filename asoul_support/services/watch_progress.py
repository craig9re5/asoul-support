"""Verify watch rewards independently of heartbeat acceptance and reaction tasks."""

import re
import sys
import time
from .. import safety

CHECK_INTERVAL = 10 * 60
MIN_STALL_SECONDS = 30 * 60
MAX_REWARD_RECONNECTS = 2


def parse_watch_task(club):
    tasks = club.get("task_info", []) if isinstance(club, dict) else []
    if not isinstance(tasks, list):
        return None
    task = next((t for t in tasks if isinstance(t, dict) and t.get("jump_type") == "watchLive"), None)
    if not task:
        return None
    subtitle = task.get("sub_title")
    match = re.search(r"(\d+)\s*/\s*(\d+)", subtitle) if isinstance(subtitle, str) else None
    if not match:
        return {"done": True} if task.get("is_done") else None
    current, limit = map(int, match.groups())
    if limit < 1 or current > limit:
        return None
    title = task.get("title")
    minutes = re.search(r"(\d+)\s*分钟", title) if isinstance(title, str) else None
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
        self.reconnects = 0
        self.recovery_episodes = {}
        self.next_recovery_check = 0

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
        self._publish()

    def _episode(self):
        progress = self.result.get("progress") or {}
        return (self.result.get("day"), progress.get("current"), progress.get("limit"))

    def maybe_recover(self, chain):
        """One E per stalled progress value; never restart on an unverified read."""
        now = time.monotonic()
        if (self.result.get("status") != "stalled" or now < self.next_recovery_check
                or self._episode() in self.recovery_episodes
                or self.reconnects >= MAX_REWARD_RECONNECTS
                or safety.status(self.credentials[0])["blocked"]):
            return
        self.next_recovery_check = now + CHECK_INTERVAL
        # Delayed credit may have arrived since the last scheduled observation.
        self.check(force=True)
        if self.result.get("status") != "stalled":
            return
        if self._episode() in self.recovery_episodes:
            return
        try:
            live = self.gateway._get_single_room_status(self.room, *self.credentials)
        except (OSError, ValueError, RuntimeError) as exc:
            self.gateway._log({"type": "watch_reward_live_query_error", "room_id": self.room,
                               "error": type(exc).__name__})
            return
        if (not live or live.get("live_status") != 1
                or safety.status(self.credentials[0])["blocked"]):
            return
        self.reconnects += 1
        episode = self._episode()
        recovery = {"status": "failed", "attempt": self.reconnects,
                    "attempted_at": time.time(), "started": time.monotonic(),
                    "accepted_at": self.accepted_seconds}
        # Record before IO so even a failed restart consumes this episode's budget.
        self.recovery_episodes[episode] = recovery
        try:
            if chain.restart():
                recovery["status"] = "reconnected"
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.gateway._log({"type": "watch_reward_reconnect_error", "room_id": self.room,
                               "error": type(exc).__name__})
        self.gateway._log({"type": "watch_reward_reconnect", "room_id": self.room,
                           "attempt": self.reconnects, "success": recovery["status"] == "reconnected"})
        self._publish()

    def _publish(self):
        recovery = self.recovery_episodes.get(self._episode())
        if recovery and self.result["status"] == "stalled":
            elapsed = max(0, time.monotonic() - recovery["started"])
            if (recovery["status"] == "reconnected" and elapsed >= MIN_STALL_SECONDS
                    and self.accepted_seconds - recovery["accepted_at"] >= MIN_STALL_SECONDS):
                recovery["status"] = "pending_rewards"
            message = {
                "reconnected": "已自动重建该房间心跳，正在等待服务端结算；同一次停滞不再重连。",
                "failed": "自动重建心跳未成功，同一次停滞不再重试，请检查网络或在 B 站核对。",
                "pending_rewards": "重建心跳后又观察至少 30 分钟，仍未确认看播增长；请在 B 站核对，不继续重连。",
            }[recovery["status"]]
            progress = self.result["progress"]
            self.result["warning"] = f"看播进度 {progress['current']}/{progress['limit']}：{message}"
        elif self.result["status"] == "stalled" and self.reconnects >= MAX_REWARD_RECONNECTS:
            self.result["warning"] += " 本轮收益恢复重连次数已达上限，请手动核对。"
        self.result["recovery"] = {"attempts": self.reconnects, "max_attempts": MAX_REWARD_RECONNECTS,
                                   "status": recovery["status"] if recovery else "none",
                                   "attempted_at": recovery["attempted_at"] if recovery else None}
        kind = self.result["status"] if self.result["warning"] else ""
        if kind == "stalled" and recovery and recovery["status"] in {"failed", "pending_rewards"}:
            kind += ":" + recovery["status"]
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
