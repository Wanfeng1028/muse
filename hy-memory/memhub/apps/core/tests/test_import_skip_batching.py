import asyncio
import sqlite3
import threading
from contextlib import contextmanager, suppress

import pytest

from one_memory.imports import runner as runner_module
from one_memory.imports.adapters import (
    ScanFailure,
    ScanIssueCode,
    ScannedEvidence,
    ScanPhase,
    ScanProgressEvent,
    ScanSkip,
)
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.runner import ImportRunner
from tests.test_import_runner import FixtureAdapter, cursor, evidence, stores


def skip(index, *, file_key="a" * 64, reason=ScanIssueCode.NO_TEXT, report=False):
    return ScanSkip(
        cursor=cursor(f"line:{index}", file_key=file_key),
        reason_code=reason,
        report_issue=report,
        conversation_id="synthetic",
    )


def run_events(tmp_path, events, *, after_scan=None):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    result = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter(events, after_scan=after_scan), job_id=job.job_id
        )
    )
    return records, jobs, result


def test_batch_limit_and_tail_use_fewer_commits(tmp_path, monkeypatch):
    monkeypatch.setattr("one_memory.imports.runner._EVIDENCE_BATCH_SECONDS", 60.0)
    batch = runner_module.EVIDENCE_BATCH_RECORDS
    real_connect = ImportJobStore._connect
    updates = []

    @contextmanager
    def traced(self, **kwargs):
        with real_connect(self, **kwargs) as db:
            db.set_trace_callback(
                lambda sql: updates.append(sql) if "skipped = skipped +" in sql else None
            )
            yield db

    monkeypatch.setattr(ImportJobStore, "_connect", traced)
    total = batch * 2 + 2
    records, jobs, result = run_events(tmp_path, [skip(i) for i in range(1, total + 1)])
    assert result.skipped == result.discovered == total
    assert result.checkpoint == f"line:{total}"
    assert records.count() == 0
    assert jobs.skip_reason_counts(result.job_id) == {"no_text": total}
    assert len(updates) == 3


@pytest.mark.parametrize("boundary", ["evidence", "reason", "file"])
def test_batched_skips_keep_their_order_against_the_next_write(tmp_path, boundary):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    if boundary == "evidence":
        event = ScannedEvidence(evidence=evidence("2"), cursor=cursor("line:2"))
    elif boundary == "reason":
        event = skip(2, reason=ScanIssueCode.UNKNOWN_RECORD)
    else:
        event = skip(2, file_key="b" * 64)
    completed = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter([skip(1), event]), job_id=job.job_id
        )
    )
    assert completed.status is ImportStatus.COMPLETED
    assert completed.checkpoint == "line:2"
    assert completed.skipped == (1 if boundary == "evidence" else 2)
    assert jobs.skip_reason_counts(job.job_id) == (
        {"no_text": 1, "unknown_record": 1}
        if boundary == "reason"
        else {"no_text": completed.skipped}
    )
    cursors = jobs.get_source_cursors(user_id="local", source_id="fixture")
    assert {key: item.checkpoint for key, item in cursors.items()} == (
        {"a" * 64: "line:1", "b" * 64: "line:2"} if boundary == "file" else {"a" * 64: "line:2"}
    )


@pytest.mark.parametrize("boundary", ["progress", "error", "issue"])
def test_flushes_before_every_nonmatching_event(tmp_path, monkeypatch, boundary):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    checked = []
    if boundary == "progress":
        event = ScanProgressEvent(phase=ScanPhase.READ)
        name = "record_progress"
    elif boundary == "error":
        event = ScanFailure(cursor=cursor("line:2"), reason_code=ScanIssueCode.INVALID_JSON)
        name = "record_error"
    else:
        event = skip(2, report=True)
        name = "record_skip"
    original = getattr(jobs, name)

    def inspect(*args, **kwargs):
        current = jobs.require(job.job_id)
        checked.append((current.skipped, current.checkpoint))
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, name, inspect)
    completed = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter([skip(1), event]), job_id=job.job_id
        )
    )
    assert checked == [(1, "line:1")]
    assert completed.status is ImportStatus.COMPLETED
    assert len(jobs.list_issues(job.job_id)) == int(boundary in {"issue", "error"})


