"""Executable error boundary; library calls keep their exceptions and signatures."""

import sys
from .http import ApiError
from .redaction import redact


def run_cli(main):
    try:
        return main() or 0
    except (ApiError, OSError, ValueError, RuntimeError) as exc:
        print(f"❌ {redact(str(exc))}", file=sys.stderr)
        return 1


def heartbeat():
    from .heartbeat import main

    return run_cli(main)


def checkin():
    from .checkin import main

    return run_cli(main)


def videos():
    from .videos import main

    return run_cli(main)


def dynamics():
    from .dynamics import main

    return run_cli(main)
