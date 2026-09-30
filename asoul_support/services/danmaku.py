import random
import re
import sys
import time
from typing import Optional, Dict, Tuple
from ..policies import *
from .. import safety


def send_danmaku_batch(
    room_id: int,
    count: int,
    sessdata: str,
    bili_jct: str,
    used_pool: Optional[set] = None,
    delay: float = DANMAKU_DELAY,
    max_attempts: Optional[int] = None,
    deadline: Optional[float] = None,
    *,
    messages=None,
    _gateway,
) -> Tuple[int, set, int]:
    """Try to reach the target with bounded retries; return successes, used, attempts."""
    used = set(used_pool) if used_pool else set()
    pool = _gateway._DANMAKU_MSGS if messages is None else messages
    if not pool:
        raise ValueError("弹幕消息池不能为空")
    available = [m for m in pool if m not in used]
    if not available:
        available = list(pool)
    random.shuffle(available)
    sent_ok = 0
    attempted = 0
    limit = max_attempts if max_attempts is not None else count + min(count, 3)
    for i in range(max(0, limit)):
        if safety.status(sessdata)["blocked"]:
            break
        if sent_ok >= count or (deadline is not None and time.monotonic() >= deadline):
            break
        msg = available[i % len(available)]
        attempted += 1
        if _gateway._send_danmaku(room_id, msg, sessdata, bili_jct):
            sent_ok += 1
            used.add(msg)
        elif safety.status(sessdata)["blocked"]:
            break
        if delay > 0 and sent_ok < count and (i + 1 < limit):
            time.sleep(delay)
    return (sent_ok, used, attempted)


def light_up_medal(
    room_id: int, sessdata: str, bili_jct: str, count: int = LIGHT_UP_DANMAKU_COUNT, *, _gateway
) -> int:
    """开播时发弹幕点亮粉丝牌（保留兼容）"""
    sent, _, _ = _gateway.send_danmaku_batch(room_id, count, sessdata, bili_jct)
    print(f"    💬 弹幕点亮：{sent}/{count} 条", file=sys.stderr)
    return sent


def _danmaku_task_progress(club_info: Dict, *, _gateway) -> Optional[Dict]:
    tasks = club_info.get("task_info") if isinstance(club_info, dict) else None
    if not isinstance(tasks, list):
        return None
    task = next(
        (t for t in tasks if isinstance(t, dict) and t.get("jump_type") == "sendDanmu"), None
    )
    if not task:
        return None
    if task.get("is_done"):
        match = re.search("(\\d+)\\s*/\\s*(\\d+)", task.get("sub_title") or "")
        current, limit = (
            map(int, match.groups())
            if match
            else (_gateway.INTIMACY_DANMAKU_COUNT, _gateway.INTIMACY_DANMAKU_COUNT)
        )
        return {"current": current, "limit": limit, "done": True}
    match = re.search("(\\d+)\\s*/\\s*(\\d+)", task.get("sub_title") or "")
    if not match:
        return None
    current, limit = map(int, match.groups())
    if limit < 1 or current > limit:
        return None
    return {
        "current": current,
        "limit": limit,
        "done": bool(task.get("is_done")) or current >= limit,
    }


def send_medal_danmaku_tasks(
    room_id: int,
    anchor_uid: int,
    sessdata: str,
    bili_jct: str,
    medal_info: Optional[Dict] = None,
    max_attempts: Optional[int] = None,
    deadline: Optional[float] = None,
    auto_revive: bool = True,
    auto_intimacy: bool = True,
    *,
    messages=None,
    delay=DANMAKU_DELAY,
    _gateway,
) -> Dict:
    return MedalDanmakuTask(
        room_id,
        anchor_uid,
        sessdata,
        bili_jct,
        medal_info,
        max_attempts,
        deadline,
        auto_revive,
        auto_intimacy,
        messages,
        delay,
        _gateway,
    ).run()


