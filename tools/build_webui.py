"""Build or verify the offline, per-file scoped JavaScript used by the desktop UI.

Default: compile JSX with Node and the pinned, vendored Babel compiler.
--check: verify the committed output hashes without Node or a network connection.
--prepare: compile when Node is available; otherwise require fresh committed JS.
--stage-assets: copy only production runtime resources to a directory under build/.
"""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from vendor_web_assets import ASSETS as VENDOR_ASSETS, NOTICE, verify_assets

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "desktop" / "webui" / "assets"
JS = ASSETS / "js"
DRIVER = ROOT / "tools" / "build_webui.mjs"
HEADER = "/* LiveSupport JSX "
REBUILD = "Run python tools/build_webui.py with Node.js available, then commit the generated .js files."


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def text_bytes(path):
    # Git may use CRLF in a Windows checkout. Text inputs/output are hashed as LF.
    return path.read_text(encoding="utf-8").encode("utf-8")


def source_files():
    sources = sorted(JS.glob("*.jsx"))
    if not sources:
        raise RuntimeError(f"No JSX sources found in {JS}")
    return sources


def pipeline_hash():
    return sha256(text_bytes(Path(__file__)) + b"\0" + text_bytes(DRIVER))


def input_hashes(source, pipeline, body=None):
    return {
        "schema": 1,
        "source": source.name,
        "source_sha256": sha256(text_bytes(source) if body is None else body),
        "compiler_sha256": VENDOR_ASSETS["babel.js"]["sha256"],
        "pipeline_sha256": pipeline,
    }


class RuntimeReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            if attrs.get("type", "").lower() in {"text/babel", "text/jsx"}:
                raise RuntimeError("index.html still loads a runtime JSX compiler")
            if "src" in attrs:
                self.paths.append(attrs["src"])
                self.scripts.append(attrs["src"])
        elif tag == "link" and "stylesheet" in attrs.get("rel", "").lower().split():
            self.paths.append(attrs.get("href", ""))
        elif tag in {"img", "source"} and attrs.get("src"):
            self.paths.append(attrs["src"])


def runtime_files():
    """Production entry-point dependencies; development previews are not staged."""
    index = ASSETS / "index.html"
    refs = RuntimeReferences()
    refs.feed(index.read_text(encoding="utf-8"))
    paths = {index, ASSETS / "vendor" / NOTICE, ASSETS / "vendor" / "SOURCES.txt"}
    for reference in refs.paths:
        url = urlsplit(reference)
        path = PurePosixPath(unquote(url.path))
        if (
            url.scheme
            or url.netloc
            or not path.parts
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in str(path)
        ):
            raise RuntimeError(f"Only local relative runtime assets are allowed: {reference}")
        if path.suffix.lower() == ".jsx" or path == PurePosixPath("vendor/babel.js"):
            raise RuntimeError(f"Build-only asset referenced by index.html: {reference}")
        if path.name in {"preview.html", "demo.js"}:
            raise RuntimeError(f"Development preview referenced by index.html: {reference}")
        paths.add(ASSETS.joinpath(*path.parts))
    required = {f"js/{source.stem}.js" for source in source_files()}
    if not required.issubset(refs.scripts):
        raise RuntimeError(f"index.html is missing compiled scripts: {sorted(required - set(refs.scripts))}")
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"Missing runtime asset: {path}")
    return sorted(paths)


def verify_compiled():
    verify_assets()
    pipeline = pipeline_hash()
    for source in source_files():
        target = source.with_suffix(".js")
        if not target.is_file():
            raise RuntimeError(f"Missing precompiled output: {target}. {REBUILD}")
        first, separator, code = target.read_text(encoding="utf-8").partition("\n")
        try:
            if not first.startswith(HEADER) or not first.endswith(" */") or not separator:
                raise ValueError("missing build header")
            recorded = json.loads(first[len(HEADER):-3])
            expected = input_hashes(source, pipeline)
            expected["code_sha256"] = sha256(code.encode("utf-8"))
            if recorded != expected:
                raise ValueError("source, compiler, build tool, or output hash changed")
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"Stale precompiled output: {target.name} ({exc}). {REBUILD}") from exc
    return runtime_files()


def compile_with_node(node):
    verify_assets()
    sources = source_files()
    contents = {source.name: text_bytes(source) for source in sources}
    payload = [
        {"name": source.name, "source": contents[source.name].decode("utf-8")}
        for source in sources
    ]
    result = subprocess.run(
        [node, str(DRIVER), str(ASSETS / "vendor" / "babel.js")],
        input=json.dumps(payload, ensure_ascii=True),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"JSX compilation failed:\n{result.stderr[:4000]}")
    outputs = json.loads(result.stdout)
    if [item["name"] for item in outputs] != [source.name for source in sources]:
        raise RuntimeError("The JSX compiler returned an unexpected set of files")
    pipeline = pipeline_hash()
    for source, output in zip(sources, outputs):
        code = output["code"]
        info = input_hashes(source, pipeline, contents[source.name])
        info["code_sha256"] = sha256(code.encode("utf-8"))
        banner = HEADER + json.dumps(info, sort_keys=True, separators=(",", ":")) + " */\n"
        target = source.with_suffix(".js")
        body = (banner + code).encode("utf-8")
        if not target.exists() or target.read_bytes() != body:
            target.write_bytes(body)
        print(f"{source.name} -> {target.name}")
    return verify_compiled()


def stage_assets(destination, files):
    destination = destination.resolve()
    build = (ROOT / "build").resolve()
    if build not in destination.parents:
        raise RuntimeError("--stage-assets must name a generated subdirectory of this repository's build/")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".webui-", dir=destination.parent) as directory:
        staged = Path(directory) / "assets"
        for source in files:
            target = staged / source.relative_to(ASSETS)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    print(f"Staged {len(files)} production assets in {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify committed JS without Node")
    mode.add_argument("--prepare", action="store_true", help="compile, or verify committed JS if Node is absent")
    parser.add_argument("--stage-assets", type=Path, metavar="DIR", help="stage runtime assets under build/")
    args = parser.parse_args()
    try:
        node = shutil.which("node")
        if args.check or (args.prepare and not node):
            files = verify_compiled()
            print("Precompiled Web UI verified" + (" (Node unavailable)" if not node else ""))
        elif node:
            files = compile_with_node(node)
        else:
            raise RuntimeError(f"Node.js is required to compile JSX. {REBUILD} Use --check to verify existing output.")
        if args.stage_assets:
            stage_assets(args.stage_assets, files)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Web UI build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
