"""Record build inputs and gather installed dependency license texts."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def licenses(output):
    target = output / "third_party_licenses"
    target.mkdir(parents=True, exist_ok=True)
    dependencies = {}
    for name in ("Pillow", "pystray", "six", "PyInstaller", "qrcode", "colorama",
                 "pywebview", "pythonnet", "clr_loader", "cffi", "pycparser", "bottle",
                 "typing_extensions", "proxy_tools", "pyinstaller-hooks-contrib"):
        distribution = metadata.distribution(name)
        dependencies[name] = distribution.version
        files = [
            file
            for file in distribution.files or []
            if any(word in str(file).lower() for word in ("license", "copying"))
        ]
        if not files:
            if name == "proxy_tools":
                # The wheel omits its upstream license, copied in consolidated notices.
                shutil.copyfile(ROOT / "desktop/webui/assets/vendor/THIRD_PARTY_NOTICES.txt",
                                target / "proxy_tools-upstream-notices.txt")
                continue
            raise RuntimeError(f"Missing dependency license: {name}")
        for index, file in enumerate(files):
            shutil.copyfile(
                distribution.locate_file(file), target / f"{name}-{index}-{Path(file).name}"
            )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        raise RuntimeError("Python license not found")
    shutil.copyfile(python_license, target / "Python-LICENSE.txt")
    for file in (Path(sys.base_prefix) / "tcl").glob("*/license*"):
        shutil.copyfile(file, target / f"{file.parent.name}-{file.name}")
    shutil.copyfile(ROOT / "desktop/webui/assets/vendor/THIRD_PARTY_NOTICES.txt",
                    target / "Web-UI-THIRD-PARTY-NOTICES.txt")
    dependencies.update({"React": "18.3.1", "React-DOM": "18.3.1", "Babel-build-only": "7.29.0"})
    return dependencies


def main():
    from asoul_support.runtime import APP_VERSION

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    exe = args.exe.resolve()
    from build_webui import verify_compiled

    runtime_assets = verify_compiled()
    sources = (
        list((ROOT / "asoul_support").rglob("*.py"))
        + list((ROOT / "desktop").rglob("*.py"))
        + list((ROOT / "desktop/webui/assets/js").glob("*.jsx"))
        + [ROOT / "tray_app.py", ROOT / "build_desktop.ps1", ROOT / "requirements-desktop.txt",
           ROOT / "tools/build_webui.py", ROOT / "tools/build_webui.mjs", ROOT / "tools/vendor_web_assets.py"]
        + runtime_assets
    )
    command = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    commit = subprocess.run(
        command + ["rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            command + ["status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        ).stdout.strip()
    )
    value = {
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_dirty": dirty,
        "exe_sha256": digest(exe),
        "sources": {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(set(sources))},
        "bundle_sources": {path.relative_to(ROOT).as_posix(): digest(path) for path in runtime_assets},
        "dependencies": licenses(exe.parent),
    }
    (exe.parent / "build-info.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(f"Build manifest: {exe.parent / 'build-info.json'}")


if __name__ == "__main__":
    main()
