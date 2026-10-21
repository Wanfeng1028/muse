import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress

import pytest

from one_memory.imports.adapters import ScanCursorTouch, ScannedEvidence
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.runner import ImportRunner, _PendingSkips
from one_memory.imports.storage import EvidenceStore
from tests.test_import_runner import FixtureAdapter, cursor, evidence, stores


@pytest.mark.parametrize("existing", [False, True])
def test_counter_failure_rolls_back_evidence_versions_and_cursor(tmp_path, monkeypatch, existing):
    records, jobs = stores(tmp_path)
    original = evidence("1")
    if existing:
        records.put(original)
    changed = original.model_copy(update={"verbatim": "revised synthetic message"})
    job = jobs.create(user_id="local", source_id="fixture")
    scheduled = []

    def fail_after_cursor(connection, owner, checkpoint, now):
        upsert(connection, owner, checkpoint, now)
        raise sqlite3.OperationalError("synthetic counter transaction failure")

    upsert = jobs._upsert_cursor
    monkeypatch.setattr(jobs, "_upsert_cursor", fail_after_cursor)
    with pytest.raises(sqlite3.OperationalError, match="synthetic counter"):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs, on_evidence=scheduled.append).run(
                adapter=FixtureAdapter(
                    [ScannedEvidence(evidence=changed, cursor=cursor("line:1"))]
                ),
                job_id=job.job_id,
            )
        )
    current = jobs.require(job.job_id)
    assert current.status is ImportStatus.FAILED
    assert current.stored == current.revised == current.merged == 0
    assert current.checkpoint is None
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}
    assert records.count() == int(existing)
    with records._connect() as db:
        assert db.execute("SELECT count(*) FROM evidence_versions").fetchone()[0] == int(existing)
        assert db.execute("SELECT count(*) FROM evidence_origins").fetchone()[0] == int(existing)
    if existing:
        kept = records.get(original.evidence_id)
        assert kept.verbatim == original.verbatim and kept.revision == 1
    assert scheduled == []


def test_same_identity_cursor_rewind_is_blocked_and_logged(tmp_path, caplog):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    first = cursor("byte:4000")
    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=first,
        was_created=True,
        was_revised=False,
    )
    caplog.set_level("WARNING", logger="one_memory.imports.jobs")

    result = jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:1000"),
        was_created=True,
        was_revised=False,
    )

    stored = jobs.get_source_cursors(user_id="local", source_id="fixture")["a" * 64]
    assert stored.checkpoint == "byte:4000"
    assert result.checkpoint == "byte:4000"
    assert result.discovered == 2
    assert result.stored == 2
    assert any("import_cursor_rewind_blocked" in record.message for record in caplog.records)


def test_replaced_identity_may_reset_checkpoint(tmp_path):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:4000"),
        was_created=True,
        was_revised=False,
    )

    replaced = cursor("byte:1").model_copy(update={"file_identity": "fixture:replaced"})
    result = jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=replaced,
        was_created=True,
        was_revised=False,
    )

    stored = jobs.get_source_cursors(user_id="local", source_id="fixture")["a" * 64]
    assert stored.file_identity == "fixture:replaced"
    assert stored.checkpoint == "byte:1"
    assert result.checkpoint == "byte:1"


def test_same_identity_truncation_may_reset_checkpoint(tmp_path):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:4000").model_copy(update={"observed_size": 4000}),
        was_created=True,
        was_revised=False,
    )

    truncated = cursor("byte:1").model_copy(update={"observed_size": 100})
    result = jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=truncated,
        was_created=True,
        was_revised=False,
    )

    stored = jobs.get_source_cursors(user_id="local", source_id="fixture")["a" * 64]
    assert stored.checkpoint == "byte:1"
    assert result.checkpoint == "byte:1"


def test_a_cursor_past_the_file_may_be_corrected_from_zero(tmp_path):
    """The real-machine branch: an out-of-range cursor must stay writable.

    `resume_checkpoint` treats a checkpoint past the file as an invalid anchor
    and re-reads from 0. Blocking every numeric regression would pin that bad
    cursor forever, so the reader could never record reaching EOF again.
    """
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    file_size = 45_411_693
    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:45587912").model_copy(update={"observed_size": file_size}),
        was_created=True,
        was_revised=False,
    )

    for offset in (500_000, 20_000_000, file_size):
        result = jobs.record_evidence(
            claimed.job_id,
            runner_token=token,
            cursor=cursor(f"byte:{offset}").model_copy(update={"observed_size": file_size}),
            was_created=True,
            was_revised=False,
        )
        assert result.checkpoint == f"byte:{offset}"

    stored = jobs.get_source_cursors(user_id="local", source_id="fixture")["a" * 64]
    assert stored.checkpoint == f"byte:{file_size}"


