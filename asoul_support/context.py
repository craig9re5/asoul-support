"""Task-local runtime dependencies; scopes are restored on exceptions and nesting."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from .public_session import SessionProvider


@dataclass(frozen=True)
class RuntimeContext:
    root: Path
    observer: Optional[Callable] = None
    notify: Optional[Callable] = None
    public_sessions: SessionProvider = field(default_factory=SessionProvider)


CURRENT = ContextVar("live_support_runtime", default=None)


@contextmanager
def use_context(context):
    token = CURRENT.set(context)
    try:
        yield context
    finally:
        CURRENT.reset(token)


def runtime_path(name, fallback):
    context = CURRENT.get()
    if context is None:
        return fallback
    paths = {
        "_LOG_DIR": "logs",
        "_LOG_FILE": "logs/activity.jsonl",
        "_LOCK_DIR": "locks",
        "_TASK_STATE_DIR": "state/tasks",
    }
    if name == "_COOKIE_PATHS":
        return [context.root / "credentials.json"]
    return context.root / paths[name]
