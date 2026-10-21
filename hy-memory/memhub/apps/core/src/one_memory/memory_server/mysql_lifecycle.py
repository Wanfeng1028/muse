"""A1-07: the policy Runtime applies when managing the bundled MySQL.

This module is deliberately pure. Starting a real `mysqld` is platform work
(A1-07's later half), but the *decisions* around it are not, and those are
where the damaging mistakes live: starting Core before migrations have run,
upgrading without a restorable backup, filling the disk, or deleting the user's
memory during uninstall.

The ordering rule is the architecture's own, and it is strict:

    MySQL ready -> schema migration -> Memory Server -> Host Gateway

Each step is gated on the previous one *reporting* success, not merely having
been attempted. A step that "probably worked" is treated as failed, because the
cost of being wrong is a Core writing to a schema that does not exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

#: The data-safety policy (disk reserve, uninstall-keeps-data, upgrade gating)
#: is engine-neutral and now lives in `data_safety`, so the D56 removal of this
#: module cannot delete it. Re-exported here only so existing imports keep
#: working during the transition; new code should import from `data_safety`.
from one_memory.memory_server.data_safety import (
    MIN_FREE_BYTES,
    BackupState,
    DiskState,
    UninstallPlan,
    UpgradeRejected,
    disk_verdict,
    may_upgrade,
    uninstall_plan,
    upgrade_plan,
)

#: Re-exported so existing imports keep working during the D56 transition.
__all__ = [
    "MIN_FREE_BYTES",
    "BackupState",
    "DiskState",
    "SHUTDOWN_ORDER",
    "STARTUP_ORDER",
    "Step",
    "StepResult",
    "UninstallPlan",
    "UpgradeRejected",
    "can_start",
    "disk_verdict",
    "may_upgrade",
    "startup_plan",
    "uninstall_plan",
    "upgrade_plan",
]


class Step(StrEnum):
    MYSQL = "mysql"
    MIGRATION = "migration"
    SERVER = "server"
    GATEWAY = "gateway"


#: Fixed order. Never reordered: each step assumes the one before it holds.
STARTUP_ORDER: tuple[Step, ...] = (Step.MYSQL, Step.MIGRATION, Step.SERVER, Step.GATEWAY)

#: Shutdown is the reverse, so a gateway never outlives the server it calls.
SHUTDOWN_ORDER: tuple[Step, ...] = tuple(reversed(STARTUP_ORDER))


@dataclass(frozen=True)
class StepResult:
    step: Step
    ok: bool
    detail: str = ""


def startup_plan(results: dict[Step, bool]) -> tuple[list[Step], str | None]:
    """Which steps may run, and the first blocking failure if any.

    Returns (steps_to_run, blocking_reason). Steps are returned in order and
    stop before the first step that has not succeeded.
    """
    to_run: list[Step] = []
    for step in STARTUP_ORDER:
        if results.get(step, False):
            continue
        to_run.append(step)
        # The first unmet step gates everything after it, so planning stops
        # here rather than scheduling work that cannot succeed yet.
        break
    blocking = None
    for step in STARTUP_ORDER:
        if results.get(step) is False:
            blocking = f"{step.value} did not report success"
            break
    return to_run, blocking


def can_start(results: dict[Step, bool]) -> bool:
    """True only when every prerequisite reported success."""
    return all(results.get(step, False) for step in STARTUP_ORDER)


@dataclass
class StartupLedger:
    """Records what actually reported success, for restart recovery."""

    results: dict[Step, bool] = field(default_factory=dict)

    def record(self, result: StepResult) -> None:
        self.results[result.step] = result.ok

    @property
    def ready(self) -> bool:
        return can_start(self.results)
