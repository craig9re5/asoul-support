"""Verify the committed browser libraries, or restore their exact pinned bytes.

Normal builds only verify local files. --download is an explicit repair command;
it never updates versions and verifies SHA-256 before replacing a vendor file.
"""

import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "desktop" / "webui" / "assets" / "vendor"
NOTICE = "THIRD_PARTY_NOTICES.txt"

# Digests of the original, unmodified upstream files, including their line endings.
ASSETS = {
    "react.js": {
        "package": "React",
        "version": "18.3.1",
        "url": "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
        "sha256": "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd",
        "runtime": True,
    },
    "react-dom.js": {
        "package": "React DOM",
        "version": "18.3.1",
        "url": "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
        "sha256": "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d",
        "runtime": True,
    },
    "babel.js": {
        "package": "@babel/standalone",
        "version": "7.29.0",
        "url": "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js",
        "sha256": "2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0",
        "runtime": False,
    },
}


def verify_body(name, body):
    actual = hashlib.sha256(body).hexdigest()
    expected = ASSETS[name]["sha256"]
    if actual != expected:
        raise RuntimeError(
            f"{name}: SHA-256 mismatch (expected {expected}, got {actual}). "
            "Restore the committed upstream bytes, or run "
            "python tools/vendor_web_assets.py --download. "
            "Vendor files must not be edited or have their line endings converted."
        )
    return actual


def verify_assets(target=TARGET):
    """Return verified hashes without accessing the network or modifying files."""
    hashes = {}
    for name in ASSETS:
        path = target / name
        if not path.is_file():
            raise RuntimeError(
                f"Missing vendor library: {path}. Restore it from Git or run "
                "python tools/vendor_web_assets.py --download."
            )
        hashes[name] = verify_body(name, path.read_bytes())
    if not (target / NOTICE).is_file():
        raise RuntimeError(f"Missing third-party notices: {target / NOTICE}")
    return hashes


def restore_assets(target=TARGET):
    target.mkdir(parents=True, exist_ok=True)
    for name, asset in ASSETS.items():
        path = target / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"]:
            continue
        # Each download has its own empty directory. Nothing downloaded is executed.
        with tempfile.TemporaryDirectory(prefix=".vendor-", dir=target) as directory:
            staged = Path(directory) / name
            request = urllib.request.Request(
                asset["url"], headers={"User-Agent": "LiveSupport-build"}
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
            staged.write_bytes(body)
            verify_body(name, body)
            staged.replace(path)
            print(f"Restored {name} ({len(body)} bytes)")
    return verify_assets(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify local files (the default)")
    mode.add_argument("--download", action="store_true", help="restore the exact pinned files")
    args = parser.parse_args()
    try:
        hashes = restore_assets() if args.download else verify_assets()
    except (OSError, RuntimeError) as exc:
        print(f"Vendor verification failed: {exc}", file=sys.stderr)
        return 1
    for name, value in hashes.items():
        print(f"{name}: SHA-256 {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
