#!/usr/bin/env python3
"""Fail-closed public release gate.

Internal testing and public distribution are deliberately separate states. This
gate checks the source tree plus externally supplied public identities/evidence;
it must remain red while private dependencies, private remotes, or unsigned
macOS artifacts are still required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Mapping


REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "SBOM.spdx.json",
    "README.md",
    "docs/INSTALLATION.md",
    "scripts/audit_core_test_design.py",
    "scripts/build-release-assets.mjs",
    "scripts/generate_core_test_index.py",
    "scripts/summarize_core_test_report.py",
    "scripts/verify-release-version.mjs",
    "scripts/verify-published-release.mjs",
    "scripts/publish-cli-after-release.mjs",
    "scripts/export_public_snapshot.py",
    "scripts/verify_public_snapshot.py",
    "scripts/platform/macos/build-macos-release.mjs",
    "scripts/platform/macos/notarize-macos-release.mjs",
    "apps/desktop/entitlements/entitlements.mac.plist",
    "apps/desktop/entitlements/entitlements.mac.inherit.plist",
)

FORBIDDEN_PUBLIC_PROCESS_FILES = (
    "OPEN_SOURCE_TODO.md",
    "release_todo.md",
    "openclaw-hy-memory-1.0.0.tgz",
    "memhub/docs/mvp/PREREQUISITES.md",
    "memhub/docs/mvp/SCOPE.md",
    "memhub/docs/mvp/packaging-smoke-checklist.md",
)

MACOS_PUBLIC_CHECKS = frozenset(
    {
        "public_gate_codesign_verify",
        "public_gate_hardened_runtime",
        "public_gate_developer_id_signature",
        "public_gate_gatekeeper_accepts",
        "public_gate_notarization_ticket",
        "public_gate_hardened_bundle_still_launches",
        "public_gate_dmg_codesign_verify",
        "public_gate_dmg_gatekeeper_accepts",
        "public_gate_dmg_notarization_ticket",
    }
)


def _origin(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _release_workflow(root: Path) -> Path | None:
    for candidate in (
        root / ".github/workflows/release.yml",
        root.parent / ".github/workflows/release.yml",
    ):
        if candidate.is_file():
            return candidate
    return None


def _check_macos_receipt(path_value: str | None) -> list[str]:
    if not path_value:
        return ["macos_public_gate_receipt_missing"]
    paths = [
        Path(value).expanduser().resolve()
        for value in path_value.split(os.pathsep)
        if value.strip()
    ]
    failures: list[str] = []
    arches: set[str] = set()
    for path in paths:
        if not path.is_file():
            failures.append("macos_public_gate_receipt_missing")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failures.append("macos_public_gate_receipt_invalid")
            continue
        if not isinstance(value, dict) or value.get("platform") != "darwin":
            failures.append("macos_public_gate_receipt_invalid")
            continue
        arch = value.get("arch")
        if arch not in {"arm64", "x64"} or arch in arches:
            failures.append("macos_public_gate_receipt_invalid")
            continue
        arches.add(arch)
        entries = value.get("checks", value.get("results", []))
        if not isinstance(entries, list):
            failures.append("macos_public_gate_receipt_invalid")
            continue
        statuses = {
            entry.get("name"): entry.get("status", entry.get("result"))
            for entry in entries
            if isinstance(entry, dict)
        }
        for name in sorted(MACOS_PUBLIC_CHECKS):
            if statuses.get(name) != "pass":
                failures.append(f"macos_gate_not_passed:{arch}:{name}")
    for arch in ("arm64", "x64"):
        if arch not in arches:
            failures.append(f"macos_public_gate_receipt_missing:{arch}")
    return failures


def evaluate_public_release(
    root: Path,
    environment: Mapping[str, str] | None = None,
    origin_url: str | None = None,
    require_macos_receipt: bool = True,
) -> dict[str, object]:
    env = environment or os.environ
    blockers: list[str] = []
    repository_root = root.parent if root.name == "memhub" else root
    for relative in FORBIDDEN_PUBLIC_PROCESS_FILES:
        if (repository_root / relative).exists():
            blockers.append(f"internal_process_file_present:{relative}")
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            blockers.append(f"required_file_missing:{relative}")

    package_path = root / "package.json"
    package: dict[str, object] = {}
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except ValueError:
            blockers.append("root_package_invalid")
    version = package.get("version")
    build_number = (
        package.get("release", {}).get("build_number")
        if isinstance(package.get("release"), dict)
        else None
    )
    if not isinstance(version, str) or not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?",
        version,
    ):
        blockers.append("release_version_invalid")
    elif "-internal" in version:
        blockers.append("internal_version_not_public")
    if not isinstance(build_number, int) or isinstance(build_number, bool) or build_number < 0:
        blockers.append("release_build_number_invalid")
    release_contract = package.get("release") if isinstance(package.get("release"), dict) else {}
    if release_contract.get("macos_min_version") != "13.0":
        blockers.append("macos_minimum_version_not_frozen")
    if release_contract.get("app_update") != "manual":
        blockers.append("macos_update_mode_not_frozen")
    expected_protocol_contract = {
        "runtime_manifest_schema": 1,
        "cli_protocol": 1,
        "cli_supported_runtime_protocol": {"min": 1, "max": 1},
        "runtime_protocol": 1,
        "runtime_supported_cli_protocol": {"min": 1, "max": 1},
    }
    for key, expected in expected_protocol_contract.items():
        if release_contract.get(key) != expected:
            blockers.append(f"release_protocol_contract_invalid:{key}")

    core_files = (
        root / "apps/core/pyproject.toml",
        root / "apps/core/uv.lock",
    )
    for file in core_files:
        if not file.is_file():
            blockers.append(f"core_dependency_file_missing:{file.relative_to(root)}")
            continue
        text = file.read_text(encoding="utf-8")
        if "hy-memory-internal" in text:
            blockers.append(f"internal_python_dependency:{file.relative_to(root)}")
        if "mirrors.tencent.com" in text:
            blockers.append(f"internal_python_index:{file.relative_to(root)}")

    public_package = env.get("MEMHUB_PUBLIC_NPM_PACKAGE", "").strip()
    if not re.fullmatch(r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+", public_package):
        blockers.append("public_npm_package_missing_or_invalid")
    elif public_package.startswith("@tencent/"):
        blockers.append("internal_npm_scope_not_public")

    public_repository = env.get("MEMHUB_PUBLIC_REPOSITORY", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", public_repository):
        blockers.append("public_repository_missing_or_invalid")

    public_bundle_id = env.get("MEMHUB_PUBLIC_BUNDLE_ID", "").strip()
    if (
        not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9.-]+[A-Za-z0-9]", public_bundle_id
        )
        or "." not in public_bundle_id
    ):
        blockers.append("public_bundle_id_missing_or_invalid")
    elif public_bundle_id.startswith("com.tencent."):
        blockers.append("internal_bundle_id_not_public")

    resolved_origin = origin_url if origin_url is not None else _origin(root)
    if not resolved_origin:
        blockers.append("origin_remote_missing")
    elif ("git" + "." + "woa" + "." + "com") in resolved_origin:
        blockers.append("internal_origin_not_public")
    elif public_repository and public_repository not in resolved_origin:
        blockers.append("origin_does_not_match_public_repository")

    workflow_path = _release_workflow(root)
    if workflow_path is None:
        blockers.append("release_workflow_missing")
    else:
        workflow = workflow_path.read_text(encoding="utf-8")
        for marker, code in (
            ("ubuntu-24.04-arm", "release_workflow_missing_linux_arm64"),
            ("verify-published-release.mjs", "release_workflow_missing_remote_verification"),
            ("publish-cli-after-release.mjs", "release_workflow_missing_publish_gate"),
            ("verify_public_release_ready.py", "release_workflow_missing_public_gate"),
            ("macos-15-intel", "release_workflow_missing_macos_x64"),
            ("build-macos-release.mjs", "release_workflow_missing_macos_build"),
            ("notarize-macos-release.mjs", "release_workflow_missing_macos_notarization"),
        ):
            if marker not in workflow:
                blockers.append(code)
        if "macos-" not in workflow or ".dmg" not in workflow:
            blockers.append("release_workflow_missing_macos_artifacts")

    if require_macos_receipt:
        blockers.extend(
            _check_macos_receipt(env.get("MEMHUB_MACOS_PUBLIC_GATE_RECEIPT"))
        )

    sbom_path = root / "SBOM.spdx.json"
    if sbom_path.is_file():
        try:
            sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        except ValueError:
            blockers.append("sbom_invalid")
        else:
            package_names = {
                entry.get("name")
                for entry in sbom.get("packages", [])
                if isinstance(entry, dict)
            }
            if "hy-memory-internal" in package_names:
                blockers.append("sbom_contains_internal_dependency")

    blockers = sorted(set(blockers))
    return {
        "schema_version": 1,
        "product": "memhub-public-release-readiness",
        "ready": not blockers,
        "version": version if isinstance(version, str) else None,
        "build_number": build_number if isinstance(build_number, int) else None,
        "public_npm_package": public_package or None,
        "public_repository": public_repository or None,
        "public_bundle_id": public_bundle_id or None,
        "origin": resolved_origin,
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    receipt = evaluate_public_release(
        root, require_macos_receipt=not args.source_only
    )
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    elif receipt["ready"]:
        print("public release readiness gate passed")
    else:
        for blocker in receipt["blockers"]:
            print(blocker)
    if not receipt["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
