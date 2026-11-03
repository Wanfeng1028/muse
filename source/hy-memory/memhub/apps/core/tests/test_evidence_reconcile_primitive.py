"""A bounded, read-only discovery primitive for the H23 Evidence reconcile.

The objective's crash requirement is "a committed Evidence row must not be
lost". The two-step `Evidence write -> queue/task submit` window can leave a
row with no write entry. C0 scheduled that reconcile for H23 and asked C2 to
supply the primitive; this module pins the discovery half, which is pure
database infrastructure and does not choose the product's grouping semantics.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.contracts import BatchIdentity, WriteRequest
from one_memory.memory_server.durable_queue import (
    DurableWriteQueue,
    ReconcileSchemaUnavailableError,
)


def _put(store: EvidenceStore, message_id: str) -> str:
    return store.put(
        EvidenceInput(
            source_id="s1",
            conversation_id="c1",
            message_id=message_id,
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim=f"body {message_id}",
            created_at=datetime.now(UTC),
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record.evidence_id


def test_unsubmitted_evidence_finds_rows_with_no_write_entry(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    queue = DurableWriteQueue(path)
    submitted = _put(store, "m1")
    orphan = _put(store, "m2")
    queue.submit(
        WriteRequest(
            internal_session_id="c1",
            batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
            evidence_ids=[submitted],
            idempotency_key="idem-1",
        )
    )

    found = queue.unsubmitted_evidence_ids(limit=10)

    assert found == (orphan,)


def test_reconcile_refuses_when_the_evidence_schema_is_not_migrated(tmp_path) -> None:
    """A queue-only database is not an empty reconcile result.

    Returning `()` here would make a pre-migration database look as if every
    trusted Evidence row were already queued. The caller needs a distinct
    retryable state so it can run migration first.
    """
    path = tmp_path / "one-memory.sqlite3"
    queue = DurableWriteQueue(path)

    with pytest.raises(ReconcileSchemaUnavailableError, match="run migrations"):
        queue.unsubmitted_evidence_ids()


def test_unsubmitted_evidence_is_bounded_and_resumable(tmp_path) -> None:
    """The cursor must be stable and bounded so a startup pass is cheap.

    `after_cursor` is the last id a previous page returned; the next call
    resumes strictly after it. In this serial fixture the pages partition the
    backlog once. The primitive is not a cross-call transaction snapshot; a
    concurrent insert or submit is tolerated by the Evidence-derived
    idempotency key, not by pretending the read itself is isolated.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    queue = DurableWriteQueue(path)
    ids = [_put(store, f"m{index}") for index in range(3)]

    first = queue.unsubmitted_evidence_ids(limit=2)
    second = queue.unsubmitted_evidence_ids(limit=2, after_cursor=first[-1])

    assert first == (ids[0], ids[1])
    assert second == (ids[2],)


