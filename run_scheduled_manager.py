#!/usr/bin/env python3
"""Run the multi-room manager from Task Scheduler with a readable log."""

import os
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from asoul_support.runtime import data_dir


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    root = Path(__file__).resolve().parent
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "scheduled_manager.log"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] Starting manager\n")
        log.flush()
        result = subprocess.run(
            [sys.executable, str(root / "manage_asoul_heartbeat.py")],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log.write(
            f"[{datetime.now().isoformat(timespec='seconds')}] Exit code: {result.returncode}\n"
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