@pytest.mark.parametrize("kind", ["byte", "record", "row", "rowid"])
def test_numeric_checkpoint_kinds_are_comparable(tmp_path, kind):
    from one_memory.imports.jobs import _numeric_checkpoint

    assert _numeric_checkpoint(f"{kind}:4096") == 4096
    assert _numeric_checkpoint(f"{kind}:0") == 0
    assert _numeric_checkpoint(f"{kind}:not-a-number") is None
    assert _numeric_checkpoint("session-ordinal:4096") is None


def test_other_readers_never_see_evidence_without_its_receipt(tmp_path, monkeypatch):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    observations = []
    record_evidence = jobs.record_evidence

    def observed(*args, **kwargs):
        observations.append((records.count(), jobs.require(job.job_id).stored))
        return record_evidence(*args, **kwargs)

    monkeypatch.setattr(jobs, "record_evidence", observed)
    scheduled = []

    def after_commit(record):
        scheduled.append(
            (records.get(record.evidence_id).verbatim, jobs.require(job.job_id).stored)
        )

    completed = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs, on_evidence=after_commit).run(
            adapter=FixtureAdapter(
                [ScannedEvidence(evidence=evidence("1"), cursor=cursor("line:1"))]
            ),
            job_id=job.job_id,
        )
    )
    assert observations == [(0, 0)]
    assert scheduled == [("message 1", 1)]
    assert completed.stored == records.count() == 1


def test_interrupt_cannot_split_evidence_from_receipt(tmp_path, monkeypatch):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    job, token = jobs.claim(job.job_id)
    runner = ImportRunner(evidence_store=records, job_store=jobs)
    entered, release, stopping, stopped = (threading.Event() for _ in range(4))
    record_evidence = jobs.record_evidence

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return record_evidence(*args, **kwargs)

    def interrupt():
        stopping.set()
        result = jobs.interrupt_running(job.job_id)
        stopped.set()
        return result

    monkeypatch.setattr(jobs, "record_evidence", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(
            runner._record_event,
            ScannedEvidence(evidence=evidence("1"), cursor=cursor("line:1")),
            job=job,
            job_id=job.job_id,
            runner_token=token,
            pending=_PendingSkips(),
        )
        try:
            assert entered.wait(3)
            stopper = pool.submit(interrupt)
            assert stopping.wait(3)
            assert not stopped.wait(0.2), "interrupt committed between Evidence and receipt"
        finally:
            release.set()
        assert writer.result(timeout=3).stored is not None
        stopper.result(timeout=3)
    current = jobs.require(job.job_id)
    assert current.status is ImportStatus.INTERRUPTED
    assert current.stored == records.count() == 1
    assert current.merged == 0 and current.checkpoint == "line:1"
    resumed = asyncio.run(
        runner.run(
            adapter=FixtureAdapter(
                [ScannedEvidence(evidence=evidence("2"), cursor=cursor("line:2"))]
            ),
            job_id=job.job_id,
            max_work_events=2,
        )
    )
    assert resumed.stored == records.count() == 2
    assert resumed.merged == 0


@pytest.mark.parametrize("change", ["pause", "cancel", "interrupt", "new-runner"])
def test_waiting_evidence_writer_respects_job_owner_change(tmp_path, change):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    job, token = jobs.claim(job.job_id)
    runner = ImportRunner(evidence_store=records, job_store=jobs)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with jobs._connect(writing=True) as db:
            if change == "new-runner":
                db.execute(
                    "UPDATE import_jobs SET runner_token='replacement' WHERE job_id=?",
                    (job.job_id,),
                )
            else:
                status = {
                    "pause": ImportStatus.PAUSED,
                    "cancel": ImportStatus.CANCELLED,
                    "interrupt": ImportStatus.INTERRUPTED,
                }[change]
                db.execute(
                    "UPDATE import_jobs SET status=?, runner_token=NULL WHERE job_id=?",
                    (status, job.job_id),
                )
            writer = pool.submit(
                runner._record_event,
                ScannedEvidence(evidence=evidence("1"), cursor=cursor("line:1")),
                job=job,
                job_id=job.job_id,
                runner_token=token,
                pending=_PendingSkips(),
            )
        outcome = writer.result(timeout=3)
    assert outcome.stop is not None and outcome.stored is None
    assert records.count() == jobs.require(job.job_id).stored == 0
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}


