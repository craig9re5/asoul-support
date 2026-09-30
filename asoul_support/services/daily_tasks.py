import time
import uuid
from typing import Dict
from ..policies import *
from .. import safety


def redo_member_tasks(
    room_id: int, anchor_uid: int, sessdata: str, bili_jct: str, task_type: str = "all", *, _gateway
) -> Dict:
    """手动执行/补齐主播的任务（danmaku / like / all）"""
    if task_type not in ("all", "danmaku", "like"):
        return {"success": False, "error": "未知任务类型"}
    runner = _gateway.DailyTaskRunner(
        room_id,
        anchor_uid,
        sessdata,
        bili_jct,
        auto_revive=task_type != "like",
        auto_intimacy=task_type != "like",
        auto_like=task_type != "danmaku",
    )
    token = _gateway.EVENT_CONTEXT.set(
        {
            "action_id": str(uuid.uuid4()),
            "room_id": room_id,
            "account_key": _gateway.account_key(sessdata),
            "source": "manual",
        }
    )
    try:
        return runner.check()
    finally:
        _gateway.EVENT_CONTEXT.reset(token)


class DailyTaskRunner:
    """Confirm backend progress on restart, with an account/room/day send budget."""

    def __init__(
        self,
        room,
        uid,
        sessdata,
        bili_jct,
        *,
        auto_revive=True,
        auto_intimacy=True,
        auto_like=False,
        messages=None,
        delay=0,
        requested_count=None,
        like_batches=None,
        _gateway,
    ):
        self.gateway = _gateway
        self.requested_count, self.like_batches = requested_count, like_batches
        self.batch_options = {"messages": messages, "delay": delay} if messages is not None else {}
        self.room, self.uid = (room, uid)
        self.sessdata, self.bili_jct = (sessdata, bili_jct)
        self.auto_revive, self.auto_intimacy, self.auto_like = (
            auto_revive,
            auto_intimacy,
            auto_like,
        )
        self.root = self.gateway._runtime_path("_TASK_STATE_DIR").parent.parent
        self.key = safety.identity(sessdata, self.root)
        self.path = self.gateway._runtime_path("_TASK_STATE_DIR") / f"{self.key}-{room}.json"
        self.day = None
        self.danmaku_done = self.like_done = False

    def check(self):
        hold = safety.status(self.sessdata, self.root)
        if hold["blocked"]:
            return {"success": False, "error": hold["reason"], "safety": hold}
        if not self.key.startswith("uid-"):
            uid = self.gateway.get_viewer_uid(self.sessdata, self.bili_jct)
            if uid is None:
                return {"success": False, "error": "无法认证账号身份，本次跳过任务"}
            self.key = safety.bind_account(self.sessdata, uid, self.root)
            self.path = (
                self.gateway._runtime_path("_TASK_STATE_DIR") / f"{self.key}-{self.room}.json"
            )
        day = self.gateway.task_day()
        if day != self.day:
            self.day = day
            self.danmaku_done = self.like_done = False
        output = {"danmaku": None, "like": None, "success": True, "day": day}
        with self.gateway.FileLock(
            self.gateway._runtime_path("_LOCK_DIR") / f"tasks-{self.key}-{self.room}.lock"
        ) as lock:
            if not lock.acquired:
                return {**output, "success": False, "error": "该直播间任务正在执行，请稍后检查"}
            saved = self.gateway.read_json(self.path, {})
            if saved.get("day") != day:
                saved = {
                    "day": day,
                    "account_key": self.key,
                    "room": self.room,
                    "attempted": 0,
                    "like_attempted": 0,
                }
            if self.auto_like:
                self._refresh_like_context(saved, output)
            if (self.auto_revive or self.auto_intimacy) and (not self.danmaku_done):
                self._check_danmaku(saved, output)
            if self.auto_like and (not self.like_done):
                hold = safety.status(self.sessdata, self.root)
                if hold["blocked"]:
                    output.update(success=False, error=hold["reason"], safety=hold)
                else:
                    self._check_like(saved, output)
            saved.update(
                danmaku_done=self.danmaku_done, like_done=self.like_done, updated=time.time()
            )
            self.gateway.write_json(self.path, saved)
            hold = safety.status(self.sessdata, self.root)
            if hold["blocked"]:
                output.update(success=False, error=hold["reason"], safety=hold)
        self.gateway._log({"type": "task_check", "room_id": self.room, "day": day, **output})
        return output

    def _refresh_like_context(self, saved, output):
        # Login context changes do not restore a UID's daily attempt allowance.
        saved.pop("like_context", None)

    def _check_danmaku(self, saved, output):
        used = saved.get("attempted", 0)
        allowance = min(
            self.gateway.DANMAKU_ATTEMPTS_PER_CHECK,
            max(0, self.gateway.DANMAKU_SESSION_ATTEMPT_LIMIT - used),
        )
        if self.requested_count is not None:
            allowance = min(allowance, self.requested_count)
        saved["attempted"] = used + allowance
        self.gateway.write_json(self.path, saved)
        try:
            result = self.gateway.send_medal_danmaku_tasks(
                self.room,
                self.uid,
                self.sessdata,
                self.bili_jct,
                auto_revive=self.auto_revive,
                auto_intimacy=self.auto_intimacy,
                max_attempts=allowance,
                deadline=time.monotonic() + self.gateway.DANMAKU_WORK_BUDGET,
                **self.batch_options,
            )
            saved["attempted"] = used + result.get("attempted", 0)
            self.danmaku_done = bool(result.get("done"))
            if not self.danmaku_done and (not result.get("error")):
                result["error"] = (
                    "今日发送尝试已达上限，任务尚未确认完成"
                    if saved["attempted"] >= self.gateway.DANMAKU_SESSION_ATTEMPT_LIMIT
                    else "任务尚未确认完成，留待下次巡检"
                )
        except Exception as exc:
            result = {"done": False, "error": f"任务执行失败（{type(exc).__name__}）"}
        output["danmaku"] = result
        output["success"] = output["success"] and self.danmaku_done

    def _check_like(self, saved, output):
        if saved.get("like_attempted", 0) >= 3:
            result = {"success": False, "error": "今日点赞尝试已达上限"}
        else:
            saved["like_attempted"] = saved.get("like_attempted", 0) + 1
            self.gateway.write_json(self.path, saved)
            try:
                result = self.gateway.like_live_room(
                    self.room,
                    self.uid,
                    self.sessdata,
                    self.bili_jct,
                    **({"batches": self.like_batches} if self.like_batches is not None else {}),
                )
            except Exception as exc:
                result = {"success": False, "error": f"任务执行失败（{type(exc).__name__}）"}
            self.like_done = bool(result.get("success") and result.get("done", True))
        output["like"] = result
        output["success"] = output["success"] and self.like_done
        self.gateway._log({"type": "live_like", "room_id": self.room, **result})
