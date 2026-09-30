from asoul_support.launch import watch_arguments

"Launch one heartbeat worker per live room using the shared desktop data."
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from asoul_support.runtime import data_dir, FileLock
from desktop.storage import initialize, load_config
from asoul_support.members import DEFAULT_MEMBERS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="只查询，不启动挂机进程")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    root = data_dir()
    initialize(root, DEFAULT_MEMBERS)
    config, members = load_config(root)
    if config.get("paused", False) and (not args.check_only):
        print("监控已暂停，跳过启动。")
        return 0
    env = {**os.environ, "ASOUL_APP_DATA": str(root), "PYTHONIOENCODING": "utf-8"}
    with FileLock(root / "locks" / "manager.lock") as manager:
        if not manager.acquired:
            print("已有管理器正在检查，跳过重复运行。")
            return 0
        auth = subprocess.run(
            [sys.executable, str(source / "scripts/check_auth.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        if auth.returncode:
            print("ERROR: Bilibili login check failed: " + auth.stderr.strip())
            return 1
        result = subprocess.run(
            [sys.executable, str(source / "scripts/heartbeat.py"), "--check-only", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )
        if result.returncode:
            print("ERROR: 无法完整查询直播状态：" + result.stderr.strip())
            return 1
        data = json.loads(result.stdout)
        live_rooms = {m["room"] for m in data.get("live", [])}
        print("当前在播：" + "、".join((m["name"] for m in members if m["room"] in live_rooms)))
        if args.check_only:
            return 0
        for member in members:
            if member["room"] not in live_rooms:
                continue
            with FileLock(root / "locks" / f"{member['room']}.watch.lock") as lease:
                if not lease.acquired:
                    print(member["name"] + "：已有挂机运行")
                    continue
            cmd = [
                sys.executable,
                str(source / "scripts/heartbeat.py"),
                *watch_arguments(member, config),
            ]
            path = root / "logs" / f"heartbeat-{member['room']}-{time.time_ns()}.log"
            with path.open("w", encoding="utf-8") as stream:
                child = subprocess.Popen(
                    cmd,
                    cwd=source,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            print(f"{member['name']}：启动 PID {child.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
