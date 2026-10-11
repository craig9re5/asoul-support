"""Worker progress deadlines and bounded recovery delays."""
import math

CONNECT_TIMEOUT = 30 * 60  # Includes account-wide task queueing before the first beat.
TASK_TIMEOUT = 30 * 60
RESTART_BASE = 60
RESTART_MAX = 15 * 60


def number(value, default=0):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else default


def heartbeat_timeout(state):
    return max(180, min(300, max(5, number(state.get("interval"), 60))) * 2 + 90)


def check_progress(state, record, now):
    """Use monotonic deadlines, ignoring files left by another worker generation."""
    if state.get("pid") != record["pid"]:
        return now - record["started"] > CONNECT_TIMEOUT
    beat = number(state.get("last_heartbeat"))
    task_start = number(state.get("task_started")) if state.get("phase") == "执行任务中" else 0
    signature = (beat, task_start)
    if beat != record.get("beat_signature"):
        record["beat_signature"] = beat
        record["beat_progress"] = now
    if signature != record.get("signature"):
        record["signature"] = signature
        record["progress"] = now
    record["had_beat"] = record.get("had_beat", False) or beat > 0
    # Task churn must never reset the deadline for an actual successful beat.
    if not record["had_beat"]:
        return now - record["started"] > CONNECT_TIMEOUT
    timeout = TASK_TIMEOUT if task_start else heartbeat_timeout(state)
    return now - record.get("beat_progress", record["started"]) > timeout


def recovery_delay(attempt):
    return min(RESTART_MAX, RESTART_BASE * 2 ** min(max(attempt - 1, 0), 4))
