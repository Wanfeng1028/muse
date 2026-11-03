"""A poll that finds nothing must not leave an import job behind.

Live sync polls every source on a timer and the file watcher triggers the same
path again on every write. Both create a full import job — a row to insert, a
claim to write, a heartbeat, a terminal transition — before asking whether the
source has anything new at all. On a real machine that was 83 new `sync` jobs
in a few minutes with nothing to show for them.

Each guard here is written after its positive twin was seen to pass on
b867261: the behaviour these tests deny is the behaviour that shipped.
"""

from __future__ import annotations

import asyncio

from one_memory.imports.adapters import (
    ScanCursorTouch,
    ScannedEvidence,
    ScanOptions,
    ScanPhase,
    ScanProgressEvent,
    SourceCapabilities,
    SourceCursor,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.live_sync import LiveSyncState, PollingLiveSyncSupervisor
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor

_DESCRIPTOR = SourceDescriptor(
    source_id="fixture",
    display_name="Fixture",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=False,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


def _cursor(*, checkpoint: str = "byte:10") -> SourceCursor:
    return SourceCursor(
        file_key="a" * 64,
        file_identity="fixture.jsonl",
        checkpoint=checkpoint,
        checkpoint_anchor="b" * 64,
        observed_size=10,
        observed_modified_ns=1,
        read_to_end=True,
    )


def _evidence(message_id: str) -> EvidenceInput:
    return EvidenceInput(
        source_id="fixture",
        conversation_id="conversation",
        message_id=message_id,
        role="user",
        written_by=WrittenBy.PERSON,
        verbatim="A turn the user just typed",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
    )


class SettledAdapter:
    """Nothing has changed since the last scan.

    This is what every T17 adapter yields when no file has moved:
    `list_changed_files` filters the unchanged ones out at discovery, so
    `read_listed` is handed an empty list and only the progress events survive.
    """

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.scans = 0

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        self.scans += 1
        yield ScanProgressEvent(phase=ScanPhase.DISCOVER)
        yield ScanProgressEvent(phase=ScanPhase.DONE)


class AwakeningAdapter:
    """Settled until the user types, then one new turn."""

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.scans = 0
        self.has_news = False

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        self.scans += 1
        yield ScanProgressEvent(phase=ScanPhase.DISCOVER)
        if self.has_news:
            yield ScannedEvidence(
                evidence=_evidence("message-1"),
                cursor=_cursor(checkpoint="byte:20"),
            )
        yield ScanProgressEvent(phase=ScanPhase.DONE)


class CursorOnlyAdapter:
    """The file moved but yielded no new turn; the cursor still has to advance."""

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.scans = 0

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        self.scans += 1
        yield ScanProgressEvent(phase=ScanPhase.DISCOVER)
        yield ScanCursorTouch(cursor=_cursor(checkpoint="byte:30"))
        yield ScanProgressEvent(phase=ScanPhase.DONE)


class CountingInFlightAdapter:
    """Records how many scans of this source overlapped.

    The first scan waits to be cancelled, standing in for a history catch-up
    that is still working through the source.
    """

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.entered = asyncio.Event()

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if not self.entered.is_set():
                self.entered.set()
                await asyncio.Event().wait()
            yield ScanProgressEvent(phase=ScanPhase.DONE)
        finally:
            self.in_flight -= 1


class FailingAdapter:
    """The source cannot be read at all."""

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.scans = 0

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        self.scans += 1
        yield ScanProgressEvent(phase=ScanPhase.DISCOVER)
        raise OSError("the source root went away")


class ClosureTrackingAdapter:
    """Records whether a scan that was abandoned part-way got closed."""

    descriptor = _DESCRIPTOR

    def __init__(self) -> None:
        self.closed = 0

    async def detect(self) -> bool:
        return True

    async def scan(self, options: ScanOptions):
        try:
            yield ScanProgressEvent(phase=ScanPhase.DISCOVER)
            yield ScannedEvidence(
                evidence=_evidence("message-1"),
                cursor=_cursor(checkpoint="byte:20"),
            )
            yield ScanProgressEvent(phase=ScanPhase.DONE)
        finally:
            self.closed += 1


def _build(tmp_path, adapter):
    database = tmp_path / "one-memory.sqlite3"
    jobs = ImportJobStore(database)
    imports = ImportSupervisor(
        adapters={"fixture": adapter},
        evidence_store=EvidenceStore(database),
        job_store=jobs,
    )
    live = PollingLiveSyncSupervisor(
        source_ids=("fixture",),
        import_supervisor=imports,
        job_store=jobs,
    )
    return jobs, imports, live


def test_polling_a_settled_source_leaves_no_import_job(tmp_path) -> None:
    """Six polls of a source with nothing new must not write six job rows.

    Positive twin seen passing on b867261: the same six triggers produced
    exactly six `sync` jobs, every one of them completed with nothing stored.
    """

    async def scenario() -> None:
        adapter = SettledAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            for _tick in range(6):
                await live.trigger("fixture")
        finally:
            await imports.shutdown()

        assert [job.operation for job in jobs.list_jobs()] == []
        assert adapter.scans == 6, "the source must still be looked at every tick"

    asyncio.run(scenario())


def test_a_settled_poll_then_a_real_change_creates_exactly_one_job(tmp_path) -> None:
    """The count has to move when the work moves, or it is measuring nothing.

    Both halves run against the same store: three empty polls, then one poll
    with a turn waiting. Only the second half may leave a job behind.
    """

    async def scenario() -> None:
        adapter = AwakeningAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            for _tick in range(3):
                await live.trigger("fixture")
            quiet = len(jobs.list_jobs())

            adapter.has_news = True
            await live.trigger("fixture")
            busy = len(jobs.list_jobs())
        finally:
            await imports.shutdown()

        assert quiet == 0
        assert busy == 1
        stored = jobs.list_jobs()[0]
        assert stored.status is ImportStatus.COMPLETED
        assert stored.stored == 1, "the new turn still has to reach the store"

    asyncio.run(scenario())


def test_a_settled_poll_leaves_the_source_idle_rather_than_degraded(tmp_path) -> None:
    """Nothing to do is not a failure, and must not erase the last success."""

    async def scenario() -> None:
        adapter = AwakeningAdapter()
        adapter.has_news = True
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            await live.trigger("fixture")
            after_success = live.health("fixture")

            adapter.has_news = False
            await live.trigger("fixture")
            after_quiet = live.health("fixture")
        finally:
            await imports.shutdown()

        assert after_success.last_success_at is not None
        assert after_quiet.state is LiveSyncState.IDLE
        assert after_quiet.last_error_code is None
        assert after_quiet.last_success_at == after_success.last_success_at

    asyncio.run(scenario())


def test_a_cursor_that_must_advance_still_creates_a_job(tmp_path) -> None:
    """A moved file with no new turn is work: skip it and we rescan it forever."""

    async def scenario() -> None:
        adapter = CursorOnlyAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            await live.trigger("fixture")
        finally:
            await imports.shutdown()

        assert len(jobs.list_jobs()) == 1

    asyncio.run(scenario())


def test_an_explicitly_requested_sync_still_records_a_job(tmp_path) -> None:
    """Someone who asks for a sync by hand is owed a record of it.

    `POST /api/v1/sources/{id}/sync` answers with the job, and a source that
    turns out to have nothing new must not come back as unavailable.
    """

    async def scenario() -> None:
        adapter = SettledAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            asked = await live.trigger_now("fixture")
            assert asked is not None
            completed = await imports.wait(asked.job_id)
        finally:
            await live.shutdown()
            await imports.shutdown()

        assert asked is not None
        assert asked.status is ImportStatus.PENDING
        assert completed.status is ImportStatus.COMPLETED
        assert len(jobs.list_jobs()) == 1

    asyncio.run(scenario())


def test_an_explicit_sync_returns_before_the_source_scan_finishes(tmp_path) -> None:
    async def scenario() -> None:
        adapter = CountingInFlightAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            asked = await asyncio.wait_for(live.trigger_now("fixture"), timeout=0.5)
            assert asked is not None
            assert asked.status is ImportStatus.PENDING
            await asyncio.wait_for(adapter.entered.wait(), timeout=0.5)
            assert jobs.require(asked.job_id).status is ImportStatus.RUNNING
        finally:
            await live.shutdown()
            await imports.shutdown()

    asyncio.run(scenario())


def test_a_catch_up_in_flight_is_never_scanned_beside(tmp_path) -> None:
    """Two readers on one source means every file read twice.

    History and sync share the cursor, so the check for new work must not add
    a second scan of its own while a catch-up still holds the source.
    """

    async def scenario() -> None:
        adapter = CountingInFlightAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        history = imports.create_job("fixture", operation="history")
        imports.enqueue(history.job_id)
        await adapter.entered.wait()
        try:
            requested = await asyncio.wait_for(live.trigger_now("fixture"), timeout=0.5)
            assert requested is not None
            await asyncio.sleep(0.05)
        finally:
            await live.shutdown()
            await imports.shutdown()

        assert adapter.max_in_flight == 1

    asyncio.run(scenario())


def test_a_source_that_cannot_be_read_still_opens_a_job_to_report_it(tmp_path) -> None:
    """A broken source is not a quiet one.

    The job owns the issue table and the failed status. If the check for new
    work swallowed the error and called it nothing to do, the source would
    stop syncing and never say why.
    """

    async def scenario() -> None:
        adapter = FailingAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        try:
            await live.trigger("fixture")
        finally:
            await imports.shutdown()

        listed = jobs.list_jobs()
        assert len(listed) == 1
        assert listed[0].status is ImportStatus.FAILED

    asyncio.run(scenario())


def test_the_check_for_new_work_closes_the_scan_it_abandons(tmp_path) -> None:
    """The check stops at the first thing worth writing down and walks away.

    The generator it leaves behind is holding the source's open files. This
    app has run a host out of file handles before; an abandoned scan has to be
    closed then and there rather than left to the garbage collector.
    """

    async def scenario() -> None:
        adapter = ClosureTrackingAdapter()
        _jobs, imports, live = _build(tmp_path, adapter)
        try:
            found = await live._has_work("fixture")
            # Asserted with no await in between on purpose. Dropping the last
            # reference would also close the generator, but only once the loop
            # gets round to the finaliser, which is too late to tell apart from
            # closing it here. Nothing has yielded yet, so this is the check
            # that the close was deliberate.
            assert adapter.closed == 1, "the abandoned scan is still open"
        finally:
            await imports.shutdown()

        assert found is True

    asyncio.run(scenario())


def test_the_timer_does_not_accumulate_jobs_while_a_source_sits_quiet(tmp_path) -> None:
    """The poller itself, not just a hand-called trigger, has to stay quiet."""

    async def scenario() -> None:
        adapter = SettledAdapter()
        jobs, imports, live = _build(tmp_path, adapter)
        live.interval_seconds = 0.05
        live.start()
        try:
            await asyncio.sleep(1.0)
        finally:
            await live.shutdown()
            await imports.shutdown()

        assert adapter.scans >= 3, "the timer has to have actually run"
        assert jobs.list_jobs() == []

    asyncio.run(scenario())
