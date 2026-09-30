"""Public browser cookies belong to one request session and thread."""

from http.cookiejar import CookieJar
import logging
import threading
import urllib.request


class PublicSession:

    def __init__(self):
        self.jar = CookieJar()
        self.ready = False

    def cookies(self, user_agent):
        if not self.ready:
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
            request = urllib.request.Request(
                "https://www.bilibili.com", headers={"User-Agent": user_agent}
            )
            try:
                with opener.open(request, timeout=5):
                    self.ready = True
            except OSError as exc:
                logging.info("Public cookie initialization failed: %s", type(exc).__name__)
        return "; ".join((f"{cookie.name}={cookie.value}" for cookie in self.jar))


class SessionProvider:
    """No credentials are retained in the provider. Each thread has its own jar."""

    def __init__(self):
        self.local = threading.local()

    def current(self):
        if not hasattr(self.local, "session"):
            self.local.session = PublicSession()
        return self.local.session
