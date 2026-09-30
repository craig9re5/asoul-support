"""Summarize the shared activity log; distinguish missing data from offline rooms."""

import argparse
import json
import time
from pathlib import Path
from typing import List
from .runtime import data_dir

_LOG_FILE = data_dir() / "logs" / "activity.jsonl"


def load_recent(hours=24, log_file=None):
    path = Path(log_file) if log_file else _LOG_FILE
    if not path.exists():
        return []
    cutoff = time.time() - hours * 3600
    records, starts = ([], {})
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get("ts"), (int, float)):
                    continue
                if row.get("type") == "watch_start" and row.get("session_id"):
                    starts[row["session_id"]] = row
                if row["ts"] >= cutoff:
                    records.append(row)
            except ValueError:
                continue
    present = {r.get("session_id") for r in records if r.get("type") == "watch_start"}
    active_ids = {r.get("session_id") for r in records if r.get("session_id")}
    records.extend((starts[key] for key in active_ids - present if key in starts))
    return sorted(records, key=lambda row: row["ts"])


def pair_sessions(records):
    sessions, legacy, consumed = ({}, [], set())
    for row in sorted(records, key=lambda r: r.get("ts", 0)):
        kind = row.get("type")
        if kind not in ("watch_start", "watch_end", "watch_interrupted"):
            continue
        key = row.get("session_id")
        if key:
            session = sessions.setdefault(key, {"start": None, "end": None})
            if kind == "watch_start":
                session["start"] = session["start"] or row
            elif kind == "watch_end" or not session["end"]:
                session["end"] = row
        elif kind == "watch_start":
            legacy.append({"start": row, "end": None})
        elif kind == "watch_end":
            identity = (row.get("member"), row.get("ts"))
            if identity in consumed:
                continue
            candidates = [
                s
                for s in legacy
                if not s["end"]
                and s["start"].get("member") == row.get("member")
                and (s["start"]["ts"] <= row["ts"])
            ]
            if candidates:
                candidates[-1]["end"] = row
                consumed.add(identity)
    return list(sessions.values()) + legacy


def fmt_ts(ts):
    return time.strftime("%m/%d %H:%M", time.localtime(ts))


def build_summary(records: List[dict], hours=24):
    checks = [r for r in records if r.get("type") == "check"]
    sessions = pair_sessions(records)
    lines = [f"A-SOUL 过去 {hours:g} 小时活动汇总", "", f"检测次数：{len(checks)}"]
    if not records:
        lines.append("没有运行记录，无法判断是否有人开播；请检查监控是否运行及日志来源。")
        return "\n".join(lines)
    live_names = sorted({m["name"] for c in checks for m in c.get("live", [])})
    unknown_names = sorted({name for c in checks for name in c.get("unknown", [])})
    if live_names:
        lines.append("检测到在播：" + "、".join(live_names))
    elif checks:
        lines.append("记录中的检测未发现开播；不代表覆盖了整个统计时段。")
    if unknown_names:
        lines.append("查询失败，状态未知：" + "、".join(unknown_names))
    total = 0
    cutoff = time.time() - hours * 3600
    for session in sessions:
        start, end = (session["start"], session["end"])
        row = start or end
        name = row.get("member", str(row.get("room", "未知直播间")))
        if end:
            minutes = max(0, end.get("minutes", 0))
            minutes = min(minutes, max(0, int((end["ts"] - cutoff) / 60)))
            total += minutes
            reason = end.get("stopped_reason", "结束")
            delta = end.get("intimacy_delta")
            gain = (
                f"，亲密度 +{delta}"
                if isinstance(delta, int) and delta >= 0
                else "，亲密度增量无法确认"
            )
            lines.append(f"  {name}：{minutes} 分钟，{reason}{gain}")
        else:
            lines.append(f"  {name}：{fmt_ts(start['ts'])} 开始，未记录结束，不能确认仍在运行")
    lines.append(f"已记录结束的会话总时长：{total} 分钟")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--log-file", type=Path, help="显式读取历史日志，默认使用统一活动日志")
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error("hours 必须大于 0")
    path = args.log_file or _LOG_FILE
    print(f"日志来源：{path}")
    print(build_summary(load_recent(args.hours, path), args.hours))


if __name__ == "__main__":
    main()
