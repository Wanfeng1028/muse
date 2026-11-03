"""A1-07: the decisions Runtime makes around the bundled MySQL.

These are policy, not platform, so they can be proven without a mysqld. The
failures they guard against are all silent-when-wrong: a Core that starts before
migrations, an upgrade with no restorable backup, a disk that fills mid-write,
or an uninstall that takes the user's memory with it.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.mysql_lifecycle import (
    MIN_FREE_BYTES,
    SHUTDOWN_ORDER,
    STARTUP_ORDER,
    BackupState,
    DiskState,
    StartupLedger,
    Step,
    StepResult,
    UninstallPlan,
    UpgradeRejected,
    can_start,
    disk_verdict,
    may_upgrade,
    startup_plan,
    uninstall_plan,
    upgrade_plan,
)


def _all(upto: int) -> dict[Step, bool]:
    """Mark the first `upto` steps as succeeded."""
    return {step: index < upto for index, step in enumerate(STARTUP_ORDER)}


def test_startup_order_is_mysql_then_migration_then_server_then_gateway() -> None:
    """The architecture's fixed order; Core must not precede migrations."""
    assert STARTUP_ORDER == (
        Step.MYSQL,
        Step.MIGRATION,
        Step.SERVER,
        Step.GATEWAY,
    )


def test_shutdown_is_the_reverse_of_startup() -> None:
    """A gateway must never outlive the server it calls."""
    assert tuple(reversed(STARTUP_ORDER)) == SHUTDOWN_ORDER


def test_nothing_runs_before_mysql() -> None:
    to_run, blocking = startup_plan({})
    assert to_run == [Step.MYSQL]
    assert blocking is None


def test_migration_is_next_after_mysql() -> None:
    to_run, _ = startup_plan(_all(1))
    assert to_run == [Step.MIGRATION]


def test_a_failed_step_blocks_later_steps() -> None:
    """'Probably worked' is treated as failed: writing to a missing schema is
    worse than refusing to start."""
    results = {Step.MYSQL: False}
    to_run, blocking = startup_plan(results)
    assert blocking is not None
    assert Step.MIGRATION not in to_run


def test_can_start_only_when_every_step_reported_success() -> None:
    assert can_start(_all(4)) is True
    assert can_start(_all(3)) is False


def test_partial_progress_is_not_ready() -> None:
    ledger = StartupLedger()
    ledger.record(StepResult(Step.MYSQL, True))
    ledger.record(StepResult(Step.MIGRATION, True))
    assert ledger.ready is False


def test_ledger_becomes_ready_after_all_steps() -> None:
    ledger = StartupLedger()
    for step in STARTUP_ORDER:
        ledger.record(StepResult(step, True))
    assert ledger.ready is True


def test_a_failed_step_unmakes_readiness() -> None:
    ledger = StartupLedger()
    for step in STARTUP_ORDER:
        ledger.record(StepResult(step, True))
    ledger.record(StepResult(Step.MIGRATION, False))
    assert ledger.ready is False


def _good_backup() -> BackupState:
    return BackupState(exists=True, verified_restorable=True, schema_version=1)


def test_upgrade_requires_a_verified_restorable_backup() -> None:
    """A backup that exists but was never restored-tested is not evidence."""
    assert may_upgrade(backup=_good_backup(), current_schema=1, target_schema=2) is True
    untested = BackupState(exists=True, verified_restorable=False, schema_version=1)
    assert may_upgrade(backup=untested, current_schema=1, target_schema=2) is False


def test_upgrade_requires_a_backup_to_exist() -> None:
    none = BackupState(exists=False, verified_restorable=False, schema_version=1)
    assert may_upgrade(backup=none, current_schema=1, target_schema=2) is False


def test_downgrading_the_schema_is_refused() -> None:
    """Rolling back the program must not downgrade an upgraded data schema."""
    assert may_upgrade(backup=_good_backup(), current_schema=3, target_schema=2) is False


def test_upgrade_plan_orders_backup_before_install() -> None:
    steps = upgrade_plan(backup=_good_backup(), current_schema=1, target_schema=2)
    assert steps.index("take_backup") < steps.index("install_new_version")
    assert steps.index("run_migrations") < steps.index("start_server")


def test_upgrade_plan_stops_services_before_touching_data() -> None:
    steps = upgrade_plan(backup=_good_backup(), current_schema=1, target_schema=2)
    assert steps[0] == "stop_gateway"
    assert steps.index("stop_server") < steps.index("take_backup")


def test_unsafe_upgrade_raises() -> None:
    none = BackupState(exists=False, verified_restorable=False, schema_version=1)
    with pytest.raises(UpgradeRejected):
        upgrade_plan(backup=none, current_schema=1, target_schema=2)


def test_writes_stop_below_the_reserve() -> None:
    state = DiskState(total_bytes=10 << 30, free_bytes=MIN_FREE_BYTES - 1, data_bytes=1)
    allowed, reason = disk_verdict(state)
    assert allowed is False
    assert "reserve" in reason


def test_a_copy_that_would_breach_the_reserve_is_refused() -> None:
    """A half-applied schema change is worse than a pause."""
    state = DiskState(
        total_bytes=10 << 30,
        free_bytes=MIN_FREE_BYTES + 10,
        data_bytes=100,
    )
    allowed, _ = disk_verdict(state)
    assert allowed is False


def test_healthy_disk_allows_writes() -> None:
    state = DiskState(total_bytes=10 << 30, free_bytes=5 << 30, data_bytes=1 << 30)
    allowed, reason = disk_verdict(state)
    assert allowed is True
    assert reason == ""


def test_uninstall_preserves_the_data_directory() -> None:
    """Removing the program must not delete a person's memory."""
    plan = uninstall_plan("/home/u/.one-memory")
    assert "/home/u/.one-memory/mysql/data" in plan.preserved
    assert "/home/u/.one-memory/mysql/data" not in plan.removed


def test_uninstall_preserves_backups_so_reinstall_can_restore() -> None:
    plan = uninstall_plan("/d")
    assert "/d/backups" in plan.preserved


def test_uninstall_removes_only_program_paths() -> None:
    plan = uninstall_plan("/d")
    assert isinstance(plan, UninstallPlan)
    assert all(
        item.startswith(("/d/mysql/bin", "/d/mysql/lib", "/d/mysql/share", "/d/runtime"))
        for item in plan.removed
    )
