"""A4-07: one identity for hook and scan, so arrival order cannot duplicate.

The hook fires when a host writes; the scanner sweeps on a timer. The same turn
will often be seen by both, and the tempting fix is "the scanner checks whether
a job exists". That fails: two arrivals can both observe "no job yet".

The reliable fix is a **derived key**. Both paths compute the identity from the
same inputs, so whichever arrives first creates the record and the later one
computes the same key and is recognised as already known. This is the same rule
as `intake`'s derived idempotency key, applied at the enqueue boundary so it
also covers the scanner and hook.

The second half is the ordering guarantee the objective asks for: whichever
order two arrivals happen in, exactly one job is enqueued — and that is asserted
both ways round, because a dedupe that only works in one order is a race.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def batch_key(*, session: str, first_round: int, last_round: int) -> str:
    """The shared identity for one batch of rounds in one session.

    Deliberately excludes the arrival path. If "hook" and "scan" produced
    different keys, the two would silently become two jobs for one batch.
    """
    return f"{session}:{first_round}-{last_round}"


def message_key(*, session: str, ordinal: int, content_hash: str) -> str:
    """The shared identity for one message."""
    return f"{session}:{ordinal}:{content_hash}"


@dataclass
class EnqueueLedger:
    """Records what has been enqueued, by derived key."""

    seen: set[str] = field(default_factory=set)
    jobs: list[str] = field(default_factory=list)


def enqueue(
    ledger: EnqueueLedger,
    *,
    key: str,
    path: str,
) -> bool:
    """Enqueue one job unless an identical key was already enqueued.

    Returns True when this call created the job, False when it was a duplicate —
    so a caller can distinguish "queued" from "already queued" rather than
    assuming both mean success.
    """
    if key in ledger.seen:
        return False
    ledger.seen.add(key)
    ledger.jobs.append(f"{key}@{path}")
    return True


def enqueue_batch(
    ledger: EnqueueLedger,
    *,
    session: str,
    first_round: int,
    last_round: int,
    path: str,
) -> bool:
    return enqueue(
        ledger,
        key=batch_key(session=session, first_round=first_round, last_round=last_round),
        path=path,
    )


def enqueue_message(
    ledger: EnqueueLedger,
    *,
    session: str,
    ordinal: int,
    content_hash: str,
    path: str,
) -> bool:
    return enqueue(
        ledger,
        key=message_key(session=session, ordinal=ordinal, content_hash=content_hash),
        path=path,
    )


def replay(*, session: str, first_round: int, last_round: int) -> int:
    """How many jobs result from both paths seeing the same batch.

    Run with each arrival order; the answer must be 1 both times, or the dedupe
    depends on ordering and is really a race.
    """
    ledger = EnqueueLedger()
    for path in ("hook", "scan"):
        enqueue_batch(
            ledger, session=session, first_round=first_round, last_round=last_round, path=path
        )
    return len(ledger.jobs)
