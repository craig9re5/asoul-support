"""Shared date windows for videos and dynamics (China time)."""

from datetime import datetime, timedelta, timezone
import re
import time

CST = timezone(timedelta(hours=8))


def month_bounds(year, month):
    start = datetime(year, month, 1, tzinfo=CST)
    end = (
        datetime(year + 1, 1, 1, tzinfo=CST)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=CST)
    )
    return (int(start.timestamp()), int(end.timestamp()))


def filter_month(items, year, month, timestamp_key):
    start, end = month_bounds(year, month)
    return [item for item in items if start <= item.get(timestamp_key, 0) < end]


def filter_days(items, days, timestamp_key):
    if days <= 0:
        raise ValueError("天数必须大于 0")
    cutoff = int(time.time()) - days * 86400
    return [item for item in items if item.get(timestamp_key, 0) >= cutoff]


def parse_month(value):
    value = value.strip()
    if re.fullmatch("\\d{4}[-/]\\d{1,2}", value):
        year, month = map(int, re.split("[-/]", value))
    elif re.fullmatch("\\d{1,2}", value):
        year, month = (datetime.now(CST).year, int(value))
    else:
        raise ValueError(f"无法解析月份: {value}")
    month_bounds(year, month)
    return (year, month)