class MedalDanmakuTask:

    def __init__(
        self,
        room_id,
        anchor_uid,
        sessdata,
        bili_jct,
        medal_info,
        max_attempts,
        deadline,
        auto_revive,
        auto_intimacy,
        messages,
        delay,
        gateway,
    ):
        self.room_id, self.anchor_uid = (room_id, anchor_uid)
        self.sessdata, self.bili_jct, self.medal_info = (sessdata, bili_jct, medal_info)
        self.max_attempts, self.deadline = (max_attempts, deadline)
        self.auto_revive, self.auto_intimacy = (auto_revive, auto_intimacy)
        self.messages, self.delay, self.gateway = (messages, delay, gateway)

    def run(self):
        failure = self.initial_state()
        if failure is not None:
            return failure
        self.revive()
        self.intimacy()
        return self.finish()

    def initial_state(self):
        self.club_info = self.gateway.get_fans_club_task_info(
            self.room_id, self.anchor_uid, self.sessdata, self.bili_jct
        )
        self.is_lighted = None
        if self.club_info and "is_lighted" in self.club_info:
            self.is_lighted = bool(self.club_info["is_lighted"])
        elif self.medal_info and "is_lighted" in self.medal_info:
            self.is_lighted = bool(self.medal_info["is_lighted"])
        if self.is_lighted is None:
            print("    ⚠️  无法确认粉丝牌点亮状态，本次跳过发送", file=sys.stderr)
            return {
                "light_sent": 0,
                "intimacy_sent": 0,
                "total_sent": 0,
                "attempted": 0,
                "done": False,
                "error": "无法确认粉丝牌状态",
            }
        self.progress = self.gateway._danmaku_task_progress(self.club_info)
        if self.auto_intimacy and self.is_lighted and (self.progress is None):
            print("    ⚠️  无法确认弹幕任务状态，本次跳过发送", file=sys.stderr)
            return {
                "light_sent": 0,
                "intimacy_sent": 0,
                "total_sent": 0,
                "attempted": 0,
                "done": False,
                "error": "无法确认任务状态",
            }
        self.progress_before = (
            f"{self.progress['current']}/{self.progress['limit']}" if self.progress else "未知"
        )
        self.used_msgs = set()
        self.batch_options = (
            {"messages": self.messages, "delay": self.delay} if self.messages is not None else {}
        )
        self.light_sent = 0
        self.intimacy_sent = 0
        self.attempted = 0

    def revive(self):
        if not self.auto_revive:
            print("    💬 [阶段 1/2] 自动点亮已关闭。", file=sys.stderr)
        elif not self.is_lighted:
            print(
                f"    💬 [阶段 1/2] 粉丝牌未点亮，发送 {self.gateway.LIGHT_UP_DANMAKU_COUNT} 条弹幕复活/点亮勋章...",
                file=sys.stderr,
            )
            self.light_sent, self.used_msgs, tries = self.gateway.send_danmaku_batch(
                self.room_id,
                self.gateway.LIGHT_UP_DANMAKU_COUNT,
                self.sessdata,
                self.bili_jct,
                used_pool=self.used_msgs,
                max_attempts=self.remaining_attempts(),
                deadline=self.deadline,
                **self.batch_options,
            )
            self.attempted += tries
            print(
                f"    💬 点亮弹幕完成：{self.light_sent}/{self.gateway.LIGHT_UP_DANMAKU_COUNT} 条",
                file=sys.stderr,
            )
            if self.light_sent:
                if self.deadline is None or time.monotonic() + 3 < self.deadline:
                    time.sleep(3)
                refreshed = self.gateway.get_fans_club_task_info(
                    self.room_id, self.anchor_uid, self.sessdata, self.bili_jct
                )
                if refreshed:
                    self.club_info = refreshed
                    self.is_lighted = bool(refreshed.get("is_lighted"))
                    self.progress = self.gateway._danmaku_task_progress(refreshed) or self.progress
        else:
            print(f"    💬 [阶段 1/2] 粉丝牌当前已处于点亮状态，跳过复活弹幕。", file=sys.stderr)

    def intimacy(self):
        if not self.auto_intimacy:
            print("    💬 [阶段 2/2] 自动弹幕亲密度已关闭。", file=sys.stderr)
        elif not self.is_lighted:
            print("    💬 [阶段 2/2] 粉丝牌尚未确认点亮，留待下次巡检", file=sys.stderr)
        elif self.progress is None:
            print("    💬 [阶段 2/2] 无法获取每日亲密度弹幕任务进度，留待下次巡检", file=sys.stderr)
        elif self.progress["done"]:
            print(
                f"    💬 [阶段 2/2] 今日发弹幕亲密度任务已完成（{self.progress['current']}/{self.progress['limit']}），跳过。",
                file=sys.stderr,
            )
        else:
            needed = self.progress["limit"] - self.progress["current"]
            print(
                f"    💬 [阶段 2/2] 勋章已就绪，发送 {needed} 条弹幕完成每日亲密度任务...",
                file=sys.stderr,
            )
            self.intimacy_sent, self.used_msgs, tries = self.gateway.send_danmaku_batch(
                self.room_id,
                needed,
                self.sessdata,
                self.bili_jct,
                used_pool=self.used_msgs,
                max_attempts=self.remaining_attempts(),
                deadline=self.deadline,
                **self.batch_options,
            )
            self.attempted += tries
            print(f"    💬 亲密度弹幕接口成功：{self.intimacy_sent}/{needed} 条", file=sys.stderr)

    def finish(self):
        total_sent = self.light_sent + self.intimacy_sent
        if total_sent:
            refreshed = self.gateway.get_fans_club_task_info(
                self.room_id, self.anchor_uid, self.sessdata, self.bili_jct
            )
            if refreshed:
                self.is_lighted = bool(refreshed.get("is_lighted", self.is_lighted))
                self.progress = self.gateway._danmaku_task_progress(refreshed) or self.progress
        light_done = not self.auto_revive or bool(self.is_lighted)
        intimacy_done = not self.auto_intimacy or bool(
            self.is_lighted and self.progress and self.progress.get("done")
        )
        is_done = light_done and intimacy_done
        current_str = str(self.progress["current"]) if self.progress else "?"
        limit_str = str(self.progress["limit"]) if self.progress else "?"
        print(
            f"    💬 弹幕接口成功：点亮 {self.light_sent} 条 + 亲密度 {self.intimacy_sent} 条；任务进度 {current_str}/{limit_str}{('（待后续确认）' if not is_done else '')}",
            file=sys.stderr,
        )
        self.gateway._log(
            {
                "type": "danmaku_tasks",
                "room_id": self.room_id,
                "light_sent": self.light_sent,
                "intimacy_sent": self.intimacy_sent,
                "total_sent": total_sent,
                "attempted": self.attempted,
                "task_progress_before": self.progress_before,
                "task_progress": f"{current_str}/{limit_str}",
                "done": is_done,
                "light_done": light_done,
                "intimacy_done": intimacy_done,
            }
        )
        return {
            "light_sent": self.light_sent,
            "intimacy_sent": self.intimacy_sent,
            "total_sent": total_sent,
            "attempted": self.attempted,
            "done": is_done,
            "progress": f"{current_str}/{limit_str}",
            "light_done": light_done,
            "intimacy_done": intimacy_done,
        }

    def remaining_attempts(self) -> Optional[int]:
        return None if self.max_attempts is None else max(0, self.max_attempts - self.attempted)
