import time
from asoul_support.runtime import data_dir, read_json, write_json, migrate_credentials
from asoul_support.members import load_members


def load_config(root):
    config = read_json(root / "settings.json")
    if not isinstance(config, dict):
        raise ValueError("设置文件必须是 JSON 对象")
    interval = config.get("check_minutes", 30)
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or (not 1 <= interval <= 1440)
    ):
        raise ValueError("检查间隔应为 1–1440 分钟")
    config.setdefault("auto_revive", config.get("danmaku", True))
    config.setdefault("auto_danmaku_intimacy", config.get("danmaku", True))
    config.setdefault("auto_like", config.get("live_likes", False))
    config.setdefault("notify_on_live", True)
    config.setdefault("autostart", False)
    for key in ("auto_revive", "auto_danmaku_intimacy", "auto_like", "notify_on_live", "paused"):
        if key in config and type(config[key]) is not bool:
            raise ValueError(f"{key} 必须为 true 或 false")
    config.pop("danmaku", None)
    config.pop("live_likes", None)
    members = load_members(root)
    return (config, members)


def initialize(root, defaults):
    for sub in ("logs", "state", "locks", "commands"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    if not (root / "settings.json").exists():
        write_json(
            root / "settings.json",
            {
                "check_minutes": 30,
                "auto_revive": True,
                "auto_danmaku_intimacy": True,
                "auto_like": False,
                "notify_on_live": True,
                "autostart": False,
                "paused": False,
            },
        )
    if not (root / "members.json").exists():
        write_json(root / "members.json", defaults)
    if root == data_dir():
        try:
            migrate_credentials(root)
        except RuntimeError:
            # Keep the UI available for verified QR replacement of unreadable credentials.
            pass


def read_status(root, max_age=15):
    """A saved snapshot is not evidence that the desktop is still running."""
    from asoul_support.process_lock import is_process_running

    try:
        state = read_json(root / "status.json", {})
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {"error": "运行快照无法读取，请重新检查"}
    updated = state.get("updated", 0)
    fresh = (
        not state.get("exited")
        and isinstance(updated, (int, float))
        and (0 <= time.time() - updated <= max_age)
        and (type(state.get("pid")) is int)
        and is_process_running(state["pid"])
    )
    if not fresh:
        state = {**state, "stale": True, "running": False}
        state["rows"] = [
            {
                **row,
                "active": False,
                "live_status": None,
                "phase": "状态已过期",
                "status_stale": True,
                "tasks_stale": True,
            }
            for row in state.get("rows", [])
        ]
    else:
        state.update(stale=False, running=True)
    return state


def send_command(root, command):
    if command not in {"pause", "resume", "check", "show", "exit", "login"}:
        raise ValueError("未知命令")
    write_json(
        root / "commands" / f"{time.time_ns()}.json", {"command": command, "created": time.time()}
    )
