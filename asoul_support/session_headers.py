"""One account-bound session header builder for all authenticated modules."""

from .runtime import credentials_path, read_json
from .login_fields import login_context, parse_cookie_header
from .redaction import register_secrets

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
)


def session_headers(sessdata, bili_jct, referer="https://www.bilibili.com/"):
    parts = {"SESSDATA": sessdata, "bili_jct": bili_jct}
    ua = DEFAULT_UA
    try:
        saved = read_json(credentials_path(), {})
    except RuntimeError:
        # An explicitly supplied new login can be verified; existing callers cannot
        # obtain an unreadable stored credential pair in the first place.
        saved = {}
    if saved.get("SESSDATA") == sessdata and saved.get("bili_jct") == bili_jct:
        context = saved.get("qr_login_context")
        if context is None and saved.get("live_like_cookie"):
            context = {
                "cookies": parse_cookie_header(saved["live_like_cookie"]),
                "user_agent": saved.get("live_like_user_agent"),
            }
        if context is not None:
            context = login_context(context.get("cookies"), context.get("user_agent"))
            if (
                context["cookies"].get("SESSDATA") != sessdata
                or context["cookies"].get("bili_jct") != bili_jct
            ):
                raise ValueError("登录会话与当前账号不匹配，请重新登录")
            parts, ua = context["cookies"], context["user_agent"]
    # Validate direct CLI credentials too, before any header is sent.
    parts = login_context(parts, ua)["cookies"]
    register_secrets(parts)
    return {
        "User-Agent": ua,
        "Cookie": "; ".join(f"{k}={v}" for k, v in sorted(parts.items())),
        "Referer": referer,
    }
