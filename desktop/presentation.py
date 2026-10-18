"""Shared room labels for cards, detail views and activity previews."""

import time


def phase_label(row, now=None):
    now = time.time() if now is None else now
    phase = row.get("phase", "等待检查")
    if row.get("active") and phase == "挂机中":
        if row.get("watch_warning"):
            return "挂机中 · 观看收益待核验"
        if row.get("watch_note"):
            return "挂机中 · 收益轮转中"
        minutes = max(0, int((now - (row.get("started") or now)) / 60))
        return f"挂机中·{minutes}分钟"
    return phase


def gain_label(row):
    value = row.get("intimacy_gain")
    if value is None:
        return "今日亲密度：待更新"
    return f"今日亲密度 +{value}"
