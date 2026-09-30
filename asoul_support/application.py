"""Shared application entry for CLI adapters, desktop workers and manual actions."""

from pathlib import Path
import time
from . import heartbeat as live
from .check_auth import check_login
from .context import RuntimeContext, use_context
from .runtime import data_dir, read_json, task_day, update_json
from .members import validate_members
from .launch import watch_arguments
from . import safety


class AppContext:

    def __init__(self, root=None, *, observer=None, notify=None, gateway=live):
        self.root = Path(root) if root is not None else data_dir()
        self.runtime = RuntimeContext(self.root, observer, notify)
        self.gateway = gateway

    def call(self, method, *args, **kwargs):
        with use_context(self.runtime):
            return getattr(self.gateway, method)(*args, **kwargs)

    def credentials(self):
        saved = read_json(self.root / "credentials.json", {})
        if not saved.get("SESSDATA") or not saved.get("bili_jct"):
            raise ValueError("尚未配置登录凭证，请打开登录设置")
        return (saved["SESSDATA"], saved["bili_jct"])

    def run_watch(self, member, policy):
        return self.call("main", watch_arguments(member, policy)) or 0

    def redo(self, room, uid, task_type="all"):
        return self.call("redo_member_tasks", room, uid, *self.credentials(), task_type)

    def resolve(self, query):
        saved = read_json(self.root / "credentials.json", {})
        return self.call(
            "resolve_anchor_info", query, saved.get("SESSDATA", ""), saved.get("bili_jct", "")
        )

    def validate_credentials(self, sessdata, bili_jct):
        from .credentials import parse_login_import
        import json

        try:
            parse_login_import(json.dumps({"SESSDATA": sessdata, "bili_jct": bili_jct}))
        except ValueError:
            return False, "凭证格式不正确，请重新扫码或检查输入"
        with use_context(self.runtime):
            return check_login(sessdata, bili_jct)

    def safety_status(self):
        try:
            saved = read_json(self.root / "credentials.json", {})
        except RuntimeError:
            return {
                "blocked": True,
                "kind": "credentials",
                "reason": "凭证无法解密，请重新扫码登录",
            }
        return safety.status(saved.get("SESSDATA"), self.root)

    def resume_safety(self, confirmed=False):
        credentials = self.credentials()
        hold = self.safety_status()
        if hold.get("until") or hold.get("kind") == "auth":
            return safety.resume(credentials[0], confirmed=confirmed, root=self.root)
        if not confirmed:
            return False, "请先在平台处理异常并确认"
        ok, message = self.validate_credentials(*credentials)
        if not ok:
            return False, "登录或平台验证未通过，保护暂停保留"
        return safety.resume(credentials[0], confirmed=True, root=self.root)

    def add_members(self, additions):
        additions = [{key: member[key] for key in ("name", "uid", "room")} for member in additions]

        def change(saved):
            members = list(saved or [])
            existing = {m["room"] for m in members}
            for member in additions:
                if member["room"] not in existing:
                    members.append(member)
                    existing.add(member["room"])
            return validate_members(members)

        return update_json(self.root / "members.json", change, [])

    def remove_member(self, room):
        return update_json(
            self.root / "members.json",
            lambda members: [m for m in members if m["room"] != room],
            [],
        )

    def medals(self):
        return self.call("get_all_user_medals", *self.credentials())

    def wear(self, uid):
        credentials = self.credentials()
        medals = self.call("get_my_medals", *credentials)
        info = medals.get(uid) or medals.get(str(uid))
        if not info or not info.get("medal_id"):
            return "no_medal"
        return "ok" if self.call("wear_medal", info["medal_id"], *credentials) else "fail"

    def probe(self, members):
        credentials = self.credentials()
        hold = self.safety_status()
        if hold["blocked"]:
            return {"error": hold["reason"], "safety": hold}
        valid, message = self.validate_credentials(*credentials)
        if not valid:
            return {
                "error": f"登录验证失败：{message}",
                "auth_invalid": not message.startswith("认证接口请求失败"),
            }
        statuses = self.call("check_live_status", [m["room"] for m in members], *credentials)
        medals = self.call("get_my_medals", *credentials)
        tasks, errors = self._query_tasks(members, credentials)
        missing = [m["name"] for m in members if m["room"] not in statuses]
        result = {
            "statuses": statuses,
            "account": message,
            "medals": medals,
            "tasks": tasks,
            "task_errors": errors,
            "observed": time.time(),
            "warning": "无法查询：" + "、".join(missing) if missing else "",
        }
        self.call(
            "_log",
            {
                "type": "check",
                "source": "desktop",
                "live": [
                    {"name": m["name"], "title": statuses[m["room"]].get("title", "")}
                    for m in members
                    if statuses.get(m["room"], {}).get("live_status") == 1
                ],
                "offline": [
                    m["name"]
                    for m in members
                    if statuses.get(m["room"], {}).get("live_status") in (0, 2)
                ],
                "unknown": missing,
            },
        )
        return result

    def _query_tasks(self, members, credentials):
        tasks, errors = ({}, {})
        for member in members:
            club = self.call("get_fans_club_task_info", member["room"], member["uid"], *credentials)
            if not club:
                errors[str(member["room"])] = "任务进度查询失败"
                continue
            tasks[str(member["room"])] = {
                "tasks": club.get("task_info", []),
                "intimacy": club.get("intimacy", 0),
                "next_intimacy": club.get("next_intimacy", 0),
                "task_light_days": club.get("task_light_days", 0),
                "is_lighted": club.get("is_lighted", False),
                "updated": time.time(),
                "day": task_day(),
            }
        return (tasks, errors)