def test_shared_receipt_connection_does_not_commit_its_callers_transaction(tmp_path):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    _, token = jobs.claim(job.job_id)
    with pytest.raises(RuntimeError, match="rollback"), jobs._connect(writing=True) as db:
        result = records.put(evidence("1"), connection=db)
        receipt = jobs.record_evidence(
            job.job_id,
            runner_token=token,
            cursor=cursor("line:1"),
            was_created=result.was_created,
            was_revised=result.was_revised,
            connection=db,
        )
        assert receipt.stored == 1 and receipt.checkpoint == "line:1"
        assert records.count() == jobs.require(job.job_id).stored == 0
        raise RuntimeError("rollback")
    assert records.count() == jobs.require(job.job_id).stored == 0
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}


def test_evidence_and_job_stores_must_share_a_database(tmp_path):
    records, _ = stores(tmp_path)
    jobs = ImportJobStore(tmp_path / "other.sqlite3")
    with pytest.raises(ValueError, match="share one database"):
        ImportRunner(evidence_store=records, job_store=jobs)


@pytest.mark.parametrize("write_fails", [False, True])
def test_cancelled_waiter_delivers_only_committed_evidence_on_event_loop(
    tmp_path, monkeypatch, write_fails
):
    async def scenario():
        records, jobs = stores(tmp_path)
        job = jobs.create(user_id="local", source_id="fixture")
        entered, release = threading.Event(), threading.Event()
        original = jobs.record_evidence
        notifications = []
        loop_thread = threading.get_ident()

        def blocked(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            receipt = original(*args, **kwargs)
            if write_fails:
                raise sqlite3.OperationalError("synthetic receipt rollback")
            return receipt

        def committed(record):
            assert threading.get_ident() == loop_thread
            assert records.get(record.evidence_id) is not None
            assert jobs.require(job.job_id).stored == 1
            notifications.append(record.evidence_id)

        monkeypatch.setattr(jobs, "record_evidence", blocked)
        runner = ImportRunner(evidence_store=records, job_store=jobs, on_evidence=committed)
        task = asyncio.create_task(
            runner.run(
                adapter=FixtureAdapter(
                    [ScannedEvidence(evidence=evidence("1"), cursor=cursor("line:1"))]
                ),
                job_id=job.job_id,
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert not task.done()
        finally:
            release.set()
        with suppress(asyncio.CancelledError):
            await task
        assert notifications == ([] if write_fails else [evidence("1").evidence_id])
        assert records.count() == jobs.require(job.job_id).stored == int(not write_fails)
        if not write_fails:
            resumed = await runner.run(adapter=FixtureAdapter([]), job_id=job.job_id)
            assert resumed.status is ImportStatus.COMPLETED
            assert notifications == [evidence("1").evidence_id]

    asyncio.run(scenario())


def test_failed_second_file_keeps_first_file_cursor_and_replays_only_the_second(
    tmp_path, monkeypatch
):
    """A batch failure must not erase an earlier file's committed cursor."""
    records, jobs = stores(tmp_path)
    first_key = "a" * 64
    second_key = "b" * 64
    job = jobs.create(user_id="local", source_id="fixture")
    original_put = EvidenceStore.put
    calls = {"count": 0}

    def fail_second_file_evidence(self, record, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise sqlite3.OperationalError("synthetic second-file failure")
        return original_put(self, record, **kwargs)

    first_cursor = cursor("line:1", file_key=first_key)
    second_cursor = cursor("line:1", file_key=second_key)
    runner = ImportRunner(evidence_store=records, job_store=jobs)
    first_slice = asyncio.run(
        runner.run(
            adapter=FixtureAdapter(
                [
                    ScannedEvidence(evidence=evidence("1"), cursor=first_cursor),
                    ScanCursorTouch(cursor=first_cursor.model_copy(update={"read_to_end": True})),
                ]
            ),
            job_id=job.job_id,
            max_work_events=2,
        )
    )
    assert first_slice.status is ImportStatus.PENDING
    assert records.count() == 1
    assert jobs.get_source_cursors(user_id="local", source_id="fixture")[first_key].checkpoint == (
        "line:1"
    )

    monkeypatch.setattr(EvidenceStore, "put", fail_second_file_evidence)
    with pytest.raises(sqlite3.OperationalError, match="second-file"):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=FixtureAdapter(
                    [ScannedEvidence(evidence=evidence("2"), cursor=second_cursor)]
                ),
                job_id=job.job_id,
            )
        )

    assert jobs.require(job.job_id).status is ImportStatus.FAILED
    assert records.count() == 1
    cursors = jobs.get_source_cursors(user_id="local", source_id="fixture")
    assert cursors[first_key].checkpoint == "line:1"
    assert second_key not in cursors

    monkeypatch.undo()
    resumed = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter(
                [
                    ScannedEvidence(evidence=evidence("2"), cursor=second_cursor),
                    ScanCursorTouch(cursor=second_cursor.model_copy(update={"read_to_end": True})),
                ]
            ),
            job_id=job.job_id,
        )
    )
    assert resumed.status is ImportStatus.COMPLETED
    assert records.count() == 2
    assert resumed.merged == 0


