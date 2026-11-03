"""A7-03: the fault-injection list, as data you can assert against.

The objective names six faults: HY fails before, HY call interrupted, crash
after HY succeeded but before the write landed, MySQL restart, disk full, and
file rotation. Listing them in prose is how one gets skipped. Here they are
data with a required outcome each, so "did we cover them?" is a test rather
than a memory exercise.

The outcome for each is not "the system works". It is the specific property
that must hold, because several of these faults have a *tempting* wrong answer:

- `hy_succeeded_then_crash`: the tempting answer is to retry. That duplicates
  the memory (A0-03: no idempotency key). The required outcome is `inquire`,
  and the reconciliation must show the job as `unknown` rather than `failed`.
- `disk_full`: the tempting answer is to keep trying. The required outcome is
  to refuse writes while the reserve is breached, because a half-applied
  schema change is worse than a pause.
- `file_rotation`: the tempting answer is to resume from the old byte offset.
  The required outcome is to re-resolve identity, because the bytes at that
  offset now belong to a different file.
"""

from __future__ import annotations

from dataclasses import dataclass


class Outcome:
    """What must hold after a fault."""

    #: Nothing was sent, so the write may simply be retried.
    RETRY = "retry"
    #: HY may hold the result; ask before deciding.
    INQUIRE = "inquire"
    #: The job must be recorded as unknown, never silently failed.
    UNKNOWN_RECORDED = "unknown_recorded"
    #: Refuse writes until the reserve is restored.
    REFUSE_WRITES = "refuse_writes"
    #: Re-resolve file identity instead of trusting the old offset.
    RE_RESOLVE_IDENTITY = "re_resolve_identity"
    #: Recover by re-running migrations and re-checking health.
    RECOVER_BY_REPLAY = "recover_by_replay"


@dataclass(frozen=True)
class Fault:
    name: str
    outcome: str
    #: Why this outcome and not the tempting one.
    rationale: str


FAULTS: tuple[Fault, ...] = (
    Fault(
        "hy_fails_before_send",
        Outcome.RETRY,
        "nothing reached HY, so a retry cannot duplicate anything",
    ),
    Fault(
        "hy_call_interrupted",
        Outcome.INQUIRE,
        "the request may have been applied; retrying blind duplicates it",
    ),
    Fault(
        "hy_succeeded_then_crash",
        Outcome.UNKNOWN_RECORDED,
        "the memory may exist; recording failure would lose it silently",
    ),
    Fault(
        "mysql_restart",
        Outcome.RECOVER_BY_REPLAY,
        "schema and migrations are idempotent, so replaying is safe; "
        "guessing at partial state is not",
    ),
    Fault(
        "disk_full",
        Outcome.REFUSE_WRITES,
        "a half-applied change is worse than a pause",
    ),
    Fault(
        "file_rotation",
        Outcome.RE_RESOLVE_IDENTITY,
        "the old offset now points into a different file",
    ),
)


def names() -> tuple[str, ...]:
    return tuple(fault.name for fault in FAULTS)


def outcome_of(name: str) -> str | None:
    return next((fault.outcome for fault in FAULTS if fault.name == name), None)


REQUIRED_NAMES: tuple[str, ...] = (
    "hy_fails_before_send",
    "hy_call_interrupted",
    "hy_succeeded_then_crash",
    "mysql_restart",
    "disk_full",
    "file_rotation",
)


def missing() -> tuple[str, ...]:
    """Required faults with no entry. Empty means the matrix is complete."""
    present = set(names())
    return tuple(name for name in REQUIRED_NAMES if name not in present)
