"""Credential storage paths and compatibility validation exports."""

from pathlib import Path
from .runtime import migrate_credentials, credentials_path
from .login_fields import LOGIN_COOKIE_NAMES, login_context, parse_cookie_header, parse_login_import


def load_saved(paths):
    from .context import runtime_path
    from .runtime import read_json

    for path in runtime_path("_COOKIE_PATHS", paths):
        if not Path(path).exists() and Path(path) == credentials_path():
            migrate_credentials()
        value = read_json(path, None)
        if isinstance(value, dict) and value.get("SESSDATA") and value.get("bili_jct"):
            return value
    return None


def cookie_path() -> Path:
    return credentials_path()
