"""Coordinate danmaku sends from this machine's A-SOUL worker processes."""

import errno
import os
import time
from pathlib import Path
from typing import Callable, TypeVar
from .runtime import data_dir

MIN_SEND_INTERVAL = 6.0
LOCK_WAIT_TIMEOUT = 45.0
_LOCK_FILE = data_dir() / "locks" / "danmaku-send.lock"
_Result = TypeVar("_Result")


def _try_lock(stream) -> bool:
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise
        return False


def _unlock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def send_paced(
    sender: Callable[[], _Result],
    *,
    lock_path: Path = None,
    min_interval: float = MIN_SEND_INTERVAL,
    lock_timeout: float = LOCK_WAIT_TIMEOUT,
) -> _Result:
    """Serialize sends and reserve a minimum interval between attempts.

    The timestamp is written before sending so a failed request is paced too.
    The OS releases the lock if a worker exits unexpectedly.
    """
    lock_path = (
        Path(lock_path) if lock_path is not None else data_dir() / "locks" / "danmaku-send.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    deadline = time.monotonic() + lock_timeout
    with lock_path.open("r+b") as stream:
        while not _try_lock(stream):
            if time.monotonic() >= deadline:
                raise TimeoutError("等待弹幕发送锁超时")
            time.sleep(0.1)
        try:
            stream.seek(0)
            try:
                last_sent = float(stream.read(32).strip() or b"0")
            except ValueError:
                last_sent = 0.0
            elapsed = max(0.0, time.time() - last_sent)
            wait = max(0.0, min_interval - elapsed)
            if wait > 0:
                time.sleep(wait)
            stream.seek(0)
            stream.write(f"{time.time():.6f}".encode("ascii").ljust(32, b" "))
            stream.flush()
            return sender()
        finally:
            _unlock(stream)
