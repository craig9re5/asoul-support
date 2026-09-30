import time
from typing import Dict, List

LIGHT_UP_COUNT = 10


def _pick_messages(msgs: List[str], count: int, *, _gateway) -> List[str]:
    """从消息池中选取 count 条不重复的弹幕；池不够则循环复用。"""
    import random

    pool = list(msgs)
    random.shuffle(pool)
    result = []
    for i in range(count):
        result.append(pool[i % len(pool)])
    return result


def batch_checkin(
    members,
    msgs,
    sessdata,
    bili_jct,
    auto_medal=True,
    count=LIGHT_UP_COUNT,
    delay=8,
    danmaku_delay=3,
    *,
    _gateway,
):
    from ..heartbeat import DailyTaskRunner

    if not msgs or (count is not None and count < 1):
        raise ValueError("消息池不能为空，发送条数应大于 0")
    medals = _gateway.get_my_medals(sessdata, bili_jct) if auto_medal else {}
    results = []
    for index, member in enumerate(members):
        medal = medals.get(member["uid"])
        worn = bool(medal and _gateway.wear_medal(medal["medal_id"], sessdata, bili_jct))
        task = DailyTaskRunner(
            member["room"],
            member["uid"],
            sessdata,
            bili_jct,
            messages=msgs,
            delay=danmaku_delay,
            requested_count=count,
        ).check()
        action = task.get("danmaku") or {}
        sent = action.get("total_sent", 0)
        failed = max(0, action.get("attempted", 0) - sent)
        lit = action.get("light_done", False)
        success = task["success"]
        error = task.get("error") or action.get("error")
        target = sent
        results.append(
            {
                "name": member["name"],
                "room": member["room"],
                "url": f"https://live.bilibili.com/{member['room']}",
                "sent_ok": sent,
                "sent_fail": failed,
                "count": target,
                "lit": lit,
                "success": success,
                "error": error,
                "medal": medal,
                "medal_worn": worn,
            }
        )
        if index < len(members) - 1:
            time.sleep(max(0, delay))
    return results


def format_output(results: List[Dict], *, _gateway) -> str:
    lines = ["🌟 A-SOUL 粉丝牌点亮结果", ""]
    lit_count = sum((1 for r in results if r["lit"]))
    for r in results:
        medal = r.get("medal")
        medal_str = ""
        if medal:
            if r.get("medal_worn"):
                medal_str = f"  🏅{medal['medal_name']}Lv{medal['level']}"
            else:
                medal_str = f"  🏅{medal['medal_name']}(佩戴失败)"
        elif r.get("success"):
            medal_str = "  (无粉丝牌)"
        if r["lit"]:
            lines.append(f"  ✅ {r['name']}{medal_str}  — 已点亮  💬{r['sent_ok']}/{r['count']}条")
        elif r["success"]:
            lines.append(f"  ⚠️ {r['name']}{medal_str}  — 部分成功  💬{r['sent_ok']}/{r['count']}条")
        else:
            err = r["error"] or "未知错误"
            if "login" in err.lower():
                lines.append(f"  ❌ {r['name']}  — Cookie 过期，请重新设置")
            else:
                lines.append(f"  ❌ {r['name']}  — {err}")
    lines.append("")
    if lit_count == len(results):
        lines.append(f"🎉 全部点亮成功！({lit_count}/{len(results)}) 牌子 3 天内不会熄灭")
    elif lit_count > 0:
        lines.append(
            f"📊 部分点亮：{lit_count}/{len(results)}，未满 {_gateway.LIGHT_UP_COUNT} 条的牌子可能无法点亮"
        )
    else:
        lines.append(f"💔 全部失败，请检查 Cookie 是否有效")
    return "\n".join(lines)
