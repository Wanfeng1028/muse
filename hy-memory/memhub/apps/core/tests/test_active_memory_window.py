from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from one_memory.memory_queue import EXTRACTION_WINDOW, FRESH_WINDOW
from one_memory.memory_tasks import MemoryTaskStatus
from tests.test_memory_queue_recency import SteppedRunner, _put, _stores, _supervisor, _task


def _seed_pending(tmp_path, count: int):
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    now = datetime.now(UTC)
    template_record = _put(
        evidence,
        message_id="template",
        conversation_id="template",
        content="template",
        created_at=now,
        workspace="workspace:v1:test",
    )
    template_task = _task(tasks, profile, template_record, suffix="template")
    if count == 1:
        return stores, now, [template_task.task_id]

    evidence_rows = []
    task_rows = []
    live_ids = [template_task.task_id]
    for index in range(1, count):
        lane = index % 3
        moment = now if lane == 0 else now - timedelta(days=2 if lane == 1 else 100)
        evidence_id = f"window-evidence-{index}"
        task_id = f"window-task-{index}"
        evidence_rows.append(
            (
                evidence_id,
                f"window-key-{index}",
                "local",
                "cursor",
                "workspace:v1:test",
                f"conversation-{index}",
                "raw_conversation",
                "user",
                "person",
                moment.isoformat(),
                "bounded window",
                f"hash-{index}",
                1,
                now.isoformat(),
                now.isoformat(),
            )
        )
        task_rows.append(
            (
                task_id,
                f"window-request-{index}",
                "local",
                "extract",
                evidence_id,
                "pending",
                template_task.profile_id,
                template_task.profile_revision,
                template_task.profile_snapshot.model_dump_json(),
                0,
                now.isoformat(),
                now.isoformat(),
            )
        )
        if lane == 0 and len(live_ids) < 16:
            live_ids.append(task_id)
    with sqlite3.connect(tasks.database_path) as db:
        db.executemany(
            """
            INSERT INTO evidence (
                evidence_id, idempotency_key, user_id, source_id, workspace,
                conversation_id, content_kind, role, written_by, created_at,
                verbatim, content_hash, revision, imported_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            evidence_rows,
        )
        db.executemany(
            """
            INSERT INTO memory_tasks (
                task_id, request_id, user_id, kind, input_ref, status,
                profile_id, profile_revision, profile_snapshot_json, attempts,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            task_rows,
        )
    return stores, now, live_ids


@pytest.mark.parametrize("pending_count", [10, 1_000, 100_000])
def test_active_window_is_bounded_independently_of_pending_total(tmp_path, pending_count):
    stores, now, live_ids = _seed_pending(tmp_path, pending_count)
    tasks = stores[2]

    window = tasks.active_window(
        now=now,
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
        live_task_ids=tuple(live_ids),
        live_limit=16,
        fresh_limit=16,
        backlog_limit=8,
    )

    assert len(window) <= 40
    assert sum(item.live for item in window) <= 16
    assert sum(item.fresh and not item.live for item in window) <= 16
    assert sum(not item.fresh and not item.live for item in window) <= 8
    assert all(item.at >= now - EXTRACTION_WINDOW for item in window)
    if pending_count >= 1_000:
        assert len(window) == 40


def test_active_window_does_not_take_the_writer_when_nothing_needs_deferring(tmp_path):
    """Reading a window is a read unless there is an out-of-window row to mark.

    `active_window` runs on the scheduler's hot path. Taking the single writer
    for every fresh read makes ordinary scheduling contend with import and
    queue writes even when no legacy row needs deferring.
    """
    stores, now, live_ids = _seed_pending(tmp_path, 10)
    tasks = stores[2]
    # `_seed_pending` deliberately includes old rows for the bounded-window
    # test; this test is about the no-defer path, so remove those candidates.
    with sqlite3.connect(tasks.database_path) as connection, connection:
        connection.execute(
            "UPDATE memory_tasks SET status='completed' "
            "WHERE input_ref IN ("
            "SELECT evidence_id FROM evidence "
            "WHERE julianday(coalesce(created_at, imported_at)) < julianday(?)"
            ")",
            ((now - EXTRACTION_WINDOW).isoformat(),),
        )
    before = tasks._connect  # noqa: SLF001
    writer_checkouts: list[bool] = []

    def observed(*, writing: bool = False):
        writer_checkouts.append(writing)
        return before(writing=writing)

    tasks._connect = observed  # type: ignore[method-assign]
    tasks.active_window(
        now=now,
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
        live_task_ids=tuple(live_ids),
        live_limit=16,
        fresh_limit=16,
        backlog_limit=8,
    )

    assert writer_checkouts == [False]


@pytest.mark.parametrize("bad", [True, 1.5, "2"])
def test_active_window_rejects_non_integer_limits(tmp_path, bad: object) -> None:
    stores, now, _live_ids = _seed_pending(tmp_path, 10)
    tasks = stores[2]
    with pytest.raises(ValueError, match="limits must be non-negative integers"):
        tasks.active_window(
            now=now,
            fresh_window=FRESH_WINDOW,
            extraction_window=EXTRACTION_WINDOW,
            live_limit=bad,  # type: ignore[arg-type]
        )


def test_active_window_accepts_a_naive_clock(tmp_path) -> None:
    stores, now, _live_ids = _seed_pending(tmp_path, 10)
    tasks = stores[2]

    rows = tasks.active_window(
        now=now.replace(tzinfo=None),
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
    )

    assert rows
    assert all(row.at is None or row.at.tzinfo is not None for row in rows)


def test_resume_uses_joined_window_metadata_without_per_task_evidence_get(tmp_path, monkeypatch):
    stores, _now, _live_ids = _seed_pending(tmp_path, 100)
    evidence = stores[0]
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())
    monkeypatch.setattr(
        evidence,
        "get",
        lambda _evidence_id: pytest.fail("resume performed an N+1 evidence.get"),
    )

    work = supervisor.prepare_resume()

    assert work
    assert len(work) <= 40


