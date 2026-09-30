"""Compatibility entry point; implementation lives in asoul_support.danmaku_pacing."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asoul_support import danmaku_pacing as _implementation

if __name__ == "__main__":
    from asoul_support.entrypoints import run_cli

    raise SystemExit(run_cli(_implementation.main))
else:
    sys.modules[__name__] = _implementation
