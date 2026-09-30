"""One HTTP/JSON boundary. Failures have explicit, credential-free metadata."""

import json
import urllib.error
import urllib.parse
import urllib.request
import time
from email.utils import parsedate_to_datetime
from .login_fields import parse_cookie_header
from .redaction import redact, register_secrets
from . import safety

READ_RETRY_DELAYS = (1, 2)
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        before, after = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(newurl)
        if (before.scheme, before.netloc) != (after.scheme, after.netloc):
            raise urllib.error.HTTPError(request.full_url, 403, "拒绝跨域会话重定向", headers, fp)
        return super().redirect_request(request, fp, code, message, headers, newurl)


class ApiError(RuntimeError):

    def __init__(self, code, message, *, kind="api"):
        self.code, self.kind = (code, kind)
        super().__init__(redact(message))


def _once(url, headers=None, *, data=None, method=None, timeout=10):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        open_request = (
            urllib.request.build_opener(SameOriginRedirect()).open
            if headers and headers.get("Cookie")
            else urllib.request.urlopen
        )
        with open_request(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except urllib.error.HTTPError as exc:
        value = {"code": exc.code, "message": f"HTTP {exc.code}", "error_kind": "http"}
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after and retry_after.isdigit():
            value["retry_after"] = int(retry_after)
        elif retry_after:
            try:
                value["retry_after"] = max(
                    0, int(parsedate_to_datetime(retry_after).timestamp() - time.time())
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return value
    except (OSError, urllib.error.URLError, TimeoutError):
        return {"code": -1, "message": "网络请求失败", "error_kind": "network"}
    except (ValueError, UnicodeError):
        return {"code": -1, "message": "服务端响应格式无效", "error_kind": "data"}


def get_json(url, headers, timeout=10):
    return request_json(url, headers, timeout=timeout)


def request_json(url, headers=None, *, data=None, method=None, timeout=10, auth_probe=False):
    """Retry reads only; never replay a write after an ambiguous outcome."""
    headers = headers or {}
    parts = parse_cookie_header(headers.get("Cookie", "")) if headers.get("Cookie") else {}
    register_secrets(parts)
    sessdata = parts.get("SESSDATA")
    parsed = urllib.parse.urlsplit(url)
    if sessdata and (
        parsed.scheme != "https"
        or parsed.hostname
        not in {
            "api.bilibili.com",
            "api.live.bilibili.com",
            "api.vc.bilibili.com",
            "live-trace.bilibili.com",
        }
    ):
        return {"code": -1, "message": "拒绝向非预期地址发送登录会话", "error_kind": "safety"}
    effective_method = method or ("POST" if data is not None else "GET")
    mutation = effective_method != "GET" and parsed.path not in safety.READ_POST_PATHS
    if sessdata:
        hold = safety.status(sessdata)
        may_read = hold.get("kind") == "uncertain" and not mutation
        if (
            hold["blocked"]
            and not may_read
            and not (auth_probe and parsed.path == "/x/web-interface/nav")
        ):
            return safety.blocked_response(hold)
        if mutation and not safety.identity(sessdata).startswith("uid-"):
            verified = request_json(NAV_URL, headers, timeout=timeout)
            if not safety.identity(sessdata).startswith("uid-"):
                return (
                    verified
                    if verified.get("code") != 0
                    else {
                        "code": -101,
                        "message": "无法认证账号身份，本次跳过操作",
                        "error_kind": "auth",
                    }
                )
    op = safety.operation(url, data, effective_method)
    if sessdata and mutation:
        denied = safety.reserve(sessdata, op)
        if denied:
            return denied
    delays = () if mutation else READ_RETRY_DELAYS
    for attempt in range(len(delays) + 1):
        response = _once(url, headers, data=data, method=method, timeout=timeout)
        if response.get("error_kind") != "network" or attempt == len(delays):
            break
        time.sleep(delays[attempt])
        if sessdata:
            hold = safety.status(sessdata)
            if hold["blocked"] and hold.get("kind") != "uncertain":
                return safety.blocked_response(hold)
    if sessdata:
        safety.observe(sessdata, url, response, mutation=mutation, op=op)
    if isinstance(response.get("message"), str):
        response["message"] = redact(response["message"])
    return response


def post_form(url, data, headers, timeout=10):
    return request_json(
        url,
        {**headers, "Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(data).encode("utf-8"),
        timeout=timeout,
    )


def post_empty(url, headers, timeout=10):
    return request_json(url, headers, method="POST", timeout=timeout)


def require_data(response, operation):
    if not response or response.get("code") != 0:
        value = response or {}
        raise ApiError(
            value.get("code", -1),
            f"{operation}失败：{value.get('message', '无响应')}",
            kind=value.get("error_kind", "api"),
        )
    return response.get("data") or {}
