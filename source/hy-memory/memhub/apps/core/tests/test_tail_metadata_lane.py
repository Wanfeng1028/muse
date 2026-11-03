"""Post-response metadata retries must be bounded and never block the route."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from one_memory.memory_server.migration_runner import SqliteMigrationStore, migrate
from one_memory.memory_server.migrations import MIGRATIONS
from one_memory.memory_server.tail_lane import TailMetadataLane


def test_lane_retries_after_the_response_has_returned() -> None:
    lane = TailMetadataLane(max_pending=8)
    calls = 0
    done = threading.Event()

    def operation() -> None:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise OSError("writer busy")
        done.set()

    assert lane.submit(operation, attempts=3) is True
    assert done.wait(2)
    lane.stop()
    assert calls == 2


def test_lane_is_bounded_and_reports_drops() -> None:
    lane = TailMetadataLane(max_pending=1)
    release = threading.Event()

    def blocked() -> None:
        release.wait(2)

    assert lane.submit(blocked, attempts=1) is True
    assert lane.submit(blocked, attempts=1) is False
    release.set()
    lane.stop(drain=True)
    assert lane.dropped == 1


def _migrated_database(tmp_path):
    path = tmp_path / "one-memory.sqlite3"
    asyncio.run(migrate(SqliteMigrationStore(path), MIGRATIONS))
    return path


def test_tail_handoff_is_durable_idempotent_and_lease_recoverable(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(milliseconds=50), max_pending=2)
    payload = {"event": "query", "host": "codex"}

    assert store.submit("event-1", payload) is True
    assert store.submit("event-1", payload) is False
    with pytest.raises(ValueError, match="conflict"):
        store.submit("event-1", {"event": "different"})

    claim_a = store.claim("owner-a")
    assert [item.event_id for item in claim_a] == ["event-1"]
    assert store.claim("owner-b") == ()
    time.sleep(0.06)
    claim_b = store.claim("owner-b")
    assert [item.event_id for item in claim_b] == ["event-1"]
    assert store.complete("event-1", owner="owner-a", token=claim_a[0].token) is False
    assert store.complete("event-1", owner="owner-b", token=claim_b[0].token) is True
    assert store.pending_count() == 0
    assert store.claim("owner-c") == ()


def test_tail_handoff_capacity_is_explicit_not_a_silent_drop(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, max_pending=1)
    assert store.submit("event-1", {"event": "one"}) is True
    with pytest.raises(OverflowError, match="capacity"):
        store.submit("event-2", {"event": "two"})
    assert store.pending_count() == 1


def test_tail_handoff_terminal_rows_are_not_rewritten_or_claimed(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path)
    assert store.submit("event-1", {"event": "one"}) is True
    claim = store.claim("owner")
    assert [item.event_id for item in claim] == ["event-1"]
    assert (
        store.fail(
            "event-1",
            owner="owner",
            token=claim[0].token,
            error_code="database_locked",
        )
        is True
    )
    assert (
        store.fail(
            "event-1",
            owner="owner",
            token=claim[0].token,
            error_code="database_locked",
        )
        is False
    )
    assert store.claim("owner-2") == ()


def test_tail_handoff_claim_race_does_not_steal_a_live_lease(tmp_path) -> None:
    """A second claim must not overwrite a fresh owner with a stale predicate."""
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(seconds=30))
    assert store.submit("event-1", {"event": "one"}) is True
    claim_a = store.claim("owner-a")
    assert [item.event_id for item in claim_a] == ["event-1"]
    assert store.claim("owner-b") == ()
    assert store.complete("event-1", owner="owner-a", token=claim_a[0].token) is True
    assert store.complete("event-1", owner="owner-b", token="wrong") is False


def test_tail_handoff_old_owner_cannot_settle_after_lease_reclaim(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(milliseconds=50))
    assert store.submit("event-1", {"event": "one"}) is True
    claim_a = store.claim("owner-a")
    assert [item.event_id for item in claim_a] == ["event-1"]
    time.sleep(0.06)
    claim_b = store.claim("owner-b")
    assert [item.event_id for item in claim_b] == ["event-1"]
    assert store.complete("event-1", owner="owner-a", token=claim_a[0].token) is False
    assert (
        store.fail(
            "event-1",
            owner="owner-a",
            token=claim_a[0].token,
            error_code="old_owner",
        )
        is False
    )
    assert store.complete("event-1", owner="owner-b", token=claim_b[0].token) is True


def test_tail_handoff_unknown_is_terminal_and_prunable(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path)
    assert store.submit("event-1", {"event": "one"}) is True
    claim = store.claim("owner")
    assert [item.event_id for item in claim] == ["event-1"]
    assert (
        store.unknown(
            "event-1",
            owner="owner",
            token=claim[0].token,
            error_code="outcome_unknown",
        )
        is True
    )
    assert store.claim("owner-2") == ()
    assert store.prune_terminal(older_than=timedelta(0)) == 1
    assert store.pending_count() == 0


def test_tail_lane_remains_unwired_until_approved() -> None:
    """Product routes must not import the lane before the reliability gate."""
    source_root = Path(__file__).resolve().parents[1] / "src" / "one_memory"
    offenders = [
        path
        for path in source_root.rglob("*.py")
        if path.name != "tail_lane.py" and "TailMetadataLane" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_tail_handoff_startup_reconcile_returns_expired_work(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(milliseconds=50))
    assert store.submit("event-1", {"event": "one"}) is True
    claim = store.claim("dead-worker")
    assert [item.event_id for item in claim] == ["event-1"]

    # A live lease must not be stolen by startup reconcile.
    assert store.startup_reconcile() == 0
    time.sleep(0.06)
    assert store.startup_reconcile() == 1
    reclaimed = store.claim("new-worker")
    assert [item.event_id for item in reclaimed] == ["event-1"]


def test_tail_handoff_worker_drain_releases_failed_work(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(seconds=30))
    assert store.submit("event-1", {"event": "one"}) is True
    assert store.submit("event-2", {"event": "two"}) is True

    attempted: list[str] = []

    def execute(claim) -> None:
        attempted.append(claim.event_id)
        if claim.event_id == "event-2":
            raise OSError("writer busy")

    run = store.drain_once(execute, owner="worker", limit=2)
    assert run.processed == 1
    assert sorted(attempted) == ["event-1", "event-2"]
    assert run.remaining == 1


def test_tail_handoff_exit_flush_is_bounded_and_leaves_work_recoverable(tmp_path) -> None:
    from one_memory.memory_server.tail_lane import TailHandoffStore

    path = _migrated_database(tmp_path)
    store = TailHandoffStore(path, lease=timedelta(seconds=30))
    assert store.submit("event-1", {"event": "one"}) is True
    assert store.submit("event-2", {"event": "two"}) is True

    calls = 0

    def execute(_claim) -> None:
        nonlocal calls
        calls += 1
        if calls >= 1:
            time.sleep(0.05)

    run = store.exit_flush(
        execute,
        owner="shutdown",
        timeout_seconds=0.02,
        limit=1,
    )
    assert run.remaining >= 1
    # Remaining work is pending, not silently dropped.
    assert store.pending_count() == run.remaining


def test_migration_41_idempotent_when_lease_token_already_exists() -> None:
    from one_memory.memory_server.migrations import _041_tail_handoff_lease_token

    class Cursor:
        dialect = "mysql"

        def __init__(self) -> None:
            self.executed: list[str] = []

        async def columns(self, table: str) -> set[str]:
            assert table == "tail_handoff"
            return {"event_id", "lease_token"}

        async def execute(self, sql: str) -> None:
            self.executed.append(sql)

    cursor = Cursor()
    asyncio.run(_041_tail_handoff_lease_token(cursor))
    assert cursor.executed == []
