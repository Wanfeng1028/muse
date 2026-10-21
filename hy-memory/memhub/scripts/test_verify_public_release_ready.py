import json
import os
from pathlib import Path

from verify_public_release_ready import MACOS_PUBLIC_CHECKS, evaluate_public_release


def write_public_fixture(root: Path) -> str:
    for relative in (
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
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
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "release": {
                    "build_number": 8,
                    "macos_min_version": "13.0",
                    "app_update": "manual",
                    "runtime_manifest_schema": 1,
                    "cli_protocol": 1,
                    "cli_supported_runtime_protocol": {"min": 1, "max": 1},
                    "runtime_protocol": 1,
                    "runtime_supported_cli_protocol": {"min": 1, "max": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "apps/core").mkdir(parents=True)
    (root / "apps/core/pyproject.toml").write_text(
        '[project]\nname = "one-memory"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "apps/core/uv.lock").write_text(
        '[[package]]\nname = "one-memory"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "SBOM.spdx.json").write_text(
        json.dumps({"packages": [{"name": "one-memory"}]}),
        encoding="utf-8",
    )
    workflow = root / ".github/workflows/release.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "ubuntu-24.04-arm\nmacos-15\nmacos-15-intel\nMemHub.dmg\n"
        "build-macos-release.mjs\nnotarize-macos-release.mjs\n"
        "verify_public_release_ready.py\nverify-published-release.mjs\n"
        "publish-cli-after-release.mjs\n",
        encoding="utf-8",
    )
    receipts = []
    for arch in ("arm64", "x64"):
        receipt = root / f"macos-public-gate-{arch}.json"
        receipt.write_text(
            json.dumps(
                {
                    "platform": "darwin",
                    "arch": arch,
                    "checks": [
                        {"name": name, "status": "pass"}
                        for name in MACOS_PUBLIC_CHECKS
                    ],
                }
            ),
            encoding="utf-8",
        )
        receipts.append(str(receipt))
    return os.pathsep.join(receipts)


def test_accepts_a_public_tree_with_all_external_evidence(tmp_path: Path) -> None:
    receipt = write_public_fixture(tmp_path)
    result = evaluate_public_release(
        tmp_path,
        {
            "MEMHUB_PUBLIC_NPM_PACKAGE": "@memhub/cli",
            "MEMHUB_PUBLIC_REPOSITORY": "memhub-ai/memhub",
            "MEMHUB_PUBLIC_BUNDLE_ID": "org.memhub.desktop",
            "MEMHUB_MACOS_PUBLIC_GATE_RECEIPT": receipt,
        },
        "git@github.com:memhub-ai/memhub.git",
    )
    assert result["ready"] is True
    assert result["blockers"] == []


def test_accepts_release_workflow_from_the_monorepo_root(tmp_path: Path) -> None:
    memhub = tmp_path / "memhub"
    receipt = write_public_fixture(memhub)
    workflow = memhub / ".github/workflows/release.yml"
    root_workflow = tmp_path / ".github/workflows/release.yml"
    root_workflow.parent.mkdir(parents=True)
    workflow.replace(root_workflow)

    result = evaluate_public_release(
        memhub,
        {
            "MEMHUB_PUBLIC_NPM_PACKAGE": "memhub-cli",
            "MEMHUB_PUBLIC_REPOSITORY": "Tencent-Hunyuan/Hy-Memory",
            "MEMHUB_PUBLIC_BUNDLE_ID": "io.github.tencent-hunyuan.hy-memory.memhub",
            "MEMHUB_MACOS_PUBLIC_GATE_RECEIPT": receipt,
        },
        "https://github.com/Tencent-Hunyuan/Hy-Memory.git",
    )

    assert result["ready"] is True
    assert result["blockers"] == []


def test_rejects_internal_release_coordination_files(tmp_path: Path) -> None:
    receipt = write_public_fixture(tmp_path)
    (tmp_path / "release_todo.md").write_text("internal release checklist\n")
    result = evaluate_public_release(
        tmp_path,
        {
            "MEMHUB_PUBLIC_NPM_PACKAGE": "memhub-cli",
            "MEMHUB_PUBLIC_REPOSITORY": "Tencent-Hunyuan/Hy-Memory",
            "MEMHUB_PUBLIC_BUNDLE_ID": "io.github.tencent-hunyuan.hy-memory.memhub",
            "MEMHUB_MACOS_PUBLIC_GATE_RECEIPT": receipt,
        },
        "https://github.com/Tencent-Hunyuan/Hy-Memory.git",
    )

    assert result["ready"] is False
    assert "internal_process_file_present:release_todo.md" in result["blockers"]


def test_reports_private_dependencies_and_missing_public_evidence(tmp_path: Path) -> None:
    write_public_fixture(tmp_path)
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "version": "0.1.0-internal.1",
                "release": {
                    "build_number": 1,
                    "macos_min_version": "13.0",
                    "app_update": "manual",
                    "runtime_manifest_schema": 1,
                    "cli_protocol": 1,
                    "cli_supported_runtime_protocol": {"min": 1, "max": 1},
                    "runtime_protocol": 1,
                    "runtime_supported_cli_protocol": {"min": 1, "max": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "apps/core/pyproject.toml").write_text(
        'dependencies = ["hy-memory-internal"]\nurl = "https://mirrors.tencent.com/pypi/simple/"\n',
        encoding="utf-8",
    )
    private_origin = "git@git" + "." + "woa" + "." + "com:private/repo.git"
    result = evaluate_public_release(tmp_path, {}, private_origin)
    assert result["ready"] is False
    assert "internal_version_not_public" in result["blockers"]
    assert "internal_python_dependency:apps/core/pyproject.toml" in result["blockers"]
    assert "internal_python_index:apps/core/pyproject.toml" in result["blockers"]
    assert "internal_origin_not_public" in result["blockers"]
    assert "public_npm_package_missing_or_invalid" in result["blockers"]
    assert "public_repository_missing_or_invalid" in result["blockers"]
    assert "public_bundle_id_missing_or_invalid" in result["blockers"]
    assert "macos_public_gate_receipt_missing" in result["blockers"]


def test_source_only_gate_defers_but_does_not_fabricate_macos_evidence(
    tmp_path: Path,
) -> None:
    receipt = write_public_fixture(tmp_path)
    environment = {
        "MEMHUB_PUBLIC_NPM_PACKAGE": "@memhub/cli",
        "MEMHUB_PUBLIC_REPOSITORY": "memhub-ai/memhub",
        "MEMHUB_PUBLIC_BUNDLE_ID": "org.memhub.desktop",
        "MEMHUB_MACOS_PUBLIC_GATE_RECEIPT": receipt + os.pathsep + str(tmp_path / "missing.json"),
    }
    source_only = evaluate_public_release(
        tmp_path,
        environment,
        "git@github.com:memhub-ai/memhub.git",
        require_macos_receipt=False,
    )
    assert source_only["ready"] is True
    final = evaluate_public_release(
        tmp_path,
        environment,
        "git@github.com:memhub-ai/memhub.git",
        require_macos_receipt=True,
    )
    assert final["ready"] is False
    assert "macos_public_gate_receipt_missing" in final["blockers"]
