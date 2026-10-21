"""A5-05: backup verification, rotation, crash recovery and data-safety policy.

This is the engine-neutral home for the policies that must outlive the D56
MySQL removal. Disk budget (`disk_verdict`), uninstall that keeps data
(`uninstall_plan`) and upgrade gating (`may_upgrade`) used to live in
`mysql_lifecycle` only because that module was written first; they say nothing
about MySQL, and deleting that module would have deleted them.

What is here is the part that was genuinely missing:

- **A backup is only a backup if it has been restored.** `may_upgrade` already
  demands a verified-restorable backup, but nothing decided *when* a backup
  becomes verified. That decision lives here.
- **Rotation needs a keep-set, not "delete the oldest".** Keeping the newest N
  plus the last known-good is what makes a rotation survivable.
- **Crash recovery must distinguish resume from restart.** A write that HY may
  already hold must not be re-sent (A0-03: no idempotency key).
- **Log rotation must never delete the log being written.**
"""

from __future__ import annotations

from dataclasses import dataclass

#: Reserve headroom so a full disk does not corrupt the data directory.
MIN_FREE_BYTES = 1 << 30  # 1 GiB


@dataclass(frozen=True)
class DiskState:
    total_bytes: int
    free_bytes: int
    data_bytes: int


def disk_verdict(state: DiskState) -> tuple[bool, str]:
    """Whether writes may continue, and why not when they may not.

    Refusing to write while nearly full is better than letting the store fail
    mid-transaction: a half-applied schema change is far worse than a pause.
    """
    if state.free_bytes < MIN_FREE_BYTES:
        return False, f"free space {state.free_bytes} below {MIN_FREE_BYTES} byte reserve"
    projected = state.free_bytes - state.data_bytes
    if projected < MIN_FREE_BYTES:
        return False, "a full data copy would breach the reserve"
    return True, ""


@dataclass(frozen=True)
class UninstallPlan:
    #: Paths removed with the program.
    removed: tuple[str, ...]
    #: Paths deliberately kept. The user's memory is theirs, not the app's.
    preserved: tuple[str, ...]


def uninstall_plan(data_dir: str) -> UninstallPlan:
    """What an uninstall removes, and what it must never remove.

    "Uninstall retains data" is a product promise: removing the program must not
    delete a person's memory. The backup directory is preserved too, so a later
    reinstall can restore rather than starting from nothing.
    """
    return UninstallPlan(
        removed=(
            f"{data_dir}/mysql/bin",
            f"{data_dir}/mysql/lib",
            f"{data_dir}/mysql/share",
            f"{data_dir}/runtime",
            f"{data_dir}/runtime.json",
            f"{data_dir}/runtime-token",
        ),
        preserved=(
            f"{data_dir}/one-memory.sqlite3",
            f"{data_dir}/backups",
            f"{data_dir}/migrations",
            # Kept even though D56 no longer uses it: preserving a directory is
            # the safe direction, and a rollback to a MySQL build must not find
            # its data deleted by an uninstall under the other engine.
            f"{data_dir}/mysql/data",
        ),
    )


@dataclass(frozen=True)
class BackupState:
    exists: bool
    #: Backup must be verified restorable, not merely present.
    verified_restorable: bool
    #: Schema the backup was taken from, so a downgrade is detected.
    schema_version: int


class UpgradeRejected(ValueError):
    """An upgrade was attempted without a restorable backup."""


def may_upgrade(*, backup: BackupState, current_schema: int, target_schema: int) -> bool:
    """Whether an upgrade may proceed.

    Two refusals, both deliberate:

    - No verified-restorable backup. The architecture requires an upgrade to be
      recoverable; a backup that exists but was never restored-tested is not
      evidence of recoverability.
    - A target older than the current schema. "Rolling back the program must
      not downgrade an already-upgraded data schema" — a downgrade would be
      silently destructive.
    """
    if target_schema < current_schema:
        return False
    return backup.exists and backup.verified_restorable


