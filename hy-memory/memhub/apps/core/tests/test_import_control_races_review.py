"""Read-only review repro: real runner/store, synthetic delayed adapter cleanup."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from one_memory.imports.adapters import ScanEvent, ScanOptions
from one_memory.imports.jobs import ImportStatus, InvalidJobTransitionError
from one_memory.imports.supervisor import ImportSupervisor
from tests.test_import_supervisor import ControlledAdapter, scanned, stores


class DrainingAdapter(ControlledAdapter):
    def __init__(self) -> None:
        super().__init__([])
        self.started = asyncio.Event()
        self.draining = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
        self.scan_count = 0

    async def scan(self, _: ScanOptions) -> AsyncIterator[ScanEvent]:
        self.scan_count += 1
        self.started.set()
        try:
            await asyncio.Event().wait()
            yield scanned("synthetic")
        finally:
            self.draining.set()
            await self.release.wait()
            self.finished.set()


@pytest.mark.parametrize("first_control", [None, "pause", "cancel"])
def test_shutdown_waits_for_cleanup_already_started_by_job_control(tmp_path, first_control):
    async def scenario() -> None:
        evidence, jobs = stores(tmp_path)
        adapter = DrainingAdapter()
        supervisor = ImportSupervisor(
            adapters={"fixture": adapter}, evidence_store=evidence, job_store=jobs
        )
        job = supervisor.create_job("fixture")
        supervisor.enqueue(job.job_id)
        control = None
        shutdown = None
        try:
            await asyncio.wait_for(adapter.started.wait(), timeout=2)
            assert jobs.require(job.job_id).status is ImportStatus.RUNNING
            if first_control is not None:
                control = asyncio.create_task(getattr(supervisor, first_control)(job.job_id))
                await asyncio.wait_for(adapter.draining.wait(), timeout=2)
                assert not control.done()
            shutdown = asyncio.create_task(supervisor.shutdown())
            await asyncio.wait_for(adapter.draining.wait(), timeout=2)
            done, _ = await asyncio.wait({shutdown}, timeout=0.05)
            assert not adapter.finished.is_set()
            assert not done, (
                f"shutdown returned while {first_control or 'shutdown'} still owns "
                "an unfinished adapter cleanup"
            )
            adapter.release.set()
            await asyncio.wait_for(asyncio.shield(shutdown), timeout=2)
            if control is not None:
                await asyncio.wait_for(asyncio.shield(control), timeout=2)
            assert adapter.finished.is_set()
            assert evidence.count() == 0
        finally:
            adapter.release.set()
            pending = [task for task in (control, shutdown) if task is not None]
            if pending:
                await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=2)
            await supervisor.shutdown()
            assert adapter.finished.is_set()

    asyncio.run(scenario())


def test_cancelled_pause_waiter_does_not_release_cleanup_before_shutdown(tmp_path):
    async def scenario() -> None:
        evidence, jobs = stores(tmp_path)
        adapter = DrainingAdapter()
        supervisor = ImportSupervisor(
            adapters={"fixture": adapter}, evidence_store=evidence, job_store=jobs
        )
        job = supervisor.create_job("fixture")
        supervisor.enqueue(job.job_id)
        runner = supervisor._tasks[job.job_id]
        controls = []
        try:
            await asyncio.wait_for(adapter.started.wait(), timeout=2)
            pause = asyncio.create_task(supervisor.pause(job.job_id))
            controls.append(pause)
            await asyncio.wait_for(adapter.draining.wait(), timeout=2)
            pause.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(pause), timeout=2)
            assert supervisor._tasks.get(job.job_id) is runner
            assert not runner.done() and runner.cancelling() == 1

            shutdown = asyncio.create_task(supervisor.shutdown())
            controls.append(shutdown)
            done, _ = await asyncio.wait({shutdown}, timeout=0.05)
            assert not done and not adapter.finished.is_set()
            assert runner.cancelling() == 1
            adapter.release.set()
            await asyncio.wait_for(asyncio.shield(shutdown), timeout=2)
            assert adapter.finished.is_set() and runner.done()
            assert jobs.require(job.job_id).status is ImportStatus.INTERRUPTED
            assert job.job_id not in supervisor._tasks
            assert job.job_id not in supervisor._drains
            assert evidence.count() == 0
        finally:
            adapter.release.set()
            await asyncio.wait_for(asyncio.gather(*controls, return_exceptions=True), timeout=2)
            await asyncio.wait_for(supervisor.shutdown(), timeout=2)

    asyncio.run(scenario())


@pytest.mark.parametrize("order", [("pause", "cancel"), ("cancel", "pause")])
def test_simultaneous_controls_join_one_cancellation_without_order_assumptions(tmp_path, order):
    async def scenario() -> None:
        evidence, jobs = stores(tmp_path)
        adapter = DrainingAdapter()
        supervisor = ImportSupervisor(
            adapters={"fixture": adapter}, evidence_store=evidence, job_store=jobs
        )
        job = supervisor.create_job("fixture")
        supervisor.enqueue(job.job_id)
        runner = supervisor._tasks[job.job_id]
        controls = {}
        entered = {action: asyncio.Event() for action in order}

        async def invoke(action):
            entered[action].set()
            return await getattr(supervisor, action)(job.job_id)

        try:
            await asyncio.wait_for(adapter.started.wait(), timeout=2)
            controls = {action: asyncio.create_task(invoke(action)) for action in order}
            await asyncio.wait_for(
                asyncio.gather(*(event.wait() for event in entered.values())), timeout=2
            )
            await asyncio.wait_for(adapter.draining.wait(), timeout=2)
            done, _ = await asyncio.wait(set(controls.values()), timeout=0.05)
            assert not done and not adapter.finished.is_set()
            assert runner.cancelling() == 1
            assert supervisor._tasks.get(job.job_id) is runner
            adapter.release.set()
            results = await asyncio.wait_for(
                asyncio.gather(*controls.values(), return_exceptions=True), timeout=2
            )
            receipts = dict(zip(controls, results, strict=True))
            assert receipts["cancel"].status is ImportStatus.CANCELLED
            paused = receipts["pause"]
            if isinstance(paused, BaseException):
                # Cancel may win before pause's final transition; it must not resurrect the job.
                assert isinstance(paused, InvalidJobTransitionError)
            else:
                assert paused.status in {ImportStatus.PAUSED, ImportStatus.CANCELLED}
            assert jobs.require(job.job_id).status is ImportStatus.CANCELLED
            assert runner.cancelling() == 1 and runner.done()
            assert adapter.finished.is_set() and adapter.scan_count == 1
            assert not supervisor._drains and evidence.count() == 0
        finally:
            adapter.release.set()
            await asyncio.wait_for(
                asyncio.gather(*controls.values(), return_exceptions=True), timeout=2
            )
            await asyncio.wait_for(supervisor.shutdown(), timeout=2)

    asyncio.run(scenario())


def test_enqueue_cannot_replace_draining_runner_but_explicit_resume_after_drain_works(tmp_path):
    async def scenario() -> None:
        evidence, jobs = stores(tmp_path)
        adapter = DrainingAdapter()
        supervisor = ImportSupervisor(
            adapters={"fixture": adapter}, evidence_store=evidence, job_store=jobs
        )
        job = supervisor.create_job("fixture")
        supervisor.enqueue(job.job_id)
        runner = supervisor._tasks[job.job_id]
        pause = None
        try:
            await asyncio.wait_for(adapter.started.wait(), timeout=2)
            pause = asyncio.create_task(supervisor.pause(job.job_id))
            await asyncio.wait_for(adapter.draining.wait(), timeout=2)
            assert jobs.require(job.job_id).status is ImportStatus.INTERRUPTED
            before = jobs.require(job.job_id)
            with pytest.raises(InvalidJobTransitionError, match="^import_cleanup_in_progress$"):
                supervisor.enqueue(job.job_id)
            with pytest.raises(InvalidJobTransitionError, match="^import_cleanup_in_progress$"):
                supervisor.resume(job.job_id)
            assert jobs.require(job.job_id) == before
            assert supervisor._tasks.get(job.job_id) is runner
            done, _ = await asyncio.wait({pause}, timeout=0.05)
            assert not done and not runner.done()
            assert adapter.scan_count == 1 and runner.cancelling() == 1
            adapter.release.set()
            receipt = await asyncio.wait_for(asyncio.shield(pause), timeout=2)
            assert receipt.status is ImportStatus.PAUSED
            assert job.job_id not in supervisor._tasks
            assert adapter.finished.is_set()

            supervisor.register_adapter(ControlledAdapter([scanned("resumed")]))
            assert supervisor.resume(job.job_id).status is ImportStatus.PENDING
            assert supervisor._tasks[job.job_id] is not runner
            finished = await asyncio.wait_for(supervisor.wait(job.job_id), timeout=2)
            assert finished.status is ImportStatus.COMPLETED
            assert evidence.count() == 1
        finally:
            adapter.release.set()
            if pause is not None:
                await asyncio.wait_for(asyncio.gather(pause, return_exceptions=True), timeout=2)
            await asyncio.wait_for(supervisor.shutdown(), timeout=2)

    asyncio.run(scenario())


def test_enqueue_does_not_replace_done_runner_before_active_drain_finishes(tmp_path):
    async def scenario() -> None:
        evidence, jobs = stores(tmp_path)
        adapter = DrainingAdapter()
        supervisor = ImportSupervisor(
            adapters={"fixture": adapter}, evidence_store=evidence, job_store=jobs
        )
        job = supervisor.create_job("fixture")
        supervisor.enqueue(job.job_id)
        runner = supervisor._tasks[job.job_id]
        observed = []
        pause = None

        def enqueue_at_runner_completion(completed):
            # Registered before drain awaits runner: observe the real done-callback
            # window before the drain continuation releases its ownership.
            drain = supervisor._drains.get(job.job_id)
            before = (completed.done(), drain is not None and not drain.done())
            job_before = jobs.require(job.job_id)
            error = None
            try:
                supervisor.enqueue(job.job_id)
            except InvalidJobTransitionError as reason:
                error = str(reason)
            observed.append(
                (
                    *before,
                    supervisor._tasks.get(job.job_id) is completed,
                    error,
                    jobs.require(job.job_id) == job_before,
                )
            )

        try:
            await asyncio.wait_for(adapter.started.wait(), timeout=2)
            runner.add_done_callback(enqueue_at_runner_completion)
            pause = asyncio.create_task(supervisor.pause(job.job_id))
            await asyncio.wait_for(adapter.draining.wait(), timeout=2)
            adapter.release.set()
            await asyncio.wait_for(asyncio.shield(pause), timeout=2)
            assert len(observed) == 1 and observed[0][:2] == (True, True)
            assert observed[0][2], "enqueue replaced a done runner while its drain was still active"
            assert observed[0][3:] == ("import_cleanup_in_progress", True)
        finally:
            adapter.release.set()
            if pause is not None:
                await asyncio.wait_for(asyncio.gather(pause, return_exceptions=True), timeout=2)
            await asyncio.wait_for(supervisor.shutdown(), timeout=2)

    asyncio.run(scenario())
