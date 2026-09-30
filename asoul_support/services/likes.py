import re
import time
import urllib.parse
from typing import Optional, Dict
from ..policies import *
from .. import safety


def get_live_like_progress(
    room_id: int, anchor_uid: int, headers: dict, bili_jct: str, *, _gateway
) -> Dict:
    """Read the like task's current rounds and required likes per round."""
    params = {
        "csrf": bili_jct,
        "platform": "pc",
        "room_id": str(room_id),
        "scene": "club",
        "target_id": str(anchor_uid),
        "web_location": "444.260",
    }
    url = (
        "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/GetActivatedMedalInfo?"
        + urllib.parse.urlencode(params)
    )
    response = _gateway._get_json(url, headers)
    if not response or response.get("code") != 0:
        code = response.get("code") if response else None
        return {"error": f"无法读取点赞任务进度（接口代码：{code}）"}
    data = response.get("data") or {}
    if not isinstance(data, dict):
        return {"error": "粉丝团任务数据格式异常"}
    tasks = data.get("task_info") or []
    if not isinstance(tasks, list):
        return {"error": "粉丝团任务列表格式异常"}
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("jump_type") == "like"), None
    )
    if not task:
        return {"error": "粉丝团信息中没有点赞任务"}
    progress = re.search("(\\d+)\\s*/\\s*(\\d+)", task.get("sub_title") or "")
    count = re.search("\\d+", task.get("title") or "")
    if not progress:
        return {"error": "无法解析点赞任务进度"}
    current, limit = map(int, progress.groups())
    if limit < 1 or current > limit:
        return {"error": "点赞任务进度异常"}
    per_round = int(count.group()) if count else _gateway.LIVE_LIKE_BATCH_SIZE
    if per_round < 1:
        return {"error": "点赞任务次数异常"}
    return {
        "current": current,
        "limit": limit,
        "per_round": per_round,
        "done": bool(task.get("is_done")),
    }


def report_live_likes(
    room_id: int,
    anchor_uid: int,
    viewer_uid: int,
    sessdata: str,
    bili_jct: str,
    count: int = LIVE_LIKE_BATCH_SIZE,
    headers: Optional[dict] = None,
    *,
    _gateway,
) -> Dict:
    """Report a small batch of live-room likes; this does not like a video."""
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= LIVE_LIKE_BATCH_SIZE
    ):
        return {"success": False, "code": None, "message": "点赞批次次数必须为 1–30"}
    params = {
        "click_time": str(count),
        "room_id": str(room_id),
        "uid": str(viewer_uid),
        "anchor_id": str(anchor_uid),
        "web_location": "444.8",
        "csrf": bili_jct,
    }
    try:
        signed = _gateway._sign_wbi(params, _gateway.get_mixin_key(sessdata, bili_jct))
    except Exception:
        return {"success": False, "code": None, "message": "无法生成 WBI 签名"}
    url = (
        "https://api.live.bilibili.com/xlive/app-ucenter/v1/like_info_v3/like/likeReportV3?"
        + urllib.parse.urlencode(signed)
    )
    headers = headers or _gateway._live_like_headers(room_id, viewer_uid, sessdata, bili_jct)
    if not headers:
        return {
            "success": False,
            "code": None,
            "message": "缺少匹配当前账号的登录会话；请在桌面重新扫码登录",
        }
    resp = _gateway._post_empty_json(url, headers)
    return {
        "success": bool(resp and resp.get("code") == 0),
        "code": (resp or {}).get("code"),
        "message": (resp or {}).get("message", "请求失败"),
    }


def like_live_room(
    room_id: int,
    anchor_uid: int,
    sessdata: str,
    bili_jct: str,
    batches: int = LIVE_LIKE_BATCHES,
    *,
    _gateway,
) -> Dict:
    """Report only the remaining task rounds and verify each update."""
    viewer_uid = _gateway.get_viewer_uid(sessdata, bili_jct)
    if viewer_uid is None:
        return {"success": False, "reported": 0, "error": "无法获取当前账号 UID"}
    headers = _gateway._live_like_headers(room_id, viewer_uid, sessdata, bili_jct)
    if not headers:
        return {
            "success": False,
            "reported": 0,
            "error": "缺少匹配当前账号的登录会话；请在桌面重新扫码登录",
        }
    progress = _gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
    if "error" in progress:
        return {"success": False, "reported": 0, "error": progress["error"]}
    start = progress["current"]
    target = min(progress["limit"], start + batches)
    if progress["done"] or start >= target:
        return {"success": True, "reported": 0, "progress": f"{start}/{progress['limit']}"}
    reported = 0
    for i in range(batches):
        if progress["done"] or progress["current"] >= target:
            break
        if i:
            time.sleep(_gateway.LIVE_LIKE_DELAY)
        result = _gateway.report_live_likes(
            room_id,
            anchor_uid,
            viewer_uid,
            sessdata,
            bili_jct,
            count=progress["per_round"],
            headers=headers,
        )
        if not result["success"]:
            hold = safety.status(sessdata)
            if hold.get("kind") == "uncertain":
                # Reads are permitted while writes remain held. A timeout is not
                # evidence of rejection, so never replay this batch automatically.
                time.sleep(_gateway.LIVE_LIKE_PROGRESS_DELAY)
                observed = _gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
                progress_text = (
                    f"{observed['current']}/{observed['limit']}"
                    if "error" not in observed
                    else "查询失败"
                )
                return {
                    "success": False,
                    "reported": reported,
                    "progress": progress_text,
                    "needs_confirmation": True,
                    "error": hold["reason"],
                    "safety": hold,
                }
            return {
                "success": False,
                "reported": reported,
                "error": f"[{result['code']}] {result['message']}",
            }
        reported += progress["per_round"]
        previous = progress["current"]
        for delay in (_gateway.LIVE_LIKE_PROGRESS_DELAY, _gateway.LIVE_LIKE_PROGRESS_RETRY_DELAY):
            time.sleep(delay)
            progress = _gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
            if "error" in progress:
                return {"success": False, "reported": reported, "error": progress["error"]}
            if progress["current"] > previous or progress["done"]:
                break
        else:
            return {
                "success": False,
                "reported": reported,
                "error": "点赞接口返回成功，但粉丝团任务进度未增加",
            }
    return {
        "success": True,
        "reported": reported,
        "progress": f"{progress['current']}/{progress['limit']}",
        "done": progress["done"] or progress["current"] >= progress["limit"],
    }
