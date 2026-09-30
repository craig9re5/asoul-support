import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List


def process_member_dynamics(
    member: Dict, dynamics: List[Dict], sessdata: str, bili_jct: str, delay: float = 8, *, _gateway
) -> List[Dict]:
    results = []
    for i, d in enumerate(dynamics):
        r = _gateway.like_dynamic(d["dyn_id"], sessdata, bili_jct)
        results.append(
            {
                "member": member["name"],
                "dyn_id": d["dyn_id"],
                "type": d["type_name"],
                "text": d["text"],
                "pub_ts": d["pub_ts"],
                "url": f"https://t.bilibili.com/{d['dyn_id']}",
                **r,
            }
        )
        if i < len(dynamics) - 1:
            time.sleep(delay)
    return results


def format_output(all_results: List[Dict], *, _gateway) -> str:
    lines = ["🌟 A-SOUL 动态点赞结果", ""]
    total = 0
    new_likes = 0
    current_member = None
    for r in all_results:
        if r["member"] != current_member:
            current_member = r["member"]
            lines.append(f"  👤 {current_member}:")
        total += 1
        dt = datetime.fromtimestamp(r["pub_ts"], _gateway.CST).strftime("%m-%d")
        text_short = r["text"][:25] + ("..." if len(r["text"]) > 25 else "")
        if r.get("success"):
            if r.get("already_done"):
                icon = "👍⏭"
            else:
                icon = "👍✅"
                new_likes += 1
        else:
            icon = "👍❌"
        lines.append(f"    [{dt}] [{r['type']}] {text_short}  {icon}")
    lines.append("")
    lines.append(f"📊 共处理 {total} 条动态，新点赞 {new_likes} 条")
    return "\n".join(lines)
