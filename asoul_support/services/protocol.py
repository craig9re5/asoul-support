import hashlib
import json
import random
import string
import sys
import time
from typing import Optional, Dict, List
from ..policies import *


def _random_string(length: int, *, _gateway) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _now_ms(*, _gateway) -> int:
    return int(time.time() * 1000)


def _wait_for_heartbeat_window(last_response_at: float, interval: int, *, _gateway) -> float:
    """Wait only for the unspent part of the server heartbeat interval."""
    wait_seconds = interval - (time.monotonic() - last_response_at)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
        return wait_seconds
    return 0.0


def _x25kn_sign(payload_json: str, rules: List[int], secret_key: str, *, _gateway) -> str:
    """按 secret_rule 用 secret_key 做 HMAC 链式签名"""
    import hmac

    result = payload_json
    key_bytes = secret_key.encode("utf-8")
    for r in rules:
        if 0 <= r < len(_gateway._X25KN_HMAC_FUNCS):
            mac = hmac.new(
                key_bytes, result.encode("utf-8"), getattr(hashlib, _gateway._X25KN_HMAC_FUNCS[r])
            )
            result = mac.hexdigest()
    return result


def x25kn_enter_room(
    room_id: int,
    parent_id: int,
    area_id: int,
    up_id: int,
    buvid: str,
    uuid_str: str,
    sessdata: str,
    bili_jct: str,
    *,
    _gateway,
) -> Optional[Dict]:
    """E：进入房间，返回 {timestamp, secret_key, secret_rule, heartbeat_interval} 或 None"""
    ts = _gateway._now_ms()
    form = {
        "id": json.dumps([parent_id, area_id, 0, room_id], separators=(",", ":")),
        "device": json.dumps([buvid, uuid_str], separators=(",", ":")),
        "ts": ts,
        "is_patch": 0,
        "heart_beat": "[]",
        "ua": _gateway._X25KN_UA,
        "csrf_token": bili_jct,
        "csrf": bili_jct,
        "visit_id": "",
        "ruid": up_id,
    }
    resp = _gateway._x25kn_post(
        _gateway._X25KN_E_URL, form, sessdata, bili_jct, f"https://live.bilibili.com/{room_id}"
    )
    if resp and resp.get("code") == 0 and resp.get("data"):
        return resp["data"]
    code = (resp or {}).get("code", "?")
    msg = (resp or {}).get("message", str(resp))
    print(f"    ⚠️  E 心跳失败: [{code}] {msg}", file=sys.stderr)
    _gateway._log({"type": "x25kn_e_error", "room_id": room_id, "code": code, "message": msg})
    return None


def x25kn_heartbeat(
    room_id: int,
    parent_id: int,
    area_id: int,
    up_id: int,
    seq: int,
    buvid: str,
    uuid_str: str,
    ets: int,
    secret_key: str,
    secret_rule: List[int],
    heartbeat_interval: int,
    sessdata: str,
    bili_jct: str,
    *,
    _gateway,
) -> Optional[Dict]:
    """X：心跳，返回 {timestamp, secret_key, secret_rule, heartbeat_interval} 或 None"""
    ts = _gateway._now_ms()
    sign_payload = {
        "platform": "web",
        "parent_id": parent_id,
        "area_id": area_id,
        "seq_id": seq,
        "room_id": room_id,
        "buvid": buvid,
        "uuid": uuid_str,
        "ets": ets,
        "time": heartbeat_interval,
        "ts": ts,
    }
    sign_input = json.dumps(sign_payload, separators=(",", ":"))
    s = _gateway._x25kn_sign(sign_input, secret_rule, secret_key)
    form = {
        "s": s,
        "id": json.dumps([parent_id, area_id, seq, room_id], separators=(",", ":")),
        "device": json.dumps([buvid, uuid_str], separators=(",", ":")),
        "ruid": up_id,
        "ets": ets,
        "benchmark": secret_key,
        "time": heartbeat_interval,
        "ts": ts,
        "ua": _gateway._X25KN_UA,
        "csrf_token": bili_jct,
        "csrf": bili_jct,
        "visit_id": "",
    }
    resp = _gateway._x25kn_post(
        _gateway._X25KN_X_URL, form, sessdata, bili_jct, f"https://live.bilibili.com/{room_id}"
    )
    if resp and resp.get("code") == 0 and resp.get("data"):
        return resp["data"]
    code = (resp or {}).get("code", "?")
    msg = (resp or {}).get("message", str(resp))
    print(f"    ⚠️  X 心跳失败: [{code}] {msg}", file=sys.stderr)
    _gateway._log(
        {"type": "x25kn_x_error", "room_id": room_id, "seq": seq, "code": code, "message": msg}
    )
    return None
