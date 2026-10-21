#!/usr/bin/env python3
"""Fail closed when an exported public snapshot contains unsafe material."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MAX_PUBLIC_FILE_BYTES = 10 * 1024 * 1024
APPROVED_LARGE_FILES = {
    "apps/web/public/fonts/NotoSansSC-wght.ttf": {
        "bytes": 17_772_300,
        "sha256": "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da",
    }
}
SENSITIVE_NAMES = re.compile(
    r"(?:^|/)(?:\.env(?:\..*)?|id_(?:rsa|dsa|ecdsa|ed25519)|credentials(?:\..*)?|"
    r".*\.(?:pem|key|p12|pfx|jks|keystore))$",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
            r"[A-Za-z0-9+/=\r\n -]{64,}"
            r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
        ),
    ),
    ("npm_auth_token", re.compile(r"(?im)^\s*(?:[^\s=]+:)?_authToken\s*=")),
    ("npm_password", re.compile(r"(?im)^\s*(?:[^\s=]+:)?_password\s*=")),
    ("npm_basic_auth", re.compile(r"(?im)^\s*(?:[^\s=]+:)?_auth\s*=")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)
INTERNAL_MARKERS = (
    "git" + "." + "woa" + ".com",
    "." + "woa" + ".com",
    "." + "oa" + ".com",
    "mirrors" + "." + "tencent" + ".com",
)
INTERNAL_MARKER_POLICY_FILES = frozenset(
    {
        "scripts/test_verify_public_release_ready.py",
        "scripts/test_verify_public_snapshot.py",
        "scripts/verify_public_release_ready.py",
        "scripts/verify_public_snapshot.py",
        "scripts/verify_release_ready.py",
    }
)
TEXT_SUFFIXES = frozenset(
    {
        ".cjs",
        ".css",
        ".html",
        ".js",
        ".json",
        ".lock",
        ".md",
        ".mjs",
        ".npmrc",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_snapshot(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"public snapshot is not a directory: {root}")
    failures: list[str] = []
    files = 0
    total_bytes = 0
    approved_large: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = path.resolve(strict=False)
            if target != root and root not in target.parents:
                failures.append(f"public_symlink_escapes:{relative}")
            continue
        if not path.is_file():
            continue
        files += 1
        size = path.stat().st_size
        total_bytes += size
        if SENSITIVE_NAMES.search(relative) and relative != ".npmrc":
            failures.append(f"public_sensitive_filename:{relative}")
        if size > MAX_PUBLIC_FILE_BYTES:
            approved = APPROVED_LARGE_FILES.get(relative)
            if (
                approved is None
                or approved["bytes"] != size
                or approved["sha256"] != _sha256(path)
            ):
                failures.append(f"public_large_file_unapproved:{relative}:{size}")
            else:
                approved_large.append(relative)
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".npmrc":
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                failures.append(f"public_secret_pattern:{name}:{relative}")
        if relative not in INTERNAL_MARKER_POLICY_FILES:
            for marker in INTERNAL_MARKERS:
                if marker in content:
                    failures.append(f"public_internal_marker:{relative}")
    failures = sorted(set(failures))
    return {
        "schema_version": 1,
        "product": "memhub-public-snapshot-verification",
        "snapshot": str(root),
        "files": files,
        "bytes": total_bytes,
        "approved_large_files": approved_large,
        "failures": failures,
        "result": "passed" if not failures else "failed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = scan_snapshot(args.snapshot)
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    elif receipt["result"] == "passed":
        print(
            f"public snapshot verification passed: {receipt['files']} files, "
            f"{receipt['bytes']} bytes"
        )
    else:
        for failure in receipt["failures"]:
            print(failure)
    if receipt["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
