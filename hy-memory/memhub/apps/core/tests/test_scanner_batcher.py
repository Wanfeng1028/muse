"""A4-06: the five-round rule, and the degenerate cases around it.

The interesting failures here are not "does five produce one batch" but the
edges: a remainder that never reaches five, a burst larger than one batch, and
a replay that must not renumber anything.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.scanner.batcher import (
    ROUNDS_PER_BATCH,
    PendingRoundState,
    plan_batches,
)


def test_five_rounds_form_one_batch() -> None:
    plan = plan_batches(state=PendingRoundState(), new_complete_rounds=5, last_committed_round=0)
    assert plan.batches == ((1, 5),)
    assert plan.remaining.pending_rounds == 0


def test_four_rounds_are_held_back() -> None:
    """A remainder must not be written early; that is the whole batching point."""
    plan = plan_batches(state=PendingRoundState(), new_complete_rounds=4, last_committed_round=0)
    assert plan.batches == ()
    assert plan.remaining.pending_rounds == 4


def test_remainder_accumulates_across_scans() -> None:
    """Rounds arriving in separate scans still add up."""
    first = plan_batches(state=PendingRoundState(), new_complete_rounds=3, last_committed_round=0)
    second = plan_batches(state=first.remaining, new_complete_rounds=2, last_committed_round=0)
    assert first.batches == ()
    assert second.batches == ((1, 5),)
    assert second.remaining.pending_rounds == 0


def test_a_burst_produces_multiple_full_batches() -> None:
    plan = plan_batches(state=PendingRoundState(), new_complete_rounds=12, last_committed_round=0)
    assert plan.batches == ((1, 5), (6, 10))
    assert plan.remaining.pending_rounds == 2


def test_batch_ranges_are_absolute_not_relative() -> None:
    """Ranges follow the committed round, so replays produce identical ids.

    If ranges were relative to the batch, the same conversation split across
    restarts would produce different batch ids and the dedupe would miss.
    """
    plan = plan_batches(state=PendingRoundState(), new_complete_rounds=5, last_committed_round=10)
    assert plan.batches == ((11, 15),)


def test_batch_ids_are_stable_under_replay() -> None:
    from one_memory.memory_server.contracts import batch_id

    first = plan_batches(state=PendingRoundState(), new_complete_rounds=5, last_committed_round=10)
    replay = plan_batches(state=PendingRoundState(), new_complete_rounds=5, last_committed_round=10)
    assert first.batches == replay.batches
    for start, end in first.batches:
        assert batch_id(internal_session_id="s1", first_round=start, last_round=end) == batch_id(
            internal_session_id="s1", first_round=start, last_round=end
        )


def test_stale_remainder_is_flushed_so_idle_sessions_are_written() -> None:
    """A conversation that stops just short of five must still be saved.

    Without this flush, a short exchange would sit in `pending` indefinitely
    and never reach HY — a silent data-loss bug, not just a delay.
    """
    # One scan brings 3 rounds, then the user stops talking: every later scan
    # arrives with nothing new. The flush happens on whichever scan the
    # starvation clock expires, so the loop must inspect the plan, not just
    # carry the state forward and check at the end.
    state = plan_batches(
        state=PendingRoundState(), new_complete_rounds=3, last_committed_round=0
    ).remaining
    assert state.pending_rounds == 3

    flushed = None
    # The bound is a fixed number of scans, deliberately not derived from
    # REMAINDER_MAX_PENDING_SCANS: a limit that scales with the constant under
    # test can never fail, which is exactly how a missing flush would slip
    # through as "still pending, just wait longer".
    for _ in range(4):
        plan = plan_batches(state=state, new_complete_rounds=0, last_committed_round=0)
        if plan.batches:
            flushed = plan
            break
        state = plan.remaining

    assert flushed is not None, "an idle remainder must eventually be flushed"
    assert flushed.flushed_remainder is True, (
        "the flush must be reported as a flush, not as an ordinary full batch"
    )
    assert flushed.flushed_remainder is True
    assert flushed.batches == ((1, 3),)
    assert flushed.remaining.pending_rounds == 0


def test_fresh_arrivals_reset_the_starvation_clock() -> None:
    """A session that keeps producing should not be force-flushed mid-stream."""
    first = plan_batches(state=PendingRoundState(), new_complete_rounds=3, last_committed_round=0)
    second = plan_batches(state=first.remaining, new_complete_rounds=1, last_committed_round=0)
    assert second.flushed_remainder is False
    assert second.remaining.pending_rounds == 4


def test_no_new_rounds_and_no_pending_produces_nothing() -> None:
    plan = plan_batches(state=PendingRoundState(), new_complete_rounds=0, last_committed_round=0)
    assert plan.batches == ()
    assert plan.remaining == PendingRoundState(pending_rounds=0, pending_since_scans=1)


def test_negative_rounds_are_rejected() -> None:
    with pytest.raises(ValueError):
        plan_batches(state=PendingRoundState(), new_complete_rounds=-1, last_committed_round=0)


def test_incomplete_rounds_are_not_counted() -> None:
    """An unterminated trailing round is not a round, so it must not batch.

    Enqueuing it would write a half-finished exchange and then need a repair.
    """
    plan = plan_batches(
        state=PendingRoundState(),
        new_complete_rounds=ROUNDS_PER_BATCH - 1,
        last_committed_round=0,
    )
    assert plan.batches == ()