def test_idle_reader_flushes_after_100ms_without_cancelling_scan(tmp_path):
    async def scenario():
        records, jobs = stores(tmp_path)
        job = jobs.create(user_id="local", source_id="fixture")
        waiting, release = asyncio.Event(), asyncio.Event()

        class SlowAdapter(FixtureAdapter):
            async def scan(self, options):
                yield skip(1)
                waiting.set()
                await release.wait()
                yield ScannedEvidence(evidence=evidence("2"), cursor=cursor("line:2"))

        task = asyncio.create_task(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=SlowAdapter([]), job_id=job.job_id
            )
        )
        try:
            await asyncio.wait_for(waiting.wait(), 2)
            assert jobs.require(job.job_id).skipped == 0
            for _ in range(80):
                if jobs.require(job.job_id).skipped == 1:
                    break
                await asyncio.sleep(0.01)
            assert jobs.require(job.job_id).skipped == 1
            assert not task.done()
            release.set()
            assert (await task).stored == 1
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_pause_flushes_owned_tail_before_interrupt_and_resumes_exactly(tmp_path):
    async def scenario():
        records, jobs = stores(tmp_path)
        job = jobs.create(user_id="local", source_id="fixture")
        waiting = asyncio.Event()

        class Pausing(FixtureAdapter):
            async def scan(self, options):
                yield skip(1)
                waiting.set()
                await asyncio.Event().wait()

        runner = ImportRunner(evidence_store=records, job_store=jobs)
        task = asyncio.create_task(runner.run(adapter=Pausing([]), job_id=job.job_id))
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        stopped = jobs.require(job.job_id)
        assert stopped.status is ImportStatus.INTERRUPTED
        assert stopped.skipped == 1 and stopped.checkpoint == "line:1"
        resumed = await runner.run(adapter=FixtureAdapter([skip(2)]), job_id=job.job_id)
        assert resumed.skipped == 2 and resumed.checkpoint == "line:2"

    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["pause", "cancel", "new-runner"])
def test_pending_tail_cannot_commit_after_job_owner_change(tmp_path, change):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")

    def change_owner():
        jobs.transition(
            job.job_id, ImportStatus.CANCELLED if change == "cancel" else ImportStatus.PAUSED
        )
        if change == "new-runner":
            jobs.claim(job.job_id)

    result = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter([skip(1)], after_scan=change_owner), job_id=job.job_id
        )
    )
    assert result.skipped == 0 and result.checkpoint is None
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}
    assert result.status is (
        ImportStatus.RUNNING
        if change == "new-runner"
        else ImportStatus.CANCELLED
        if change == "cancel"
        else ImportStatus.PAUSED
    )


def test_skip_batch_rolls_back_cursor_and_counters_on_write_failure(tmp_path, monkeypatch):
    _, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    _, token = jobs.claim(job.job_id)
    original = jobs._upsert_cursor

    def fail(*args):
        original(*args)
        raise sqlite3.OperationalError("synthetic transaction failure")

    monkeypatch.setattr(jobs, "_upsert_cursor", fail)
    with pytest.raises(sqlite3.OperationalError):
        jobs._record_skip_batch(
            job.job_id, runner_token=token, cursor=cursor("line:8"), reason_code="no_text", amount=8
        )
    assert jobs.require(job.job_id).skipped == 0
    assert jobs.skip_reason_counts(job.job_id) == {}
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}


def test_old_single_skip_method_keeps_return_contract(tmp_path):
    _, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    _, token = jobs.claim(job.job_id)
    result = jobs.record_skip(
        job.job_id,
        runner_token=token,
        cursor=cursor("line:1"),
        reason_code="no_text",
        report_issue=True,
    )
    assert result.skipped == 1 and result.checkpoint == "line:1"
    assert len(jobs.list_issues(job.job_id)) == 1


def test_unpersisted_useful_record_never_gets_a_later_skip_cursor(tmp_path, monkeypatch):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")

    def fail(_, *, connection=None):
        raise sqlite3.OperationalError("synthetic evidence failure")

    monkeypatch.setattr(records, "put", fail)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=FixtureAdapter(
                    [
                        skip(1),
                        ScannedEvidence(evidence=evidence("2"), cursor=cursor("line:2")),
                        skip(3),
                    ]
                ),
                job_id=job.job_id,
            )
        )
    # The skip before the failed original shares its transaction and replays with it.
    result = jobs.require(job.job_id)
    assert result.status is ImportStatus.FAILED
    assert result.skipped == 0 and result.checkpoint is None
    assert jobs.get_source_cursors(user_id="local", source_id="fixture") == {}
    assert records.count() == 0


