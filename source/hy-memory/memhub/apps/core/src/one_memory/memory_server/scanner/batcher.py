"""A4-06: the five-round batch rule, as pure logic.

docs/ARCHITECTURE.md corrects the obvious-but-wrong version of this: the count
is per *session*, not per file. A session can span files and a file can hold
several sessions, so counting file rounds would batch unrelated conversations
together and split one conversation across batches.

The rule, per session:

1. Accumulate complete rounds parsed since the last committed point.
2. Every five complete rounds form one deterministic batch and are enqueued.
3. A remainder of 1-4 rounds is left for the next scan cycle.
4. If a session is idle and its remainder has been waiting across scans, flush
   it anyway, so a low-frequency conversation is not stuck forever at 3 rounds.
5. An incomplete trailing round never counts; it is not yet a round.

Only the caller commits cursor and evidence together; this module decides
*what* would be batched, and never writes anything.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Rounds per batch. Five is a product decision, not a tuning constant.
ROUNDS_PER_BATCH = 5

#: How many scan cycles a remainder may sit before being flushed anyway.
#: Without this, a conversation that stops at 3 rounds never gets written.
REMAINDER_MAX_PENDING_SCANS = 2


@dataclass(frozen=True)
class PendingRoundState:
    """What a session has accumulated but not yet enqueued."""

    pending_rounds: int = 0
    #: How many scan cycles the remainder has survived.
    pending_since_scans: int = 0


@dataclass(frozen=True)
class BatchPlan:
    """What to enqueue now, and what to leave behind."""

    #: Round ranges to enqueue, as (first_round, last_round) pairs.
    batches: tuple[tuple[int, int], ...]
    #: Rounds still held back after this plan.
    remaining: PendingRoundState
    #: True when a stale remainder was flushed to avoid starving the session.
    flushed_remainder: bool = False


def plan_batches(
    *,
    state: PendingRoundState,
    new_complete_rounds: int,
    last_committed_round: int,
) -> BatchPlan:
    """Decide what to enqueue after `new_complete_rounds` arrive.

    `last_committed_round` is the last round number already written, so batch
    ranges are absolute and deterministic: replaying the same input always
    produces the same batch ids, which is what lets a retried scan recognise
    work it has already enqueued.
    """
    if new_complete_rounds < 0:
        raise ValueError("new_complete_rounds must not be negative")

    total = state.pending_rounds + new_complete_rounds
    batches: list[tuple[int, int]] = []

    cursor_round = last_committed_round
    while total >= ROUNDS_PER_BATCH:
        first = cursor_round + 1
        last = cursor_round + ROUNDS_PER_BATCH
        batches.append((first, last))
        cursor_round = last
        total -= ROUNDS_PER_BATCH

    if batches:
        # Fresh full batches: any remainder starts a new wait.
        return BatchPlan(
            batches=tuple(batches),
            remaining=PendingRoundState(pending_rounds=total, pending_since_scans=0),
        )

    # Nothing reached five. Keep waiting, unless the remainder has been held
    # long enough that waiting further would starve this session.
    pending_since = state.pending_since_scans + 1
    if total > 0 and pending_since >= REMAINDER_MAX_PENDING_SCANS and new_complete_rounds == 0:
        first = last_committed_round + 1
        last = last_committed_round + total
        return BatchPlan(
            batches=((first, last),),
            remaining=PendingRoundState(pending_rounds=0, pending_since_scans=0),
            flushed_remainder=True,
        )

    return BatchPlan(
        batches=(),
        remaining=PendingRoundState(pending_rounds=total, pending_since_scans=pending_since),
    )
