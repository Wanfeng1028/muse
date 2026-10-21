from pathlib import Path

from one_memory.imports.installer import (
    InstallAction,
    InstallState,
    TransactionalOwnedFileInstaller,
)

MARKER = b"<!-- one-memory-owned -->"


def _installer(tmp_path, content: bytes) -> TransactionalOwnedFileInstaller:
    return TransactionalOwnedFileInstaller(
        source_id="cursor",
        allowed_root=tmp_path / "host",
        relative_path=Path("skills/one-memory/SKILL.md"),
        content=MARKER + b"\n" + content,
        backup_root=tmp_path / "receipts",
        owner_marker=MARKER,
    )


def test_installer_create_verify_and_rollback_is_transactional(tmp_path) -> None:
    installer = _installer(tmp_path, b"version 1")
    plan = installer.plan()

    assert plan.action is InstallAction.CREATE
    assert installer.apply(plan).state is InstallState.APPLIED
    assert installer.verify(plan).state is InstallState.VERIFIED
    assert installer.rollback(plan).state is InstallState.ROLLED_BACK
    assert plan.target_path.exists() is False


def test_installer_updates_owned_file_and_restores_backup(tmp_path) -> None:
    first = _installer(tmp_path, b"version 1")
    first_plan = first.plan()
    first.apply(first_plan)
    second = _installer(tmp_path, b"version 2")
    second_plan = second.plan()

    assert second_plan.action is InstallAction.UPDATE
    assert second.apply(second_plan).state is InstallState.APPLIED
    assert second.verify(second_plan).state is InstallState.VERIFIED
    assert second.rollback(second_plan).state is InstallState.ROLLED_BACK
    assert second_plan.target_path.read_bytes() == MARKER + b"\nversion 1"


def test_installer_refuses_unowned_or_changed_target(tmp_path) -> None:
    installer = _installer(tmp_path, b"version 1")
    installer.target.parent.mkdir(parents=True)
    installer.target.write_text("third-party content")

    conflict = installer.plan()

    assert conflict.action is InstallAction.CONFLICT
    assert installer.apply(conflict).state is InstallState.UNAVAILABLE
    assert installer.target.read_text() == "third-party content"

    installer.target.write_bytes(MARKER + b"\nold")
    plan = installer.plan()
    installer.target.write_bytes(MARKER + b"\nuser changed after plan")
    refused = installer.apply(plan)
    assert refused.state is InstallState.UNAVAILABLE
    assert refused.reason_code == "installer_target_changed_after_plan"
