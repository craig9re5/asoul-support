"""Run contracts with internet calls blocked, even if local credentials exist."""

import sys
from pathlib import Path
import unittest
import urllib.request
import os
import tempfile
from unittest.mock import patch
from contextlib import ExitStack
import base64
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def forbidden(*args, **kwargs):
    raise AssertionError("Offline tests attempted an internet request")


def main():
    urllib.request.urlopen = forbidden
    urllib.request.OpenerDirector.open = forbidden
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"ASOUL_APP_DATA": folder}))
        if os.name != "nt":
            # CI-only injected vault; production never recognizes this backend.
            from asoul_support import runtime
            from asoul_support.secret_store import FORMAT

            stack.enter_context(
                patch.object(
                    runtime,
                    "seal",
                    side_effect=lambda value: (
                        {
                            "format": FORMAT,
                            "version": 1,
                            "backend": "offline-test",
                            "payload": base64.b64encode(json.dumps(value).encode()).decode(),
                        }
                        if value
                        else {}
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    runtime,
                    "unseal",
                    side_effect=lambda value: json.loads(base64.b64decode(value["payload"])),
                )
            )
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