def upgrade_plan(*, backup: BackupState, current_schema: int, target_schema: int) -> list[str]:
    """The ordered actions for an upgrade, or raise if it must not happen."""
    if not may_upgrade(backup=backup, current_schema=current_schema, target_schema=target_schema):
        raise UpgradeRejected(
            "upgrade requires a verified-restorable backup and a non-downgrading target"
        )
    return [
        "stop_gateway",
        "stop_server",
        "take_backup",
        "install_new_version",
        "start_store",
        "run_migrations",
        "start_server",
        "start_gateway",
    ]


@dataclass(frozen=True)
class Backup:
    name: str
    #: Bytes, for rotation accounting.
    size_bytes: int
    #: True once a restore from this backup has actually been performed.
    verified: bool = False
    #: Order in which backups were created; higher is newer.
    sequence: int = 0


def is_usable(backup: Backup) -> bool:
    """Whether this backup may be relied on.

    Unverified backups are not usable here on purpose: promotion to
    `verified_restorable` in `mysql_lifecycle.BackupState` is what upgrades are
    gated on, and a backup counts as verified only after a real restore.
    """
    return backup.verified and backup.size_bytes > 0


def plan_rotation(
    backups: list[Backup],
    *,
    keep_newest: int,
) -> tuple[list[Backup], str]:
    """Choose what to delete. Returns (to_delete, reason_kept_last_good).

    The rule is "keep the newest N, plus always the newest verified one". The
    second half matters: if all N newest are unverified, deleting by age alone
    would throw away the only restorable copy.
    """
    if keep_newest < 0:
        raise ValueError("keep_newest must not be negative")
    if not backups:
        return [], "no backups"

    ordered = sorted(backups, key=lambda item: item.sequence, reverse=True)
    keep = {item.name for item in ordered[:keep_newest]}

    newest_good = next((item for item in ordered if is_usable(item)), None)
    if newest_good is not None:
        keep.add(newest_good.name)

    to_delete = [item for item in ordered if item.name not in keep]
    reason = (
        f"kept newest {keep_newest} and newest verified {newest_good.name}"
        if newest_good is not None
        else f"kept newest {keep_newest}; no verified backup exists to protect"
    )
    return to_delete, reason


class RecoveryAction:
    """What to do with an interrupted write."""

    #: Ask HY whether it holds the result, then decide. Never re-send blind.
    INQUIRE = "inquire"
    #: Safe to re-run: nothing was sent.
    RETRY = "retry"
    #: Already known to have landed; record it and stop.
    RESOLVE = "resolve"


def recovery_action(*, sent_to_hy: bool, outcome_known: bool) -> str:
    """Decide how to recover an interrupted write.

    The dangerous case is `sent_to_hy` with an unknown outcome. Retrying there
    duplicates the memory (HY has no idempotency key, A0-03), so the only safe
    action is to inquire first. Any rule that returns RETRY for that case is a
    correctness bug, not an optimisation.
    """
    if outcome_known:
        return RecoveryAction.RESOLVE
    if sent_to_hy:
        return RecoveryAction.INQUIRE
    return RecoveryAction.RETRY


def plan_log_retention(
    logs: list[tuple[str, int]],
    *,
    keep_bytes: int,
    active_name: str | None = None,
) -> list[str]:
    """Log files to delete, oldest first, never the active one.

    `active_name` is excluded explicitly. A rotation that deleted the file
    currently being written would lose the record of the failure that prompted
    the rotation in the first place.
    """
    if keep_bytes < 0:
        raise ValueError("keep_bytes must not be negative")

    candidates = [item for item in logs if item[0] != active_name]
    # Oldest first: caller-supplied order is trusted as creation order.
    ordered = list(candidates)

    total = sum(size for _, size in ordered)
    to_delete: list[str] = []
    for name, size in ordered:
        if total <= keep_bytes:
            break
        to_delete.append(name)
        total -= size
    return to_delete
