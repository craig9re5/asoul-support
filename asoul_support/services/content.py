"""Collect an entire requested video window before performing any actions."""

from ..content_filters import month_bounds
import time

MAX_CONTENT_PAGES = 100


def cutoff_for(args, gateway):
    if args.month:
        return month_bounds(*gateway.parse_month(args.month))[0]
    if not args.days or args.days < 1:
        raise ValueError("天数必须大于 0")
    return int(time.time()) - args.days * 86400


def video_window(uid, args, sessdata, bili_jct, gateway):
    cutoff = cutoff_for(args, gateway)
    result, seen = ([], set())
    for page in range(1, MAX_CONTENT_PAGES + 1):
        videos = gateway.fetch_user_videos(uid, sessdata, bili_jct, page=page)
        fresh = [video for video in videos if video.get("aid") not in seen]
        if videos and (not fresh):
            raise RuntimeError("视频分页重复，无法确认完整范围")
        seen.update((video.get("aid") for video in fresh))
        result.extend(fresh)
        if (
            not videos
            or len(videos) < 30
            or max((video.get("created", 0) for video in videos)) < cutoff
        ):
            return result
    raise RuntimeError("视频分页超过上限，未执行任何视频操作")