@pytest.mark.parametrize("committed_prefix", [0, runner_module.EVIDENCE_BATCH_RECORDS])
def test_crash_replays_only_uncommitted_tail(tmp_path, monkeypatch, committed_prefix):
    monkeypatch.setattr("one_memory.imports.runner._EVIDENCE_BATCH_SECONDS", 60.0)
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")

    class Crash(BaseException):
        pass

    class Crashing(FixtureAdapter):
        async def scan(self, options):
            for index in range(1, committed_prefix + 4):
                yield skip(index)
            raise Crash()

    with pytest.raises(Crash):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=Crashing([]), job_id=job.job_id
            )
        )
    assert jobs.require(job.job_id).skipped == committed_prefix
    total = committed_prefix + 5
    jobs.interrupt_running(job.job_id)
    resumed = asyncio.run(
        ImportRunner(evidence_store=records, job_store=jobs).run(
            adapter=FixtureAdapter([skip(i) for i in range(committed_prefix + 1, total + 1)]),
            job_id=job.job_id,
        )
    )
    assert resumed.skipped == total and resumed.checkpoint == f"line:{total}"


def test_reader_failure_flushes_owned_tail_before_failed_status(tmp_path):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")

    class Failing(FixtureAdapter):
        async def scan(self, options):
            yield skip(1)
            raise ValueError("synthetic reader failure")

    with pytest.raises(ValueError, match="synthetic reader failure"):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=Failing([]), job_id=job.job_id
            )
        )
    result = jobs.require(job.job_id)
    assert result.status is ImportStatus.FAILED and result.skipped == 1


def test_cancel_joins_inflight_writer_and_leaves_no_late_commit(tmp_path, monkeypatch):
    async def scenario():
        records, jobs = stores(tmp_path)
        job = jobs.create(user_id="local", source_id="fixture")
        entered, release = threading.Event(), threading.Event()
        original = ImportRunner._record_batch

        def blocked(*args, **kwargs):
            entered.set()
            assert release.wait(3)
            return original(*args, **kwargs)

        monkeypatch.setattr(ImportRunner, "_record_batch", blocked)
        task = asyncio.create_task(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=FixtureAdapter([skip(i) for i in range(1, 65)]), job_id=job.job_id
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done()
            task.cancel()
            await asyncio.sleep(0.02)
            assert not task.done()
            jobs.transition(job.job_id, ImportStatus.CANCELLED)
            release.set()
            with suppress(asyncio.CancelledError):
                await task
            final = jobs.require(job.job_id)
            assert final.status is ImportStatus.CANCELLED and final.skipped == 0
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())


def test_cancelled_old_runner_cannot_interrupt_new_owner(tmp_path):
    _, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")
    _, old_token = jobs.claim(job.job_id)
    jobs.transition(job.job_id, ImportStatus.PAUSED)
    _, new_token = jobs.claim(job.job_id)
    result = jobs.interrupt_running(job.job_id, runner_token=old_token)
    assert result.status is ImportStatus.RUNNING
    assert (
        jobs._record_skip_batch(
            job.job_id,
            runner_token=new_token,
            reason_code="no_text",
            cursor=cursor("line:1"),
            amount=1,
        )
        is None
    )


def test_reader_and_flush_failure_still_marks_job_failed(tmp_path, monkeypatch):
    records, jobs = stores(tmp_path)
    job = jobs.create(user_id="local", source_id="fixture")

    class Failing(FixtureAdapter):
        async def scan(self, options):
            yield skip(1)
            raise ValueError("synthetic reader failure")

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic flush failure")

    monkeypatch.setattr(jobs, "_write_skips", fail)
    with pytest.raises(ValueError, match="synthetic reader failure"):
        asyncio.run(
            ImportRunner(evidence_store=records, job_store=jobs).run(
                adapter=Failing([]), job_id=job.job_id
            )
        )
    result = jobs.require(job.job_id)
    assert result.status is ImportStatus.FAILED
    assert result.skipped == 0 and result.checkpoint is None
