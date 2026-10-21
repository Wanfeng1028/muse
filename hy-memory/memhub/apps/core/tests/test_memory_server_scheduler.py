"""A2-04: scheduling policy, proven without a database.

These are the invariants the durable queue must hold once MySQL claim exists:

- one session never runs twice concurrently;
- a live injection is not blocked by a background backlog;
- one session's long backlog cannot take every slot;
- fairness means older work goes first among equals.

Each is tested as a property rather than a snapshot, because the interesting
failures are ordering bugs that a single expected list would hide.
"""

from __future__ import annotations

from one_memory.memory_server.scheduler import (
    JobRef,
    SchedulerConfig,
    SchedulerState,
    plan_next_batch,
)


def _job(job_id: str, session: str, *, priority: str = "normal", sequence: int = 0) -> JobRef:
    return JobRef(
        job_id=job_id,
        internal_session_id=session,
        priority=priority,
        sequence=sequence,
    )


def test_same_session_never_runs_twice() -> None:
    """One conversation's rounds must not be written concurrently."""
    state = SchedulerState(running=[_job("r1", "sess-A")])
    waiting = [_job("w1", "sess-A"), _job("w2", "sess-B")]
    chosen = plan_next_batch(waiting=waiting, state=state, config=SchedulerConfig())
    assert [job.job_id for job in chosen] == ["w2"]


def test_two_waiting_jobs_from_one_session_only_start_one() -> None:
    state = SchedulerState()
    waiting = [_job("w1", "sess-A", sequence=1), _job("w2", "sess-A", sequence=2)]
    chosen = plan_next_batch(waiting=waiting, state=state, config=SchedulerConfig())
    assert len(chosen) == 1
    assert chosen[0].job_id == "w1"


def test_cross_session_runs_in_parallel_up_to_the_limit() -> None:
    waiting = [_job(f"w{i}", f"sess-{i}", sequence=i) for i in range(6)]
    chosen = plan_next_batch(
        waiting=waiting, state=SchedulerState(), config=SchedulerConfig(max_concurrent=4)
    )
    assert len(chosen) == 4
    assert len({job.internal_session_id for job in chosen}) == 4


def test_live_work_is_not_blocked_by_a_background_backlog() -> None:
    """A user waiting on an injection outranks a full queue of background work."""
    state = SchedulerState(running=[_job(f"r{i}", f"bg-{i}") for i in range(3)])
    waiting = [_job(f"more-bg-{i}", f"bg-new-{i}", sequence=i) for i in range(6)] + [
        _job("live-1", "sess-live", priority="live", sequence=99)
    ]
    chosen = plan_next_batch(
        waiting=waiting,
        state=state,
        config=SchedulerConfig(max_concurrent=4, live_reserved=1),
    )
    # One free slot, and it goes to the live job rather than to a backlog that
    # was enqueued earlier and would otherwise win purely on age.
    assert [job.job_id for job in chosen] == ["live-1"]


def test_live_work_wins_the_slot_over_older_background_work() -> None:
    """Priority beats age. This is the whole point of the live lane."""
    waiting = [
        _job("old-bg", "sess-bg", sequence=1),
        _job("live", "sess-live", priority="live", sequence=50),
    ]
    chosen = plan_next_batch(
        waiting=waiting,
        state=SchedulerState(),
        config=SchedulerConfig(max_concurrent=1, live_reserved=1),
    )
    assert [job.job_id for job in chosen] == ["live"]


def test_background_work_cannot_take_the_reserved_live_slot() -> None:
    """The reservation must actually reserve, not just prefer.

    If background jobs could fill every slot, a burst of imports would delay a
    live injection until one finished, which is the WorkBuddy hook timeout the
    product already hit once.

    Scoped to a round where live work is also waiting: with no live demand,
    background work is allowed to run full (see the next test), because
    leaving a slot idle would cap throughput for no benefit.
    """
    waiting = [_job(f"bg-{i}", f"sess-{i}", sequence=i) for i in range(8)]
    waiting.append(_job("live-1", "sess-live", priority="live", sequence=99))
    chosen = plan_next_batch(
        waiting=waiting,
        state=SchedulerState(),
        config=SchedulerConfig(max_concurrent=4, live_reserved=1),
    )
    assert len(chosen) == 4
    assert any(job.priority == "live" for job in chosen)
    assert sum(1 for job in chosen if job.priority == "normal") == 3


def test_background_runs_full_when_no_live_work_is_waiting() -> None:
    """An unused reservation must not become a permanent throughput hole."""
    waiting = [_job(f"bg-{i}", f"sess-{i}", sequence=i) for i in range(8)]
    chosen = plan_next_batch(
        waiting=waiting,
        state=SchedulerState(),
        config=SchedulerConfig(max_concurrent=4, live_reserved=1),
    )
    assert len(chosen) == 4


def test_live_is_selected_first_when_slots_are_scarce() -> None:
    """Priority must decide *order*, not merely survive the reservation.

    A reservation alone can keep a live slot open without ever preferring live
    work when several jobs compete for fewer slots than there are jobs. This
    pins the ordering itself: with one slot and an older background job, the
    live job must be the one chosen. (An earlier version of this suite passed
    even with live demoted to age-ordering, because the reservation masked it.)
    """
    waiting = [
        _job("old-bg", "sess-bg", sequence=1),
        _job("old-bg-2", "sess-bg-2", sequence=2),
        _job("live", "sess-live", priority="live", sequence=90),
    ]
    chosen = plan_next_batch(
        waiting=waiting,
        state=SchedulerState(),
        config=SchedulerConfig(max_concurrent=2, live_reserved=1),
    )
    assert chosen[0].job_id == "live"


def test_one_session_cannot_take_every_slot() -> None:
    waiting = [_job(f"w{i}", "sess-A", sequence=i) for i in range(10)]
    waiting.append(_job("other", "sess-B", sequence=50))
    chosen = plan_next_batch(
        waiting=waiting, state=SchedulerState(), config=SchedulerConfig(max_concurrent=4)
    )
    assert sum(1 for job in chosen if job.internal_session_id == "sess-A") == 1
    assert any(job.internal_session_id == "sess-B" for job in chosen)


def test_older_work_goes_first_among_equals() -> None:
    waiting = [_job("new", "sess-A", sequence=10), _job("old", "sess-B", sequence=1)]
    chosen = plan_next_batch(waiting=waiting, state=SchedulerState(), config=SchedulerConfig())
    assert [job.job_id for job in chosen] == ["old", "new"]


def test_capacity_respected_when_some_are_running() -> None:
    state = SchedulerState(running=[_job("r1", "sess-A"), _job("r2", "sess-B")])
    waiting = [_job(f"w{i}", f"sess-{i}", sequence=i) for i in range(5)]
    chosen = plan_next_batch(waiting=waiting, state=state, config=SchedulerConfig(max_concurrent=4))
    assert len(chosen) == 2
    assert len(state.running) + len(chosen) <= 4


def test_zero_capacity_starts_nothing() -> None:
    waiting = [_job("w1", "sess-A")]
    assert (
        plan_next_batch(
            waiting=waiting, state=SchedulerState(), config=SchedulerConfig(max_concurrent=0)
        )
        == []
    )
