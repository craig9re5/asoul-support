"""Remove credentials from logs, diagnostics and exception messages."""

import logging
import re
import threading

_SECRET_KEYS = re.compile(
    r"^(cookie|set-cookie|authorization|sessdata|bili_jct|csrf(?:_token)?|"
    r"qrcode_key|refresh_token|access_token|secret_key|qr_login_context|live_like_cookie|"
    r"sid|buvid\w*|w_rid|DedeUserID__ckMd5)$",
    re.I,
)
_ASSIGNMENT = re.compile(
    r"(?i)((?:SESSDATA|bili_jct|csrf(?:_token)?|qrcode_key|refresh_token|access_token|"
    r"sid|buvid\w*|secret_key|w_rid)\s*[\"']?\s*[:=]\s*[\"']?)[^\s;&\"'<>]+"
)
_known = set()
_lock = threading.Lock()


def register_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_KEYS.match(str(key)) or str(key).lower().startswith("buvid") or key == "sid":
                if isinstance(item, str) and len(item) >= 12:
                    with _lock:
                        _known.add(item)
            if isinstance(item, (dict, list, tuple)):
                register_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            register_secrets(item)


def forget_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_KEYS.match(str(key)) and isinstance(item, str):
                with _lock:
                    _known.discard(item)
            elif isinstance(item, (dict, list, tuple)):
                forget_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            forget_secrets(item)


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEYS.match(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    with _lock:
        secrets = sorted(_known, key=len, reverse=True)
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(
        r"(?im)((?:set-cookie|cookie|authorization)\s*:\s*)[^\r\n]+", r"\1[REDACTED]", value
    )
    return _ASSIGNMENT.sub(r"\1[REDACTED]", value)


class SafeStream:
    """Buffer by line so split writes cannot reveal a credential."""

    def __init__(self, stream):
        self.stream, self.pending = stream, ""
        self.lock = threading.Lock()

    def write(self, value):
        with self.lock:
            self.pending += value
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                self.stream.write(redact(line) + "\n")
        return len(value)

    def flush(self):
        with self.lock:
            if self.pending:
                self.stream.write(redact(self.pending))
                self.pending = ""
            self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))