def test_refill_excludes_tasks_already_queued_or_in_flight(tmp_path):
    stores, _now, _live_ids = _seed_pending(tmp_path, 100)
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())
    first = supervisor.prepare_resume()
    assert len(first) == 24
    for item in first[:-1]:
        supervisor._queue.add(item)
    supervisor._in_flight[first[-1].task_id] = first[-1]

    refill = supervisor._prepare_active_window()

    occupied = {item.task_id for item in first}
    assert refill
    assert occupied.isdisjoint(item.task_id for item in refill)


def test_active_window_defers_tasks_older_than_ninety_days(tmp_path):
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    old = _put(
        evidence,
        message_id="old",
        conversation_id="old",
        content="too old for automatic extraction",
        created_at=datetime.now(UTC) - timedelta(days=91),
        workspace="workspace:v1:test",
    )
    task = _task(tasks, profile, old, suffix="old")
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    assert supervisor.prepare_resume() == []
    deferred = tasks.require(task.task_id)
    assert deferred.status is MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW
    assert deferred.last_error_code == "outside_extraction_window"


def test_active_window_keeps_old_continuous_ingest_pending(tmp_path):
    """Continuous eligibility follows ingest sequence, not message time."""
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    old = _put(
        evidence,
        message_id="old-continuous",
        conversation_id="old-continuous",
        content="old content imported after continuous processing was enabled",
        created_at=datetime.now(UTC) - timedelta(days=365),
        workspace="workspace:v1:test",
    )
    task = _task(tasks, profile, old, suffix="old-continuous")
    with sqlite3.connect(tasks.database_path) as connection:
        connection.execute(
            "CREATE TABLE memory_task_continuous_permissions (task_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO memory_task_continuous_permissions VALUES (?)", (task.task_id,)
        )

    window = tasks.active_window(
        now=datetime.now(UTC),
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
    )

    assert [item.task.task_id for item in window] == [task.task_id]
    assert tasks.require(task.task_id).status is MemoryTaskStatus.PENDING


def test_continuous_old_task_does_not_take_the_writer(tmp_path):
    """A continuous exemption is not a defer candidate.

    The old task is eligible by ingest sequence, so the window must read it
    without setting `outside_extraction_window`; touching the sole writer for
    that read would recreate the contention the no-defer path removes.
    """
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    old = _put(
        evidence,
        message_id="old-continuous-writer",
        conversation_id="old-continuous-writer",
        content="old continuous content",
        created_at=datetime.now(UTC) - timedelta(days=365),
        workspace="workspace:v1:test",
    )
    task = _task(tasks, profile, old, suffix="old-continuous-writer")
    with sqlite3.connect(tasks.database_path) as connection:
        connection.execute(
            "CREATE TABLE memory_task_continuous_permissions (task_id TEXT PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO memory_task_continuous_permissions VALUES (?)", (task.task_id,)
        )
    before = tasks._connect  # noqa: SLF001
    writer_checkouts: list[bool] = []

    def observed(*, writing: bool = False):
        writer_checkouts.append(writing)
        return before(writing=writing)

    tasks._connect = observed  # type: ignore[method-assign]
    window = tasks.active_window(
        now=datetime.now(UTC),
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
    )

    assert [item.task.task_id for item in window] == [task.task_id]
    assert writer_checkouts == [False]
