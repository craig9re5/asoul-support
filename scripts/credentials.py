"""Compatibility entry point; implementation lives in asoul_support.credentials."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asoul_support import credentials as _implementation

if __name__ == "__main__":
    from asoul_support.entrypoints import run_cli

    raise SystemExit(run_cli(_implementation.main))
else:
    sys.modules[__name__] = _implementation
