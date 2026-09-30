"""Persistent account safety holds and shared per-room budgets at the IO boundary."""

import time
from urllib.parse import urlsplit, parse_qs
from .runtime import (
    data_dir,
    read_json,
    write_json,
    update_json,
    FileLock,
    session_fingerprint,
    task_day,
)
from .policies import DANMAKU_SESSION_ATTEMPT_LIMIT, LIVE_LIKE_BATCHES

RATE_COOLDOWN = 300
NETWORK_COOLDOWN = 60
READ_POST_PATHS = {"/room/v1/Room/get_status_info_by_uids"}


def _root(root=None):
    return root if root is not None else data_dir()


def identity(sessdata, root=None):
    root = _root(root)
    fingerprint = session_fingerprint(sessdata)
    return read_json(root / "state/account-bindings.json", {}).get(fingerprint, fingerprint)


def _path(key, root=None):
    return _root(root) / "state" / "safety" / f"{key}.json"


def status(sessdata, root=None):
    if not sessdata:
        return {"blocked": False}
    value = read_json(_path(identity(sessdata, root), root), {})
    hold = value.get("hold") or {}
    if hold.get("until") and time.time() >= hold["until"]:
        return {"blocked": False}
    return {"blocked": bool(hold), **hold}


def blocked_response(hold):
    return {
        "code": hold.get("code", -1),
        "message": hold.get("reason", "账号保护暂停"),
        "error_kind": "safety",
        "safety": hold,
        "success": False,
    }


def bind_account(sessdata, uid, root=None):
    """Only a successful authenticated nav response can establish a UID binding."""
    key = f"uid-{int(uid)}"
    fingerprint = session_fingerprint(sessdata)
    root = _root(root)
    path = root / "state/account-bindings.json"
    with FileLock(str(path) + ".guard", timeout=5) as lock:
        if not lock.acquired:
            raise TimeoutError("账号身份写入超时")
        values = read_json(path, {})
        if values.get(fingerprint) != key:
            _migrate_session_state(root, fingerprint, key)
            values[fingerprint] = key
            write_json(path, values)
    # Authentication resolves only an expired-login hold, never a risk/permission hold.
    update_json(
        _path(key, root),
        lambda v: {**v, "hold": {}} if (v.get("hold") or {}).get("kind") == "auth" else v,
        {},
    )
    return key


def _migrate_session_state(root, old, new):
    source = _path(old, root)
    if source.exists():
        previous = read_json(source, {})

        def merge_safety(current):
            for name, count in previous.get("counts", {}).items():
                current.setdefault("counts", {})[name] = (
                    current.get("counts", {}).get(name, 0) + count
                )
            if previous.get("hold"):
                current["hold"] = previous["hold"]
            return current

        update_json(_path(new, root), merge_safety, {})
        source.unlink()
    # Upgrade existing daily runner files once, preserving attempts across QR replacement.
    folder = root / "state/tasks"
    for source in folder.glob(f"{old}-*.json"):
        previous = read_json(source, {})
        room = previous.get("room")
        if not isinstance(room, int):
            continue
        destination = folder / f"{new}-{room}.json"
        with FileLock(root / "locks" / f"tasks-{new}-{room}.lock", timeout=5) as lease:
            if not lease.acquired:
                raise TimeoutError("任务预算迁移等待超时")
            current = read_json(destination, {})
            if current.get("day") == previous.get("day"):
                for field in ("attempted", "like_attempted"):
                    current[field] = current.get(field, 0) + previous.get(field, 0)
            elif current.get("day", "") < previous.get("day", ""):
                current = previous
            current["account_key"] = new
            write_json(destination, current)

            def carry_budget(value):
                counts = value.setdefault("counts", {})
                prefix = f"{current.get('day')}:{room}:"
                for kind, amount in (
                    ("danmaku", current.get("attempted", 0)),
                    ("like", current.get("like_attempted", 0) * LIVE_LIKE_BATCHES),
                ):
                    counts[prefix + kind] = max(counts.get(prefix + kind, 0), amount)
                return value

            update_json(_path(new, root), carry_budget, {})
            source.unlink()


