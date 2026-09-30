"""One paginated medal query, shared by watch, synchronization and check-in."""

from ..http import require_data


def entries(sessdata, bili_jct, gateway):
    page = 1
    seen = set()
    while page <= 100:
        url = f"https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/panel?page={page}&page_size=50"
        response = gateway._get_json(url, gateway._make_headers(sessdata, bili_jct))
        data = require_data(response, "获取粉丝牌")
        for item in (data.get("special_list") or []) + (data.get("list") or []):
            medal = item.get("medal", item)
            identity = medal.get("medal_id") or medal.get("target_id")
            if identity and identity not in seen:
                seen.add(identity)
                yield item
        if page >= int(data.get("page_info", {}).get("total_page", 1)):
            return
        page += 1
    raise RuntimeError("粉丝牌分页超过上限，无法确认完整列表")
