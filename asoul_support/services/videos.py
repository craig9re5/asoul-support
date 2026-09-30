import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List


def process_member_videos(
    member: Dict,
    videos: List[Dict],
    sessdata: str,
    bili_jct: str,
    do_like: bool = True,
    do_coin: bool = False,
    do_fav: bool = False,
    fav_id: Optional[int] = None,
    delay: float = 8,
    *,
    _gateway,
) -> List[Dict]:
    results = []
    for i, v in enumerate(videos):
        aid = v["aid"]
        title = v["title"]
        actions = []
        if do_like:
            r = _gateway.like_video(aid, sessdata, bili_jct)
            actions.append(r)
            if do_coin or do_fav:
                time.sleep(2)
        if do_coin:
            r = _gateway.coin_video(aid, sessdata, bili_jct)
            actions.append(r)
            if do_fav:
                time.sleep(2)
        if do_fav:
            r = _gateway.fav_video(aid, sessdata, bili_jct, fav_id)
            actions.append(r)
        results.append(
            {
                "member": member["name"],
                "title": title,
                "bvid": v.get("bvid", ""),
                "aid": aid,
                "url": f"https://www.bilibili.com/video/{v.get('bvid', '')}",
                "created": v.get("created", 0),
                "actions": actions,
            }
        )
        if i < len(videos) - 1:
            time.sleep(delay)
    return results


def format_output(
    all_results: List[Dict], do_like: bool, do_coin: bool, do_fav: bool, *, _gateway
) -> str:
    action_names = []
    if do_like:
        action_names.append("点赞")
    if do_coin:
        action_names.append("投币")
    if do_fav:
        action_names.append("收藏")
    action_str = "+".join(action_names)
    lines = [f"🌟 A-SOUL 视频{action_str}结果", ""]
    total_videos = 0
    total_success = 0
    current_member = None
    for r in all_results:
        if r["member"] != current_member:
            current_member = r["member"]
            lines.append(f"  👤 {current_member}:")
        total_videos += 1
        title_short = r["title"][:30] + ("..." if len(r["title"]) > 30 else "")
        dt = datetime.fromtimestamp(r["created"], _gateway.CST).strftime("%m-%d")
        action_icons = []
        all_ok = True
        for a in r["actions"]:
            act = a["action"]
            if a.get("success"):
                if a.get("already_done"):
                    action_icons.append({"like": "👍⏭", "coin": "🪙⏭", "fav": "⭐⏭"}[act])
                else:
                    action_icons.append({"like": "👍✅", "coin": "🪙✅", "fav": "⭐✅"}[act])
                    total_success += 1
            else:
                action_icons.append({"like": "👍❌", "coin": "🪙❌", "fav": "⭐❌"}[act])
                all_ok = False
        status = " ".join(action_icons)
        lines.append(f"    [{dt}] {title_short}  {status}")
    lines.append("")
    lines.append(f"📊 共处理 {total_videos} 个视频")
    return "\n".join(lines)
