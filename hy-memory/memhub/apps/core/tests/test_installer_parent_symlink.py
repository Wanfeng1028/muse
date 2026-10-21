"""The owned-file installer must not follow a parent directory swapped for a symlink."""

from __future__ import annotations

from pathlib import Path

import pytest

from one_memory.imports.installer import (
    InstallAction,
    InstallState,
    TransactionalOwnedFileInstaller,
)

MARKER = b"# one-memory-owned\n"


def _installer(root: Path, backup: Path) -> TransactionalOwnedFileInstaller:
    return TransactionalOwnedFileInstaller(
        source_id="fixture",
        allowed_root=root,
        relative_path=Path("nested/config.json"),
        content=MARKER + b'{"enabled":true}\n',
        backup_root=backup,
        owner_marker=MARKER,
    )


def test_installer_refuses_apply_through_a_replaced_parent_directory(tmp_path) -> None:
    root = tmp_path / "allowed"
    (root / "nested").mkdir(parents=True)
    installer = _installer(root, tmp_path / "backups")
    plan = installer.plan()

    moved = tmp_path / "moved"
    (root / "nested").rename(moved)
    (root / "nested").symlink_to(moved, target_is_directory=True)

    receipt = installer.apply(plan)

    assert receipt.state is InstallState.UNAVAILABLE
    assert receipt.reason_code == "installer_target_escaped_allowed_root"
    assert receipt.observed_hash is None
    assert not (moved / "config.json").exists(), "apply wrote outside the allowed root"


def test_installer_plan_does_not_read_an_escaped_target(tmp_path) -> None:
    root = tmp_path / "allowed"
    (root / "nested").mkdir(parents=True)
    outside = tmp_path / "moved"
    outside.mkdir()
    (outside / "config.json").write_bytes(MARKER + b'{"outside":true}\n')
    installer = _installer(root, tmp_path / "backups")

    (root / "nested").rmdir()
    (root / "nested").symlink_to(outside, target_is_directory=True)

    plan = installer.plan()

    assert plan.action is InstallAction.CONFLICT
    assert plan.reason_code == "installer_target_escaped_allowed_root"
    assert plan.before_hash is None


def test_installer_refuses_a_symlinked_target_parent_at_construction(tmp_path) -> None:
    root = tmp_path / "allowed"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes allowed root"):
        _installer(root, tmp_path / "backups")
