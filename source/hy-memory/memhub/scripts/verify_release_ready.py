#!/usr/bin/env python3

import json
import struct
import subprocess
from pathlib import Path

REQUIRED_RELEASE_FILES = (
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
)

ASAR_GLOBS = (
    "apps/desktop/release/*/*.app/Contents/Resources/app.asar",
    "apps/desktop/release-preview/*/*.app/Contents/Resources/app.asar",
)


def asar_entries(archive: Path) -> list[str]:
    """List the paths inside an asar without needing Node on the machine."""
    with archive.open("rb") as handle:
        prefix = handle.read(16)
        if len(prefix) < 16:
            raise ValueError("asar header is truncated")
        # pickle framing: 4, header payload size, header size, json size
        _padding, _payload, _header, json_size = struct.unpack("<IIII", prefix)
        header = json.loads(handle.read(json_size).decode("utf-8"))

    paths: list[str] = []

    def walk(node: dict, prefix: str) -> None:
        for name, child in node.get("files", {}).items():
            path = f"{prefix}/{name}"
            if "files" in child:
                walk(child, path)
            else:
                paths.append(path)

    walk(header, "")
    return paths


def scan_packaged_app(root: Path) -> list[str]:
    """Reject a bundle that ships build-time sources next to the runtime bundle.

    The desktop entry point is bundled by tsup and requires nothing but Node
    builtins and electron, so any workspace TypeScript inside the archive means
    the packaging rules regressed. That has previously shipped test files and
    stale sources into a real installer.
    """
    failures: list[str] = []
    for pattern in ASAR_GLOBS:
        for archive in sorted(root.glob(pattern)):
            label = archive.relative_to(root)
            try:
                entries = asar_entries(archive)
            except (OSError, ValueError, KeyError) as error:
                failures.append(f"unreadable asar {label}: {error}")
                continue
            leaked = sorted(
                entry
                for entry in entries
                if entry.endswith((".ts", ".tsx"))
                and not entry.endswith((".d.ts", ".d.tsx"))
            )
            if leaked:
                failures.append(
                    f"packaged sources in {label}: {', '.join(leaked[:5])}"
                    + (f" (+{len(leaked) - 5} more)" if len(leaked) > 5 else "")
                )
            if not any(entry.endswith("dist/main.js") for entry in entries):
                failures.append(f"packaged app is missing dist/main.js: {label}")
    return failures


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures = [
        f"missing release file: {relative}"
        for relative in REQUIRED_RELEASE_FILES
        if not (root / relative).is_file()
    ]
    failures.extend(scan_packaged_app(root))
    if (root / "LICENSE-PENDING.md").exists():
        failures.append("project license is still pending")

    core_lock = root / "apps" / "core" / "uv.lock"
    if core_lock.is_file() and "mirrors.tencent.com" in core_lock.read_text(encoding="utf-8"):
        failures.append("Core lockfile still depends on the internal Tencent Python index")

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if remote.returncode != 0:
        failures.append("origin remote is not configured")

    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("release readiness gate passed")


if __name__ == "__main__":
    main()
