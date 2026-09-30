"""Process adapters. Desktop and CLI invoke the same application services."""

import os
import time
from asoul_support.application import AppContext
from desktop.storage import load_config, write_json
from desktop.windows import Mutex, instance_name


def prepare(root, members=None):
    """Compatibility constructor; never mutates a module or command arguments."""
    return AppContext(root)


def probe(root, output):
    try:
        _, members = load_config(root)
        result = prepare(root).probe(members)
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"error": f"检查失败（{type(exc).__name__}），请检查配置和网络。"}
        if isinstance(exc, ValueError) and "登录凭证" in str(exc):
            result["auth_invalid"] = True
    write_json(output, result)
    return 1 if result.get("error") else 0


class RoomStateRecorder:

    def __init__(self, path, member):
        self.path = path
        self.state = {
            "room": member["room"],
            "name": member["name"],
            "phase": "正在连接",
            "beats": 0,
            "pid": os.getpid(),
            "started": time.time(),
        }
        self.save()

    def save(self):
        self.state["updated"] = time.time()
        write_json(self.path, self.state)

    def __call__(self, event):
        kind = event.get("type")
        if kind == "x25kn_x_success":
            self.state.update(
                phase="挂机中",
                beats=self.state["beats"] + 1,
                last_heartbeat=time.time(),
                interval=event.get("interval", 60),
                error="",
            )
        elif kind in {"x25kn_e_error", "x25kn_x_error", "auth_error", "watch_exception"}:
            self.state.update(
                phase="正在重试",
                error=str(event.get("message", event.get("error", "请求失败")))[:180],
            )
        elif kind == "watch_start":
            self.state.update(
                session_id=event.get("session_id"),
                account_key=event.get("account_key"),
                started=time.time(),
            )
        elif kind == "watch_end":
            self.state.update(phase="本轮结束", result=event)
        elif kind == "task_check":
            self.state.update(task_result=event, task_updated=time.time())
        self.save()

    def finish(self, code):
        from asoul_support.runtime import read_json
        from asoul_support import safety

        saved = read_json(self.path.parent.parent / "credentials.json", {})
        hold = safety.status(saved.get("SESSDATA"), self.path.parent.parent)
        if hold.get("blocked"):
            self.state.update(phase="账号保护暂停", error=hold["reason"], safety=hold)
            self.save()
            return
        if code:
            self.state.update(phase="运行失败", error="本轮挂机未成功完成，请查看日志")
        else:
            self.state["phase"] = "本轮结束" if self.state["beats"] else "本轮结束（暂无成功心跳）"
        self.save()


def watch(root, room, skip_actions=False):
    config, members = load_config(root)
    member = next((m for m in members if m["room"] == room))
    mutex = Mutex(instance_name(root) + f"-room-{room}")
    if not mutex.acquired:
        mutex.close()
        return 0
    recorder = RoomStateRecorder(root / "state" / f"{room}.json", member)
    code = 1
    try:
        code = AppContext(root, observer=recorder).run_watch(member, config)
        return code
    except Exception as exc:
        recorder.state.update(phase="运行失败", error=type(exc).__name__)
        return 1
    finally:
        recorder.finish(code)
        mutex.close()
