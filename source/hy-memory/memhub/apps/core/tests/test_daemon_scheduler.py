"""A5-02/A5-04: the daemon's scan scheduler and composed health."""

from __future__ import annotations

import pytest

from one_memory.memory_server.daemon_scheduler import (
    HealthPart,
    PartState,
    ScanScheduler,
    ScanState,
    combined_state,
)


def test_a_request_is_admitted() -> None:
    scheduler = ScanScheduler(["a"])
    root, state = scheduler.request("a")
    assert root == "a"
    assert state == ScanState.IDLE
    assert scheduler.next_batch() == ["a"]


def test_the_same_root_is_never_scanned_twice_at_once() -> None:
    """Two scans of one root would both write the same cursor."""
    scheduler = ScanScheduler(["a"])
    # Request first: the scheduler only starts scans that were asked for, so a
    # bare next_batch() with nothing requested must stay idle rather than
    # busy-loop over the roots.
    scheduler.request("a")
    assert scheduler.next_batch() == ["a"]
    root, state = scheduler.request("a")
    assert state == ScanState.RUNNING
    # A second request while running returns the in-flight scan, not a new one.
    assert scheduler.next_batch() == []


def test_asking_twice_is_safe() -> None:
    """Pressing 'scan now' twice must not create a second scan."""
    scheduler = ScanScheduler(["a"])
    root, first = scheduler.request("a")
    scheduler.next_batch()
    root, second = scheduler.request("a")
    assert second == ScanState.RUNNING
    assert scheduler.ledger.waiting == []


def test_finishing_frees_the_root() -> None:
    scheduler = ScanScheduler(["a"])
    scheduler.request("a")
    scheduler.next_batch()
    scheduler.finish("a")
    assert scheduler.state_of("a") == ScanState.IDLE
    assert scheduler.next_batch() == []


def test_finishing_an_unknown_root_ignores_it() -> None:
    scheduler = ScanScheduler(["a"])
    scheduler.finish("nope")
    assert scheduler.ledger.running == set()


def test_one_beat_requests_every_registered_root() -> None:
    scheduler = ScanScheduler(["a", "b", "c"])
    assert scheduler.beat() == ["a"]
    scheduler.finish("a")
    assert scheduler.next_batch() == ["b"]


def test_a_beat_does_not_restart_a_running_root() -> None:
    scheduler = ScanScheduler(["a"])
    scheduler.beat()
    assert scheduler.beat() == []
    assert scheduler.state_of("a") == ScanState.RUNNING


def test_repeated_beats_never_start_a_second_scan_of_one_root() -> None:
    """The end-to-end invariant, not just the queue bookkeeping.

    `request()` already refuses to re-queue a running root, which is why
    disabling the start guard alone changes nothing observable. So this asserts
    the outcome a caller depends on: no matter how many beats arrive before a
    finish, exactly one scan of a root is ever in flight, and only one is ever
    started per cycle.
    """
    scheduler = ScanScheduler(["a"])
    started = scheduler.beat()
    assert started == ["a"]
    for _ in range(5):
        assert scheduler.beat() == []
    assert scheduler.ledger.running == {"a"}
    scheduler.finish("a")
    assert scheduler.beat() == ["a"]


def test_rotation_continues_from_where_it_stopped() -> None:
    """A busy root must not hold the front of the queue forever."""
    scheduler = ScanScheduler(["a", "b"])
    scheduler.beat()
    scheduler.finish("a")
    # Second beat starts at b, not a.
    assert scheduler.beat() == ["b"]


def test_concurrency_is_bounded() -> None:
    scheduler = ScanScheduler(["a", "b", "c"], max_concurrent=2)
    assert scheduler.beat() == ["a", "b"]
    # Two are already running, so a further beat must not admit a third.
    assert scheduler.beat() == []


def test_zero_concurrency_is_rejected() -> None:
    with pytest.raises(ValueError):
        ScanScheduler(["a"], max_concurrent=0)


def test_duplicate_roots_are_collapsed() -> None:
    scheduler = ScanScheduler(["a", "a"])
    assert scheduler.beat() == ["a"]


def test_no_roots_means_nothing_happens() -> None:
    assert ScanScheduler([]).beat() == []


def test_health_is_the_worst_part() -> None:
    """One failure must not hide behind an aggregate."""
    parts = [
        HealthPart("mysql", PartState.OK),
        HealthPart("server", PartState.FAILED, "not responding"),
    ]
    assert combined_state(parts) == PartState.FAILED


def test_unknown_is_worse_than_ok() -> None:
    """'Not checked yet' is not a claim of health."""
    parts = [HealthPart("scanner", PartState.UNKNOWN), HealthPart("mysql", PartState.OK)]
    assert combined_state(parts) == PartState.UNKNOWN


def test_degraded_beats_unknown() -> None:
    parts = [HealthPart("a", PartState.UNKNOWN), HealthPart("b", PartState.DEGRADED)]
    assert combined_state(parts) == PartState.DEGRADED


def test_empty_health_is_unknown_not_ok() -> None:
    assert combined_state([]) == PartState.UNKNOWN
