"""Shared local storage for desktop and command-line entry points."""

import errno
import hashlib
import json
import os
import tempfile
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .context import CURRENT
from .secret_store import is_envelope, seal, unseal, discard
from .redaction import redact, register_secrets, forget_secrets

EVENT_CONTEXT = ContextVar("activity_context", default={})
APP_VERSION = "2026.09.30.8"


def data_dir():
    context = CURRENT.get()
    if context is not None:
        return context.root
    override = os.environ.get("ASOUL_APP_DATA")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LiveSupport"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "asoul-support"


def task_day():
    """Daily tasks use China time, independently of the machine timezone."""
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def account_key(sessdata):
    fingerprint = session_fingerprint(sessdata)
    bindings = _read_json(data_dir() / "state/account-bindings.json", {})
    return bindings.get(fingerprint, fingerprint)


def session_fingerprint(sessdata):
    return hashlib.sha256(sessdata.encode("utf-8")).hexdigest()[:20]


def _read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if is_envelope(value):
            value = unseal(value)
        if isinstance(value, dict) and "SESSDATA" in value:
            register_secrets(value)
        return value
    except FileNotFoundError:
        return default


def read_json(path, default=None):
    """Read compatible data; atomically protect an existing plaintext login file."""
    path = Path(path)
    if path.name == "credentials.json" and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if raw and not is_envelope(raw):
            return update_json(path, lambda value: value, default)
    return _read_json(path, default)


def write_json(path, value):
    """Use a unique temporary file, including for writers in the same process."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = path.name == "credentials.json" or (
        isinstance(value, dict) and ("SESSDATA" in value or "bili_jct" in value)
    )
    old = None
    if protected:
        register_secrets(value)
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8-sig"))
        value = seal(value)
    else:
        value = redact(value)
    committed = False
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        for attempt in range(5):
            try:
                os.replace(temp, path)
                committed = True
                if protected:
                    discard(old)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    finally:
        temp.unlink(missing_ok=True)
        if protected and not committed:
            discard(value)


class FileLock:
    """An OS lease; crash recovery does not depend on PID files."""

    def __init__(self, path, timeout=0):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        self.acquired = False
        deadline = time.monotonic() + timeout
        while True:
            self.stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    self.stream.close()
                    raise
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)

    def close(self):
        if self.stream.closed:
            return
        if self.acquired:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.acquired = False
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def update_json(path, change, default=None):
    """Serialize read-modify-write so settings and credentials retain other keys."""
    with FileLock(str(path) + ".guard", timeout=5) as lock:
        if not lock.acquired:
            raise TimeoutError("等待配置写入锁超时")
        value = change(_read_json(path, default))
        write_json(path, value)
        return value


def credentials_path(root=None):
    return (Path(root) if root is not None else data_dir()) / "credentials.json"


def migrate_credentials(root=None):
    """Import once; never replace an existing desktop credential file."""
    path = credentials_path(root)
    if path.exists():
        read_json(path, {})
        return path
    if os.environ.get("ASOUL_APP_DATA"):
        return path
    legacy = (
        Path(__file__).resolve().parents[2] / ".asoul-support-data" / ".cookies.json"
        if os.name == "nt"
        else data_dir() / ".cookies.json"
    )
    if legacy.exists():
        saved = read_json(legacy)
        if isinstance(saved, dict):
            update_json(path, lambda current: current if current is not None else saved)
            legacy.unlink()
    return path


def save_login(sessdata, bili_jct, path=None, *, context=None):
    path = Path(path) if path is not None else migrate_credentials()
    if context is not None:
        from .login_fields import login_context

        context = login_context(context.get("cookies"), context.get("user_agent"))
        if (
            context["cookies"].get("SESSDATA") != sessdata
            or context["cookies"].get("bili_jct") != bili_jct
        ):
            raise ValueError("扫码会话与登录凭证不一致")

    previous = []

    def change(saved):
        saved = dict(saved or {})
        previous.append(dict(saved))
        if saved.get("SESSDATA") != sessdata or saved.get("bili_jct") != bili_jct:
            for key in (
                "LIVE_BUVID",
                "live_like_cookie",
                "live_like_user_agent",
                "qr_login_context",
            ):
                saved.pop(key, None)
        if sessdata and bili_jct:
            saved.update(SESSDATA=sessdata, bili_jct=bili_jct)
            if context is not None:
                saved["qr_login_context"] = context
        else:
            saved.clear()
        return saved

    try:
        result = update_json(path, change, {})
    except RuntimeError:
        if context is None and (sessdata or bili_jct):
            raise
        # Confirmed QR login or explicit logout can replace an unreadable vault.
        with FileLock(str(path) + ".guard", timeout=5) as lease:
            if not lease.acquired:
                raise TimeoutError("凭证恢复等待超时")
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if not is_envelope(raw):
                raise
            result = change({})
            write_json(path, result)
    for old in previous:
        forget_secrets(old)
    register_secrets(result)
    if not sessdata and not bili_jct:
        # Account budgets and safety holds survive logout; only session aliases are cleared.
        bindings = path.parent / "state/account-bindings.json"
        if bindings.exists():
            update_json(bindings, lambda _: {}, {})
    return result


def append_event(path, event):
    record = redact({**EVENT_CONTEXT.get(), **event, "ts": int(time.time())})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".guard", timeout=5) as lock:
        if not lock.acquired:
            raise TimeoutError("等待活动日志锁超时")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    context = CURRENT.get()
    if context is not None and context.observer is not None:
        context.observer(record)


def protect_credentials(root, legacy=None):
    """Local-only upgrade. Remove the named legacy file only after matching verification."""
    root = Path(root)
    path = credentials_path(root)
    existing = read_json(path, {})
    removed = False
    if legacy is not None:
        source = Path(legacy).resolve()
        if source.name != ".cookies.json" or source.parent.name != ".asoul-support-data":
            raise ValueError("旧凭证迁移路径不符合约定")
        if source.exists():
            previous = _read_json(source, {})
            if not existing and previous.get("SESSDATA") and previous.get("bili_jct"):
                from .login_fields import parse_login_import

                parse_login_import(json.dumps(previous))
                update_json(path, lambda current: current or previous, {})
                existing = read_json(path, {})
            if existing and all(
                existing.get(k) == previous.get(k) for k in ("SESSDATA", "bili_jct")
            ):
                source.unlink()
                removed = True
    return {
        "protected": not existing or is_envelope(json.loads(path.read_text(encoding="utf-8-sig"))),
        "legacy_removed": removed,
    }