def classify(response):
    code = response.get("code")
    message = str(response.get("message", ""))
    if response.get("error_kind") == "network":
        return "network", "网络连续失败，暂缓请求", NETWORK_COOLDOWN
    if code in (401, -101, -111) or "未登录" in message or "登录失效" in message:
        return "auth", "登录已失效，请重新扫码登录", None
    if code in (429, -509) or any(
        word in message
        for word in (
            "过于频繁",
            "发言频繁",
            "请求频繁",
            "频率过高",
            "频率限制",
            "请求过快",
            "发言过快",
        )
    ):
        return "rate", "收到频率限制，账号操作已冷却", RATE_COOLDOWN
    if code in (403, -403) or any(word in message for word in ("禁言", "权限不足", "封禁")):
        return "permission", "收到权限或禁言限制，请先在平台确认账号状态", None
    if code in (412, -412, -352) or any(word in message for word in ("验证码", "安全验证", "风控")):
        return "review", "收到验证或异常拒绝，请在平台检查后手动恢复", None
    return None


def hold_account(sessdata, kind, reason, *, code=-1, seconds=None, operation=None):
    now = time.time()
    hold = {
        "kind": kind,
        "reason": reason,
        "code": code,
        "since": now,
        "until": now + seconds if seconds else None,
        "operation": operation or {},
    }

    def change(current):
        previous = current.get("hold") or {}
        permanent = previous and not previous.get("until")
        if not permanent or kind in ("review", "permission"):
            current["hold"] = hold
        return current

    return update_json(_path(identity(sessdata)), change, {}).get("hold", hold)


def operation(url, data, method):
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)
    if isinstance(data, bytes):
        params.update(parse_qs(data.decode("utf-8", errors="replace")))
    room = next((params[name][0] for name in ("roomid", "room_id") if params.get(name)), "")
    kind = (
        "danmaku"
        if parsed.path == "/msg/send"
        else ("like" if parsed.path.endswith("/likeReportV3") else "other")
    )
    return {"path": parsed.path, "room": room, "kind": kind, "method": method}


def reserve(sessdata, op):
    """Reserve before IO so uncertain outcomes and process crashes consume budget."""
    key = identity(sessdata)
    if not key.startswith("uid-"):
        return blocked_response({"reason": "无法认证账号身份，本次跳过操作", "kind": "auth"})
    hold = status(sessdata)
    if hold["blocked"]:
        return blocked_response(hold)
    if op["kind"] not in ("danmaku", "like"):
        return None
    counter = f"{task_day()}:{op['room']}:{op['kind']}"
    limit = DANMAKU_SESSION_ATTEMPT_LIMIT if op["kind"] == "danmaku" else LIVE_LIKE_BATCHES * 3
    allowed = [False]

    def change(current):
        counts = {
            name: n
            for name, n in current.get("counts", {}).items()
            if name.startswith(task_day() + ":")
        }
        count = counts.get(counter, 0)
        if count < limit and not status(sessdata)["blocked"]:
            counts[counter] = count + 1
            allowed[0] = True
        current["counts"] = counts
        return current

    update_json(_path(key), change, {})
    if not allowed[0]:
        return blocked_response({"kind": "budget", "reason": "今日该房间操作尝试已达上限"})
    return None


def observe(sessdata, url, response, *, mutation=False, op=None):
    path = urlsplit(url).path
    data = response.get("data") or {}
    if path == "/x/web-interface/nav" and response.get("code") == 0:
        if isinstance(data, dict) and data.get("isLogin") is True:
            uid = data.get("mid")
            if str(uid).isdigit() and int(uid) > 0:
                bind_account(sessdata, uid)
        elif isinstance(data, dict) and data.get("isLogin") is False:
            hold_account(sessdata, "auth", "登录已失效，请重新扫码登录", code=-101)
    decision = classify(response)
    if mutation and (
        response.get("error_kind") in ("network", "data")
        or (
            response.get("error_kind") == "http"
            and (response.get("code", 0) >= 500 or response.get("code") == 408)
        )
    ):
        hold_account(
            sessdata, "uncertain", "操作结果未知，已停止重复发送；请核对服务端进度", operation=op
        )
    elif decision:
        kind, reason, delay = decision
        if kind == "rate" and response.get("retry_after"):
            delay = max(delay, response["retry_after"])
        hold_account(sessdata, kind, reason, code=response.get("code"), seconds=delay)


def resume(sessdata, *, confirmed=False, root=None):
    """Explicit local acknowledgement; auth expiry can only be cleared by authentication."""
    hold = status(sessdata, root)
    if hold.get("kind") == "auth" and hold["blocked"]:
        return False, "请先重新扫码登录"
    if hold["blocked"] and hold.get("until"):
        return False, "冷却期间不提前恢复，请等待冷却结束"
    if hold["blocked"] and not confirmed:
        return False, "请先在平台处理异常或核对任务结果，再确认恢复"
    update_json(_path(identity(sessdata, root), root), lambda v: {**v, "hold": {}}, {})
    return True, "账号保护暂停已解除；当天预算保留"
