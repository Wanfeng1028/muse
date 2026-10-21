"""A3-03: the seam every write entry converges on.

Manual notes, the five-minute scanner and hook events currently reach HY by
different routes. A3-03 requires them all to become "Evidence first, then one
queue". This module holds the *decision* each entry must make before enqueuing,
so the rules are stated once:

- a write is only submitted once there is Evidence to point at;
- the idempotency key is derived, not chosen, so a replay is recognisable;
- a live user-facing write outranks background work.

The routing decision is separate from the submission itself so it can be tested
without a queue, and so a caller cannot forget the Evidence rule by accident:
`plan_intake` refuses rather than returning an empty plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from one_memory.memory_server.contracts import BatchIdentity, WriteRequest


@dataclass(frozen=True)
class IntakeRequest:
    """What an entry knows before it can submit a write."""

    internal_session_id: str
    first_round: int
    last_round: int
    evidence_ids: list[str]
    #: True when a person is waiting on the result (a note, a live turn).
    live: bool = False


class IntakeRejected(ValueError):
    """The request cannot become a write as given."""


def plan_intake(request: IntakeRequest) -> WriteRequest:
    """Turn an entry's request into a `WriteRequest`, or refuse.

    Refusing on missing evidence is the point: a write with nothing to point at
    cannot be verified later, and silently allowing it would put unverifiable
    content into the memory store.
    """
    if not request.evidence_ids:
        raise IntakeRejected("a write needs evidence to point at")
    if request.first_round < 1 or request.last_round < request.first_round:
        raise IntakeRejected("round range must be ascending and start at 1 or later")

    batch = BatchIdentity(
        internal_session_id=request.internal_session_id,
        first_round=request.first_round,
        last_round=request.last_round,
    )
    return WriteRequest(
        internal_session_id=request.internal_session_id,
        batch_identity=batch,
        evidence_ids=list(request.evidence_ids),
        # Derived, not chosen: a replay re-derives the same key and is therefore
        # recognised instead of written twice.
        idempotency_key=batch.batch_id,
        priority="live" if request.live else "normal",
    )


def is_live(write: WriteRequest) -> bool:
    return write.priority == "live"