def test_unsubmitted_evidence_refuses_a_missing_cursor(tmp_path) -> None:
    """A vanished cursor must not silently reset pagination to page one.

    Replaying a prefix may be harmless only because the idempotency key exists;
    the discovery contract itself must fail closed. A caller that deleted the
    anchor or restored an older database must restart from a fresh scan, not
    have the primitive quietly change its place.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    queue = DurableWriteQueue(path)
    first = _put(store, "m1")
    second = _put(store, "m2")

    first_page = queue.unsubmitted_evidence_ids(limit=1)
    assert first_page == (first,)
    with sqlite3.connect(path) as connection, connection:
        connection.execute("DELETE FROM evidence_origins WHERE evidence_id=?", (first,))
        connection.execute("DELETE FROM evidence WHERE evidence_id=?", (first,))

    with pytest.raises(RuntimeError, match="cursor is unavailable"):
        queue.unsubmitted_evidence_ids(limit=10, after_cursor=first)

    # A deliberate fresh pass still sees the remaining orphan.
    assert queue.unsubmitted_evidence_ids(limit=10) == (second,)


def test_unsubmitted_evidence_query_uses_the_reference_index(tmp_path) -> None:
    """The anti-join must not scan every queue payload.

    At production scale the queue can keep many terminal rows, so discovery
    uses a dedicated Evidence reference and an indexed `NOT EXISTS` join
    instead of loading every job's payload or reference JSON.
    """
    from one_memory.database_access import main_database
    from one_memory.memory_server.migrations import memory_write_jobs_sqlite_schema

    path = tmp_path / "one-memory.sqlite3"
    with main_database(path).write(autocommit=True) as connection, connection:
        connection.execute(
            "CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, imported_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX evidence_imported_order ON evidence(imported_at, evidence_id)"
        )
        for statement in memory_write_jobs_sqlite_schema():
            connection.execute(statement)
        plan = [
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT evidence.evidence_id FROM evidence "
                "WHERE evidence.imported_at IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM memory_write_job_evidence ref "
                "WHERE ref.evidence_id=evidence.evidence_id) "
                "ORDER BY evidence.imported_at, evidence.evidence_id LIMIT ?",
                (512,),
            )
        ]

    joined = " | ".join(plan)
    assert "idx_write_job_evidence_evidence" in joined
    assert "SCAN memory_write_jobs" not in joined
    assert "SCAN ref" not in joined


def test_the_shipped_schema_serves_the_reconcile_order(tmp_path) -> None:
    """The real schema must not scan+sort Evidence on every discovery page.

    `unsubmitted_evidence_ids` orders by `(imported_at, evidence_id)` with no
    `user_id` predicate, so `evidence_imported_index` (leading column
    `user_id`) cannot serve it. Before the reconcile-order index the real plan
    was `SCAN evidence` + `USE TEMP B-TREE FOR ORDER BY`; a pass over a large
    corpus paid that on every page. This pins the shipped schema, not a
    test-local index, so a regression to the old DDL fails here.
    """
    import asyncio

    from one_memory.database_access import main_database
    from one_memory.memory_server.migration_runner import SqliteMigrationStore, migrate
    from one_memory.memory_server.migrations import MIGRATIONS

    path = tmp_path / "one-memory.sqlite3"
    asyncio.run(migrate(SqliteMigrationStore(path), MIGRATIONS))

    with main_database(path).read() as connection:
        plan = [
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT evidence.evidence_id FROM evidence "
                "WHERE evidence.imported_at IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM memory_write_job_evidence ref "
                "WHERE ref.evidence_id=evidence.evidence_id) "
                "ORDER BY evidence.imported_at, evidence.evidence_id LIMIT ?",
                (512,),
            )
        ]

    joined = " | ".join(plan)
    assert "evidence_reconcile_order" in joined, joined
    assert "USE TEMP B-TREE FOR ORDER BY" not in joined, joined
    # SQLite reports an in-order covering-index walk as `SCAN evidence USING
    # COVERING INDEX ...`; the failure mode we forbid is a bare table scan with
    # a temp sort, so require the index to be named and the sort to be gone.
    assert "USING COVERING INDEX evidence_reconcile_order" in joined, joined


def test_unsubmitted_evidence_returns_empty_when_all_are_queued(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    queue = DurableWriteQueue(path)
    evidence_id = _put(store, "m1")
    queue.submit(
        WriteRequest(
            internal_session_id="c1",
            batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
            evidence_ids=[evidence_id],
            idempotency_key="idem-1",
        )
    )

    assert queue.unsubmitted_evidence_ids(limit=10) == ()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "10"])
def test_unsubmitted_evidence_rejects_an_invalid_limit(tmp_path, limit: object) -> None:
    queue = DurableWriteQueue(tmp_path / "one-memory.sqlite3")
    with pytest.raises(ValueError, match="limit must be positive"):
        queue.unsubmitted_evidence_ids(limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("cursor", ["", 1, True, ["evidence-id"], object()])
def test_unsubmitted_evidence_rejects_an_invalid_cursor(tmp_path, cursor: object) -> None:
    """A malformed cursor must fail with the public contract, not SQL errors.

    ``after_cursor`` crosses an API/worker boundary and is allowed to be
    absent, but every present value must be a non-empty evidence id. Passing
    a list/object into the lookup produced a raw SQLite binding error; an
    empty string performed a pointless lookup and then reported a missing
    cursor as if the database had lost a real row. The primitive should
    reject the caller's input before touching SQL.
    """
    path = tmp_path / "one-memory.sqlite3"
    with sqlite3.connect(path) as connection, connection:
        connection.execute(
            "CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, imported_at TEXT NOT NULL)"
        )
    queue = DurableWriteQueue(path)

    with pytest.raises(ValueError, match="after_cursor must be a non-empty string"):
        queue.unsubmitted_evidence_ids(after_cursor=cursor)  # type: ignore[arg-type]


def test_a_reconcile_pass_enqueues_an_orphan_exactly_once(tmp_path) -> None:
    """The acceptance's "enqueue once" half, on the C2-owned primitives.

    A crash between Evidence commit and submit leaves an orphan. The reconcile
    flow is: discover it, then submit a write with a stable idempotency key
    derived from the Evidence identity. A second pass must find nothing (the
    row now references it) and must not create a duplicate — the same
    idempotency key would in any case return the existing job.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    queue = DurableWriteQueue(path)
    orphan = _put(store, "m1")  # evidence committed, no submit -> the crash window

    def reconcile_once() -> str | None:
        ids = queue.unsubmitted_evidence_ids(limit=64)
        if not ids:
            return None
        first = ids[0]
        record = queue.submit(
            WriteRequest(
                internal_session_id="c1",
                batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
                evidence_ids=[first],
                # Derived from the Evidence identity: a replay re-derives the
                # same key, so the queue refuses to create a second job.
                idempotency_key=f"reconcile:{first}",
            )
        )
        return record.job_id

    first_job = reconcile_once()
    assert first_job is not None

    # Second pass: the orphan is gone, and a forced replay is idempotent.
    assert queue.unsubmitted_evidence_ids(limit=64) == ()
    replay = queue.submit(
        WriteRequest(
            internal_session_id="c1",
            batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
            evidence_ids=[orphan],
            idempotency_key=f"reconcile:{orphan}",
        )
    )
    assert replay.job_id == first_job
    assert replay.enqueued is False
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory_write_jobs").fetchone()[0] == 1