def test_pending_dispatch_is_recovered_after_a_crash_before_enqueue(tmp_path):
    """A crash after Evidence commit but before the callback must not strand work.

    The import transaction stages `evidence_pending_memory_dispatch` in the same
    commit as Evidence. If the process dies before `on_stable_evidence` runs,
    the row is durable but no callback will ever see it. A restart must drain
    every pending file, and a second drain must be a no-op.
    """
    records, jobs = stores(tmp_path)
    file_key = "c" * 64
    first = evidence("1").model_copy(update={"conversation_id": "conversation-a"})
    second = evidence("2").model_copy(update={"conversation_id": "conversation-b"})

    with records._connect(writing=True) as connection:
        first_stored = records.put(first, connection=connection)
        second_stored = records.put(second, connection=connection)
        records.stage_memory_dispatch(
            first_stored.record,
            file_key=file_key,
            connection=connection,
        )
        records.stage_memory_dispatch(
            second_stored.record,
            file_key=file_key,
            connection=connection,
        )

    recovered = records.take_all_stable_records()
    assert {item.evidence_id for item in recovered} == {
        first_stored.record.evidence_id,
        second_stored.record.evidence_id,
    }
    assert records.take_all_stable_records() == ()
    assert records.count() == 2


def test_non_consuming_take_preserves_pending_for_callback_failure(tmp_path) -> None:
    """A failed/cancelled callback must leave a replayable pending marker.

    `take_stable_file_records(consume=False)` is the read half. The durable
    submit's success is the only event allowed to call the consume half.
    """
    records, _jobs = stores(tmp_path)
    file_key = "d" * 64
    first = evidence("pending-1").model_copy(update={"conversation_id": "conversation-a"})

    with records._connect(writing=True) as connection:
        stored = records.put(first, connection=connection).record
        records.stage_memory_dispatch(
            stored,
            file_key=file_key,
            connection=connection,
        )

    read = records.take_stable_file_records(
        user_id="local",
        source_id=stored.source_id,
        file_key=file_key,
        consume=False,
    )
    assert [record.evidence_id for record in read] == [stored.evidence_id]
    # A second non-consuming read still sees the marker: no dispatch result has
    # been reported yet, so recovery must remain possible.
    assert (
        records.take_stable_file_records(
            user_id="local",
            source_id=stored.source_id,
            file_key=file_key,
            consume=False,
        )
        != ()
    )

    assert (
        records.consume_stable_file_records(
            user_id="local",
            source_id=stored.source_id,
            file_key=file_key,
        )
        == 1
    )
    assert records.take_all_stable_records() == ()


