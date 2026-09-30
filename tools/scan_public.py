"""Inspect publishable files and Git history without printing matched secret values."""

import argparse
import re
import subprocess
from pathlib import Path
import json
import sys
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "github token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "session literal": re.compile(
        r"(?:SESSDATA|bili_jct|csrf(?:_token)?|refresh_token|access_token|qrcode_key|"
        r"DedeUserID__ckMd5|buvid[34]|sid)[\"']?\s*[:=]\s*[\"']?"
        r"([A-Za-z0-9%_./+\-]{28,})", re.I
    ),
    "personal filesystem path": re.compile(
        r"\b[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][A-Za-z0-9_.-]+"
        r"|/(?:home|Users)/[A-Za-z0-9_.-]+", re.I
    ),
}
FORBIDDEN_NAMES = {
    "credentials.json",
    ".cookies.json",
    "activity.jsonl",
    "status.json",
    ".env",
    "auth.json",
    "members.json",
    "settings.json",
    "diagnostic.json",
}
FORBIDDEN_PARTS = {".asoul-support-data", "logs", "captures", "private-history"}
FORBIDDEN_SUFFIXES = {".har", ".pem", ".pfx", ".exe", ".log", ".bundle"}
PRIVATE_KEYS = re.compile(
    r"^(sessdata|bili_jct|csrf(?:_token)?|refresh_token|access_token|qrcode_key|"
    r"DedeUserID(?:__ckMd5)?|buvid\w*|sid)$", re.I
)


def git(*args, binary=False, root=ROOT):
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def scan_blob(data, label, findings, private_values=()):
    # Exact private values are also searched in binary data; pattern matching is textual.
    for value in private_values:
        if value.encode("utf-8") in data:
            findings.append({"file": label, "kind": "known private value"})
            break
    if b"\0" not in data:
        text = data.decode("utf-8", errors="replace")
        for category, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    {"file": label, "line": text.count("\n", 0, match.start()) + 1, "kind": category}
                )


def check_path(relative, label, findings):
    path = Path(relative)
    if (
        path.name in FORBIDDEN_NAMES
        or path.suffix.lower() in FORBIDDEN_SUFFIXES
        or any(part in FORBIDDEN_PARTS for part in path.parts)
    ):
        findings.append({"file": label, "kind": "private runtime/build file"})


def private_values_from_file(path):
    """Read only an explicitly supplied credential file; never log its contents."""
    sys.path.insert(0, str(ROOT))
    from asoul_support.secret_store import is_envelope, unseal

    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if is_envelope(value):
        value = unseal(value)
    values = set()

    def collect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if PRIVATE_KEYS.match(str(key)) and isinstance(child, (str, int)):
                    text = str(child)
                    if len(text) >= 8:
                        values.update((text, unquote(text), quote(unquote(text), safe="")))
                if isinstance(child, (dict, list)):
                    collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    return values


def history_blobs(root):
    """Batch object reads avoid starting a Git process for every historical blob."""
    objects = {}
    for row in git("rev-list", "--objects", "--all", root=root).splitlines():
        parts = row.split(" ", 1)
        if len(parts) == 2:
            objects.setdefault(parts[0], parts[1])
    if not objects:
        return
    result = subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "cat-file", "--batch"],
        cwd=root, input=("\n".join(objects) + "\n").encode("ascii"),
        check=True, capture_output=True,
    ).stdout
    offset = 0
    for oid, relative in objects.items():
        end = result.index(b"\n", offset)
        header = result[offset:end].split()
        if len(header) != 3 or header[0].decode() != oid:
            raise RuntimeError("Invalid Git object response")
        size = int(header[2])
        data = result[end + 1:end + 1 + size]
        offset = end + 2 + size
        if header[1] == b"blob":
            yield oid, relative, data


def scan(history=True, root=ROOT, private_values=()):
    root = Path(root).resolve()
    findings = []
    paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", root=root).split("\0")
    for relative in filter(None, paths):
        path = root / relative
        check_path(relative, relative, findings)
        if path.is_file():
            scan_blob(path.read_bytes(), relative, findings, private_values)
    blob_count = 0
    if history:
        for oid, relative, data in history_blobs(root):
            blob_count += 1
            label = f"history:{oid[:10]}:{relative}"
            check_path(relative, label, findings)
            scan_blob(data, label, findings, private_values)
        metadata = git("log", "--all", "--format=%H%n%an <%ae>%n%cn <%ce>%n%B", root=root)
        scan_blob(metadata.encode(), "history:commit-metadata", findings, private_values)
        if re.search(r"<[\w.+-]+@(?!users\.noreply\.github\.com)[\w.-]+>", metadata):
            findings.append({"file": "history:commit-metadata", "kind": "personal author email"})
        for relative in set(git("log", "--all", "--format=", "--name-only", "-z", root=root).split("\0")):
            relative = relative.strip("\n")
            if relative:
                check_path(relative, f"history:path:{relative}", findings)
    # Even a filename might contain private text. Never print that text in a report.
    for finding in findings:
        for value in private_values:
            finding["file"] = finding["file"].replace(value, "[REDACTED]")
    return {
        "files": len(list(filter(None, paths))),
        "history_objects": blob_count,
        "findings": findings,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--private-credentials", type=Path, action="append", default=[],
                        help="Optional local credential file for exact-value checks; values are never printed")
    args = parser.parse_args()
    try:
        values = set()
        for path in args.private_credentials:
            values.update(private_values_from_file(path))
        result = scan(not args.no_history, args.root, values)
    except Exception:
        print(json.dumps({"error": "Public scan failed; no secret details are printed"}))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["findings"]))