def test_two_reconcile_workers_submit_the_same_orphan_once(tmp_path) -> None:
    """A restart and a periodic pass may race; the derived key is the arbiter.

    The discovery cursor cannot promise a cross-call snapshot, so two workers
    can both observe the same orphan. They must not create two jobs:
    `reconcile:<evidence_id>` is derived from the Evidence identity and the
    queue's UNIQUE idempotency key makes the second submit an idempotent replay.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    DurableWriteQueue(path)
    orphan = _put(store, "m1")

    def reconcile_worker() -> str:
        request = WriteRequest(
            internal_session_id="c1",
            batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
            evidence_ids=[orphan],
            idempotency_key=f"reconcile:{orphan}",
        )
        return DurableWriteQueue(path).submit(request).job_id

    first = reconcile_worker()
    second = reconcile_worker()

    assert first == second
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory_write_jobs").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM memory_write_job_evidence WHERE evidence_id=?",
                (orphan,),
            ).fetchone()[0]
            == 1
        )


def test_a_sigkill_before_submit_leaves_an_orphan_the_primitive_recovers(tmp_path) -> None:
    """Real process crash between Evidence commit and submit (objective 4.1-4.2).

    The child writes Evidence and is SIGKILLed before it can submit the write.
    No task/queue row exists, so only a *discovery over committed rows* can find
    it. This is the boundary the C1 file-level drain does not cover for manual
    notes; the primitive + derived key then enqueue it exactly once.
    """
    import os
    import signal
    import subprocess
    import sys

    if sys.platform == "win32":
        pytest.skip("POSIX process-kill recovery")

    path = tmp_path / "one-memory.sqlite3"
    EvidenceStore(path)
    child = (
        "import time\n"
        "from datetime import UTC, datetime\n"
        "from pathlib import Path\n"
        "from one_memory.imports.models import ("
        "EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy)\n"
        "from one_memory.imports.storage import EvidenceStore\n"
        "path = Path(" + repr(str(path)) + ")\n"
        "store = EvidenceStore(path)\n"
        "store.put(EvidenceInput(source_id='s1', conversation_id='c1', message_id='m1',\n"
        "    role='user', written_by=WrittenBy.PERSON, verbatim='orphan',\n"
        "    created_at=datetime.now(UTC), origin_meta={EvidenceOrigin.FILE: OriginMetadata()}))\n"
        "print('written', flush=True)\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "written"
    os.kill(process.pid, signal.SIGKILL)
    process.wait(timeout=10)

    queue = DurableWriteQueue(path)
    ids = queue.unsubmitted_evidence_ids(limit=10)
    assert len(ids) == 1, "the committed Evidence must be discoverable after the crash"
    queue.submit(
        WriteRequest(
            internal_session_id="c1",
            batch_identity=BatchIdentity(internal_session_id="c1", first_round=1, last_round=1),
            evidence_ids=[ids[0]],
            idempotency_key=f"reconcile:{ids[0]}",
        )
    )
    assert queue.unsubmitted_evidence_ids(limit=10) == ()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM memory_write_jobs").fetchone()[0] == 1
