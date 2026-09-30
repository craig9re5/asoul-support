"""Web QR login for the user's own account; no browser/profile access."""

from dataclasses import dataclass, field
from http.cookies import SimpleCookie, CookieError
import json
import time
import urllib.request
from urllib.parse import urlencode, urlsplit, parse_qs

from .login_fields import parse_login_import, login_context, LOGIN_COOKIE_NAMES
from .http import SameOriginRedirect

PASSPORT = "https://passport.bilibili.com"
GENERATE = PASSPORT + "/x/passport-login/web/qrcode/generate"
POLL = PASSPORT + "/x/passport-login/web/qrcode/poll"
QR_LIFETIME = 180
POLL_INTERVAL = 2
QR_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
)


def passport_request(url, cookies=None, user_agent=QR_USER_AGENT):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Referer": "https://www.bilibili.com/",
            **(
                {"Cookie": "; ".join(f"{name}={value}" for name, value in cookies.items())}
                if cookies
                else {}
            ),
        },
    )
    try:
        open_request = (
            urllib.request.build_opener(SameOriginRedirect()).open
            if cookies
            else urllib.request.urlopen
        )
        with open_request(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
            cookies = {}
            for header in response.headers.get_all("Set-Cookie", []):
                parsed = SimpleCookie()
                parsed.load(header)
                for name in LOGIN_COOKIE_NAMES:
                    if name in parsed:
                        cookies[name] = parsed[name].value
    except (OSError, ValueError, UnicodeError, CookieError):
        raise RuntimeError("扫码登录请求失败，请检查网络后重试") from None
    if (
        not isinstance(body, dict)
        or body.get("code") != 0
        or not isinstance(body.get("data"), dict)
    ):
        raise RuntimeError("扫码登录服务返回异常，请稍后重试")
    return body["data"], cookies


class PassportSession:
    """One QR flow keeps server cookies; it never reads a browser profile."""

    def __init__(self):
        self.cookies = {}
        self.initialized = False

    def __call__(self, url):
        if not self.initialized:
            # Normal device-cookie issuance; no generated identity or activation bypass.
            device, issued = passport_request("https://api.bilibili.com/x/frontend/finger/spi")
            self.cookies.update(issued)
            for field, name in (("b_3", "buvid3"), ("b_4", "buvid4")):
                value = device.get(field)
                if isinstance(value, str) and value and not any(c in value for c in ";\r\n"):
                    self.cookies[name] = value
            self.initialized = True
        data, issued = passport_request(url, self.cookies)
        self.cookies.update(issued)
        return data, dict(self.cookies)

    def clear(self):
        self.cookies.clear()


def confirmed_credentials(data, cookies):
    if not all(cookies.get(name) for name in ("SESSDATA", "bili_jct")):
        # Some web responses also carry credentials in the cross-domain URL.
        # Parse it locally; never navigate to or log that URL.
        target = urlsplit(data.get("url", ""))
        if target.scheme != "https" or target.hostname not in {
            "passport.biligame.com",
            "passport.bilibili.com",
        }:
            raise RuntimeError("扫码已确认，但未收到完整登录凭证，请重新扫码")
        values = parse_qs(target.query)
        cookies = {name: (values.get(name) or [""])[0] for name in ("SESSDATA", "bili_jct")}
    try:
        return parse_login_import(json.dumps(cookies))
    except ValueError:
        raise RuntimeError("扫码已确认，但登录凭证格式不正确，请重新扫码") from None


@dataclass
class PollResult:
    state: str
    credentials: dict = field(default_factory=dict, repr=False)
    context: dict = field(default_factory=dict, repr=False)


class QrLoginSession:
    def __init__(self, request=None, clock=time.monotonic):
        self.request, self.clock = request if request is not None else PassportSession(), clock
        self.cookies = {}
        self.key = ""
        self.url = ""
        self.expires_at = 0
        self.state = "idle"

    def generate(self):
        data, issued = self.request(GENERATE)
        self.cookies = dict(issued)
        url, key = data.get("url", ""), data.get("qrcode_key", "")
        if not isinstance(url, str) or not isinstance(key, str):
            raise RuntimeError("二维码响应格式无效")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"passport.bilibili.com", "account.bilibili.com"}
            or not key
            or len(key) > 128
        ):
            raise RuntimeError("二维码响应格式无效")
        self.key, self.url = key, url
        self.expires_at = self.clock() + QR_LIFETIME
        self.state = "waiting"
        return url

    def cancel(self):
        self.key = self.url = ""
        self.cookies.clear()
        if isinstance(self.request, PassportSession):
            self.request.clear()
        self.state = "cancelled"

    def poll(self):
        if self.state in {"expired", "cancelled", "confirmed"}:
            return PollResult(self.state)
        if not self.key:
            raise RuntimeError("请先申请二维码")
        if self.clock() >= self.expires_at:
            self.key = self.url = ""
            self.state = "expired"
            return PollResult(self.state)
        data, cookies = self.request(POLL + "?" + urlencode({"qrcode_key": self.key}))
        self.cookies.update(cookies)
        code = data.get("code")
        states = {86101: "waiting", 86090: "scanned", 86038: "expired", 0: "confirmed"}
        if code not in states:
            raise RuntimeError("扫码状态异常，请刷新二维码重试")
        state = states[code]
        credentials = confirmed_credentials(data, self.cookies) if state == "confirmed" else {}
        context = {}
        if state == "confirmed":
            # Cross-domain URL may carry additional account cookies; only parse locally.
            target = urlsplit(data.get("url", ""))
            if target.scheme == "https" and target.hostname in {
                "passport.biligame.com",
                "passport.bilibili.com",
            }:
                for name, values in parse_qs(target.query).items():
                    if name in LOGIN_COOKIE_NAMES and name not in self.cookies:
                        self.cookies[name] = values[0]
            context = login_context({**self.cookies, **credentials}, QR_USER_AGENT)
        self.state = state
        if state in {"expired", "confirmed"}:
            self.key = self.url = ""
        return PollResult(state, credentials, context)