def test_take_all_stable_records_consumes_only_after_read(tmp_path) -> None:
    """The startup compensation consumes each file only once it selected it."""
    records, _jobs = stores(tmp_path)
    file_key = "e" * 64
    first = evidence("startup-1").model_copy(update={"conversation_id": "conversation-a"})
    with records._connect(writing=True) as connection:
        stored = records.put(first, connection=connection).record
        records.stage_memory_dispatch(
            stored,
            file_key=file_key,
            connection=connection,
        )

    recovered = records.take_all_stable_records()
    assert [record.evidence_id for record in recovered] == [stored.evidence_id]
    assert records.take_all_stable_records() == ()


def test_list_pending_dispatch_files_is_read_only_and_stable(tmp_path) -> None:
    """Startup enumeration must not consume markers or depend on insert order."""
    records, _jobs = stores(tmp_path)
    file_key_a = "a" * 64
    file_key_b = "b" * 64
    with records._connect(writing=True) as connection:
        for message_id, file_key in (("list-b", file_key_b), ("list-a", file_key_a)):
            stored = records.put(evidence(message_id), connection=connection).record
            records.stage_memory_dispatch(
                stored,
                file_key=file_key,
                connection=connection,
            )

    expected = (
        ("local", "fixture", file_key_a),
        ("local", "fixture", file_key_b),
    )
    assert records.list_pending_dispatch_files() == expected
    assert records.list_pending_dispatch_files() == expected
    with records._connect() as connection:
        assert (
            connection.execute("SELECT count(*) FROM evidence_pending_memory_dispatch").fetchone()[
                0
            ]
            == 2
        )


def test_startup_two_phase_failure_keeps_marker_until_retry_consumes(tmp_path) -> None:
    """A failed startup submit must leave the marker for the next attempt."""
    records, _jobs = stores(tmp_path)
    file_key = "f" * 64
    with records._connect(writing=True) as connection:
        stored = records.put(evidence("startup-retry"), connection=connection).record
        records.stage_memory_dispatch(
            stored,
            file_key=file_key,
            connection=connection,
        )

    file_identity = ("local", "fixture", file_key)
    assert records.list_pending_dispatch_files() == (file_identity,)
    first_read = records.take_stable_file_records(
        user_id=file_identity[0],
        source_id=file_identity[1],
        file_key=file_identity[2],
        consume=False,
    )
    assert [record.evidence_id for record in first_read] == [stored.evidence_id]

    # The submit failed, so the caller does not consume. Enumeration and a retry
    # still see the same marker and record.
    assert records.list_pending_dispatch_files() == (file_identity,)
    retry_read = records.take_stable_file_records(
        user_id=file_identity[0],
        source_id=file_identity[1],
        file_key=file_identity[2],
        consume=False,
    )
    assert [record.evidence_id for record in retry_read] == [stored.evidence_id]

    assert (
        records.consume_stable_file_records(
            user_id=file_identity[0],
            source_id=file_identity[1],
            file_key=file_identity[2],
        )
        == 1
    )
    assert records.list_pending_dispatch_files() == ()


def test_an_unfinished_read_ahead_of_the_snapshot_is_logged(tmp_path, caplog):
    """The real-machine signature: 262 events had cursor_old > file size.

    Numbers only, no content, and only at the point the value is written.
    """
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:1000").model_copy(update={"observed_size": 1000}),
        was_created=True,
        was_revised=False,
    )
    caplog.set_level("WARNING", logger="one_memory.imports.jobs")

    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:5000").model_copy(update={"observed_size": 1000}),
        was_created=True,
        was_revised=False,
    )

    warnings = [
        record.message
        for record in caplog.records
        if "import_cursor_ahead_of_snapshot" in record.message
    ]
    assert warnings, "an unfinished read ahead of the snapshot must be logged"
    assert "new_checkpoint=byte:5000" in warnings[0]
    assert "observed_size=1000" in warnings[0]
    assert "read_to_end=0" in warnings[0]


def test_a_read_that_reaches_the_end_does_not_raise_the_warning(tmp_path, caplog):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    claimed, token = jobs.claim(job.job_id)
    caplog.set_level("WARNING", logger="one_memory.imports.jobs")

    jobs.record_evidence(
        claimed.job_id,
        runner_token=token,
        cursor=cursor("byte:2000").model_copy(update={"observed_size": 1000, "read_to_end": True}),
        was_created=True,
        was_revised=False,
    )

    assert not [
        record.message
        for record in caplog.records
        if "import_cursor_ahead_of_snapshot" in record.message
    ], "a file that grew during a finished read is not a fault"
