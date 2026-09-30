"""LiveSupport desktop entry point. Worker modes reuse the existing protocol."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from desktop.storage import data_dir, initialize, send_command
from asoul_support.members import MEMBERS
from asoul_support.runtime import APP_VERSION
from asoul_support.redaction import SafeStream, SafeFormatter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=int)
    parser.add_argument("--probe")
    parser.add_argument("--skip-actions", action="store_true")
    parser.add_argument("--command", choices=["pause", "resume", "check", "show", "exit"])
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--login", action="store_true", help="打开 B 站扫码登录")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--protect-credentials", action="store_true")
    parser.add_argument("--legacy-credentials")
    args = parser.parse_args()
    root = data_dir()
    initialize(root, MEMBERS)
    if args.protect_credentials:
        from asoul_support.runtime import protect_credentials, write_json

        write_json(
            root / "credential-migration.json", protect_credentials(root, args.legacy_credentials)
        )
        return 0
    if args.command:
        from desktop.windows import Mutex, instance_name

        active = Mutex(instance_name(root))
        if active.acquired:
            active.close()
            return 2
        send_command(root, args.command)
        active.close()
        return 0
    # No-console executables have no usable standard streams, even with redirection.
    log_path = (
        root
        / "logs"
        / (
            f"room-{args.worker}.log"
            if args.worker
            else "probe.log" if args.probe else "desktop.log"
        )
    )
    if log_path.exists() and log_path.stat().st_size > 2_000_000:
        try:
            os.replace(log_path, log_path.with_suffix(".previous.log"))
        except PermissionError:
            pass  # A second launch may encounter the current instance's log.
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = SafeStream(stream)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(
                root / "logs" / "errors.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
        ],
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SafeFormatter("%(asctime)s %(levelname)s %(message)s"))
    logging.info(
        "Startup mode=%s root=%s cwd=%s credentials_present=%s",
        "probe" if args.probe else "worker" if args.worker else "desktop",
        root,
        os.getcwd(),
        (root / "credentials.json").exists(),
    )
    if args.probe:
        from desktop.worker import probe

        return probe(root, Path(args.probe))
    if args.worker:
        from desktop.worker import watch

        return watch(root, args.worker, args.skip_actions)
    if args.diagnostic:
        from desktop.ui import icon_image
        from desktop.storage import write_json, load_config
        from desktop.windows import Job
        import tkinter as tk
        import qrcode
        from qrcode.image.pil import PilImage

        qr = qrcode.make("https://www.bilibili.com/", image_factory=PilImage)

        config, members = load_config(root)
        window = tk.Tk()
        window.withdraw()
        window.update()
        window.destroy()
        job = Job()
        job.close()
        write_json(
            root / "diagnostic.json",
            {
                "ok": True,
                "version": APP_VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "members": len(members),
                "icon": icon_image().size,
                "qr": qr.size,
            },
        )
        return 0
    from desktop.windows import Mutex, instance_name

    mutex = Mutex(instance_name(root))
    if not mutex.acquired:
        send_command(root, "login" if args.login else "show")
        mutex.close()
        return 0
    try:
        from desktop.engine import Engine
        from desktop.ui import TrayUI

        engine = Engine(root)
        ui = TrayUI(engine, show=args.show or not (root / "credentials.json").exists())
        if args.login:
            ui.root.after_idle(lambda: ui.open_settings(focus_auth=True, scan=True))
        engine.start()
        ui.run()
    except Exception:
        logging.exception("Desktop startup failed")
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"启动失败，请查看 {root / 'logs' / 'errors.log'}", "LiveSupport", 0x10
        )
        return 1
    finally:
        mutex.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
