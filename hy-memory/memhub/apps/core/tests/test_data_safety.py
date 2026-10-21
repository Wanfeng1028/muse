"""A5-05: backup usability/rotation, crash recovery, log retention.

The three dangerous rules get explicit tests: an unverified backup must not be
relied on, an unknown-outcome write must not be retried, and the active log
must never be deleted.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.data_safety import (
    Backup,
    RecoveryAction,
    is_usable,
    plan_log_retention,
    plan_rotation,
    recovery_action,
    uninstall_plan,
)


def _backup(name: str, seq: int, *, verified: bool = True, size: int = 100) -> Backup:
    return Backup(name=name, size_bytes=size, verified=verified, sequence=seq)


def test_a_verified_backup_is_usable() -> None:
    assert is_usable(_backup("b1", 1)) is True


def test_an_unverified_backup_is_not_usable() -> None:
    """A backup counts only after a real restore has been performed."""
    assert is_usable(_backup("b1", 1, verified=False)) is False


def test_an_empty_backup_is_not_usable() -> None:
    assert is_usable(_backup("b1", 1, size=0)) is False


def test_rotation_keeps_the_newest() -> None:
    backups = [_backup("old", 1), _backup("new", 2)]
    to_delete, _ = plan_rotation(backups, keep_newest=1)
    assert [item.name for item in to_delete] == ["old"]


def test_rotation_protects_the_newest_verified_backup() -> None:
    """If all newest are unverified, deleting by age would drop the only
    restorable copy."""
    backups = [
        _backup("good", 1, verified=True),
        _backup("fresh", 2, verified=False),
        _backup("fresher", 3, verified=False),
    ]
    to_delete, reason = plan_rotation(backups, keep_newest=2)
    names = [item.name for item in to_delete]
    assert "good" not in names
    assert "good" in reason


def test_rotation_with_no_verified_backup_says_so() -> None:
    backups = [_backup("a", 1, verified=False)]
    to_delete, reason = plan_rotation(backups, keep_newest=0)
    assert [item.name for item in to_delete] == ["a"]
    assert "no verified" in reason


def test_rotation_of_nothing_is_nothing() -> None:
    assert plan_rotation([], keep_newest=3) == ([], "no backups")


def test_negative_keep_is_rejected() -> None:
    with pytest.raises(ValueError):
        plan_rotation([_backup("a", 1)], keep_newest=-1)


def test_known_outcome_is_resolved() -> None:
    assert recovery_action(sent_to_hy=True, outcome_known=True) == RecoveryAction.RESOLVE


def test_never_sent_may_be_retried() -> None:
    assert recovery_action(sent_to_hy=False, outcome_known=False) == RecoveryAction.RETRY


def test_sent_with_unknown_outcome_must_be_inquired_not_retried() -> None:
    """Retrying duplicates the memory: HY has no idempotency key (A0-03)."""
    action = recovery_action(sent_to_hy=True, outcome_known=False)
    assert action == RecoveryAction.INQUIRE
    assert action != RecoveryAction.RETRY


def test_logs_under_budget_are_kept() -> None:
    assert plan_log_retention([("a.log", 10)], keep_bytes=100) == []


def test_oldest_logs_are_deleted_first() -> None:
    logs = [("old.log", 60), ("new.log", 60)]
    assert plan_log_retention(logs, keep_bytes=100) == ["old.log"]


def test_the_active_log_is_never_deleted() -> None:
    """Deleting the file being written would lose the record of the failure
    that prompted the rotation."""
    logs = [("active.log", 90), ("old.log", 90)]
    assert plan_log_retention(logs, keep_bytes=10, active_name="active.log") == ["old.log"]


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(ValueError):
        plan_log_retention([("a.log", 1)], keep_bytes=-1)


def test_engine_neutral_policy_lives_outside_the_mysql_module() -> None:
    """The D56 MySQL removal must not take data-safety policy with it.

    Disk reserve, uninstall-keeps-data and upgrade gating say nothing about
    MySQL; they were only in `mysql_lifecycle` because it was written first.
    They now live here, so deleting that module (as the cleanup plans) cannot
    delete them.
    """
    from pathlib import Path

    import one_memory.memory_server.data_safety as safety

    source = Path(safety.__file__).read_text(encoding="utf-8")
    assert "def disk_verdict" in source
    assert "def uninstall_plan" in source
    assert "def may_upgrade" in source
    assert "def upgrade_plan" in source


def test_uninstall_always_preserves_the_database_and_backups() -> None:
    plan = uninstall_plan("/home/u/.one-memory")

    assert "/home/u/.one-memory/one-memory.sqlite3" in plan.preserved
    assert "/home/u/.one-memory/backups" in plan.preserved
    assert "/home/u/.one-memory/one-memory.sqlite3" not in plan.removed
