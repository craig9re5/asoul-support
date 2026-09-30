"""Pure credential validation shared by QR login, storage and requests."""

import json

LOGIN_COOKIE_NAMES = frozenset(
    {
        "SESSDATA",
        "bili_jct",
        "DedeUserID",
        "DedeUserID__ckMd5",
        "sid",
        "buvid3",
        "buvid4",
        "b_nut",
        "LIVE_BUVID",
        "buvid_fp",
        "buvid_fp_plain",
    }
)


def login_context(cookies, user_agent):
    """Keep only server-issued login/device cookies and a safe request UA."""
    if not isinstance(cookies, dict) or not isinstance(user_agent, str):
        raise ValueError("登录会话格式无效")
    if (
        not user_agent
        or len(user_agent) > 1024
        or any(ord(c) < 32 or ord(c) > 126 for c in user_agent)
    ):
        raise ValueError("登录会话 User-Agent 格式无效")
    selected = {}
    for name in LOGIN_COOKIE_NAMES:
        value = cookies.get(name)
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 4096
            or any(ord(c) < 33 or ord(c) > 126 or c in ';,"\\' for c in value)
        ):
            raise ValueError("登录会话 Cookie 格式无效")
        selected[name] = value
    parse_login_import(json.dumps(selected))
    if "DedeUserID" in selected and (
        not selected["DedeUserID"].isdigit() or int(selected["DedeUserID"]) < 1
    ):
        raise ValueError("登录会话账号 ID 无效")
    return {"cookies": selected, "user_agent": user_agent}


def parse_cookie_header(raw: str) -> dict:
    if not raw or "\r" in raw or "\n" in raw:
        raise ValueError("Cookie 不能为空，也不能包含换行")
    cookies = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name:
            cookies[name] = value
    return cookies


def parse_login_import(raw: str) -> dict:
    """Validate a credential pair or legacy serialized input; keep two login fields."""
    if not isinstance(raw, str) or len(raw) > 16_384:
        raise ValueError("登录导入内容格式不正确或超过大小限制")
    raw = raw.lstrip("\ufeff").strip()
    if raw.startswith("{"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("登录导入文件不是有效 JSON") from None
        if value.get("format") not in (None, "livesupport-login") or value.get("version", 1) != 1:
            raise ValueError("不支持此登录导出格式")
        cookies = value.get("credentials", value)
        if not isinstance(cookies, dict):
            raise ValueError("登录导出内容缺少凭证对象")
    else:
        cookies = parse_cookie_header(raw)
    result = {}
    for name in ("SESSDATA", "bili_jct"):
        item = cookies.get(name)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"登录信息缺少 {name}，请重新扫码或检查输入")
        item = item.strip()
        if len(item) > 4096 or any(ord(c) < 33 or ord(c) > 126 or c in ';,"\\' for c in item):
            raise ValueError(f"{name} 格式不正确，请重新扫码或检查输入")
        result[name] = item
    return result
