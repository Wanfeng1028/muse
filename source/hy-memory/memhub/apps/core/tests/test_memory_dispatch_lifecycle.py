"""Exercise the automatic enqueue boundary without producing substitute memories."""

import asyncio
import threading
from datetime import UTC, datetime

from one_memory.imports.models import WrittenBy
from one_memory.memory_processing import MemoryProcessingSupervisor
from one_memory.memory_queue import QueuedWork
from tests.test_memory_processing import _put, _setup, _task


def supervisor_for(tmp_path, runner=None):
    evidence, profiles, tasks, governance, secrets, _profile = _setup(tmp_path)
    supervisor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
        runner_factory=(lambda: runner) if runner is not None else None,
    )
    record = _put(
        evidence,
        message_id="dispatch-input",
        role="user",
        written_by=WrittenBy.PERSON,
        content="保留原话并检查是否进入处理队列。",
    )
    return supervisor, record


def work(identity):
    return QueuedWork(task_id=identity, at=datetime.now(UTC), fresh=True, all_apps=True, length=10)


def test_arrival_during_preparation_does_not_cancel_recorded_work(tmp_path, monkeypatch):
    async def scenario():
        supervisor, record = supervisor_for(tmp_path)
        started, release, second_started = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def prepare(seed, **_kwargs):
            calls.append(seed.evidence_id)
            if len(calls) == 1:
                started.set()
                assert release.wait(5)
            else:
                second_started.set()
            return [], []

        monkeypatch.setattr(supervisor, "_prepare_conversation_work", prepare)
        supervisor.enqueue_evidence(record)
        try:
            assert await asyncio.to_thread(started.wait, 3)
            preparation = next(iter(supervisor._preparations.values()))
            supervisor.enqueue_evidence(record)
            await asyncio.sleep(0)
            assert not preparation.done(), "new evidence cancelled the active preparation"
            release.set()
            assert await asyncio.to_thread(second_started.wait, 3)
            assert len(calls) == 2
        finally:
            release.set()
            await supervisor.shutdown()

    asyncio.run(scenario())


def test_work_arriving_as_worker_exits_is_not_stranded(tmp_path):
    async def scenario():
        calls = []
        second_dispatched = asyncio.Event()
        supervisor, record = supervisor_for(tmp_path)
        profile = supervisor.profiles.active(supervisor.secrets)
        first = _task(supervisor.tasks, profile, record, suffix="first")
        second = _task(supervisor.tasks, profile, record, suffix="second")

        class Runner:
            async def run(self, identity, *, timeout=None):
                calls.append(identity)
                if identity == first.task_id:
                    # Runs after _work returns, before its done callback removes it.
                    asyncio.get_running_loop().call_soon(
                        supervisor._schedule_tasks, [work(second.task_id)]
                    )
                else:
                    second_dispatched.set()

        supervisor.runner_factory = lambda: Runner()
        try:
            supervisor._schedule_tasks([work(first.task_id)])
            await asyncio.wait_for(second_dispatched.wait(), timeout=3)
            assert calls == [first.task_id, second.task_id]
            assert len(supervisor._queue) == 0
        finally:
            await supervisor.shutdown()

    asyncio.run(scenario())


def test_shutdown_rejects_new_debounce_and_queue_work(tmp_path):
    async def scenario():
        supervisor, record = supervisor_for(tmp_path)
        await supervisor.shutdown()
        supervisor.enqueue_evidence(record)
        supervisor._schedule_tasks([work("late")])
        try:
            assert supervisor._debounces == {}, "shutdown allowed another delayed reader"
            assert len(supervisor._queue) == 0
            assert supervisor._workers == {}
        finally:
            await supervisor.shutdown()

    asyncio.run(scenario())


def test_shutdown_waits_for_local_preparation_without_starting_hy(tmp_path, monkeypatch):
    async def scenario():
        calls = []

        class Runner:
            async def run(self, identity, *, timeout=None):
                calls.append(identity)

        supervisor, record = supervisor_for(tmp_path, Runner())
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def prepare(_seed, **_kwargs):
            started.set()
            assert release.wait(5)
            finished.set()
            return [], [work("recorded-before-exit")]

        monkeypatch.setattr(supervisor, "_prepare_conversation_work", prepare)
        supervisor.enqueue_evidence(record)
        assert await asyncio.to_thread(started.wait, 3)
        preparation = next(iter(supervisor._preparations.values()))
        stopping = asyncio.create_task(supervisor.shutdown())
        try:
            for _ in range(8):
                await asyncio.sleep(0)
            assert not stopping.done(), "shutdown detached a preparation that can still write"
            assert not preparation.done()
            release.set()
            await asyncio.wait_for(stopping, 2)
            assert finished.is_set()
            assert calls == []
            assert supervisor._preparations == {}
            assert supervisor._debounces == {}
            assert len(supervisor._queue) == 0
        finally:
            release.set()
            await supervisor.shutdown()
            await stopping

    asyncio.run(scenario())


def test_new_arrivals_coalesce_behind_one_active_preparation(tmp_path, monkeypatch):
    async def scenario():
        supervisor, record = supervisor_for(tmp_path)
        started, release, second_finished = threading.Event(), threading.Event(), threading.Event()
        calls = []
        active = 0
        peak = 0

        def prepare(seed, **_kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            calls.append(seed.evidence_id)
            try:
                if len(calls) == 1:
                    started.set()
                    assert release.wait(5)
                else:
                    second_finished.set()
                return [], []
            finally:
                active -= 1

        monkeypatch.setattr(supervisor, "_prepare_conversation_work", prepare)
        supervisor.enqueue_evidence(record)
        try:
            assert await asyncio.to_thread(started.wait, 3)
            for _ in range(20):
                supervisor.enqueue_evidence(record)
                await asyncio.sleep(0)
            # Allow the replacement debounce to finish while the preparation is blocked.
            await asyncio.sleep(0.8)
            assert calls == [record.evidence_id]
            release.set()
            assert await asyncio.to_thread(second_finished.wait, 3)
            assert calls == [record.evidence_id] * 2
            assert peak == 1
        finally:
            release.set()
            await supervisor.shutdown()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# A runner that raises must leave a trace.
#
# `_work` used to end in `except Exception: continue`. When bb5e432 started
# passing `timeout=` to `runner.run`, every runner written against the old
# signature raised TypeError on the call itself; the supervisor swallowed it,
# no task was dispatched, and nothing anywhere said so. These tests pin the
# opposite: an unexpected failure is logged and the task leaves `pending` /
# `running`, while failures the runner already settled keep the runner's state.
# ---------------------------------------------------------------------------


def _dispatch_setup(tmp_path, runner, monkeypatch):
    from one_memory import memory_processing
    from one_memory.memory_tasks import MemoryTaskKind

    evidence, profiles, tasks, governance, secrets, profile = _setup(tmp_path)
    record = _put(
        evidence,
        message_id="dispatch-failure",
        role="user",
        written_by=WrittenBy.PERSON,
        content="这条原话的任务会遇到一个出错的 runner。",
    )
    task = tasks.create(
        request_id=f"native:{record.evidence_id}:{record.revision}:dispatch",
        user_id=record.user_id,
        kind=MemoryTaskKind.EXTRACT,
        input_ref=record.evidence_id,
        profile=profile,
    )
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        memory_processing, "diagnostic_event", lambda **values: events.append(values)
    )
    supervisor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
        runner_factory=lambda: runner,
    )
    return supervisor, tasks, task, events


async def _until(predicate, *, seconds: float = 3.0) -> bool:
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _dispatch_failures(events, task_id):
    return [
        event
        for event in events
        if event.get("event") == "memory_scheduler.dispatch_failed"
        and event.get("task_id") == task_id
    ]


def test_a_runner_that_cannot_be_called_is_recorded_not_skipped(tmp_path, monkeypatch):
    """The exact shape of the bb5e432 regression: `run()` rejects `timeout=`."""
    from one_memory.memory_tasks import MemoryTaskStatus

    calls: list[str] = []

    class OldSignatureRunner:
        async def run(self, task_id: str) -> None:
            calls.append(task_id)

    supervisor, tasks, task, events = _dispatch_setup(tmp_path, OldSignatureRunner(), monkeypatch)

    async def scenario() -> None:
        supervisor.resume()
        try:
            await _until(lambda: tasks.require(task.task_id).status is not MemoryTaskStatus.PENDING)
        finally:
            await supervisor.shutdown()

    asyncio.run(scenario())

    assert calls == [], "the stub was expected to reject the call before running"
    failures = _dispatch_failures(events, task.task_id)
    assert failures, f"no error diagnostic for the failed dispatch: {events}"
    assert failures[0]["level"] == "error"
    assert failures[0]["error_type"] == "TypeError"
    settled = tasks.require(task.task_id)
    assert settled.status is MemoryTaskStatus.FAILED
    assert settled.last_error_code == "memory_task_dispatch_failed"


def test_a_task_abandoned_mid_run_does_not_stay_running(tmp_path, monkeypatch):
    """A claimed task whose runner blows up must not be left `running`.

    Nothing looks at `running` again until the next process start, so a task
    left there is invisible work that never finishes.
    """
    from one_memory.memory_tasks import MemoryTaskStatus

    holder: dict[str, object] = {}

    class CrashingRunner:
        async def run(self, task_id: str, *, timeout: float | None = None) -> None:
            holder["tasks"].claim(task_id)
            raise RuntimeError("adapter exploded after claim")

    supervisor, tasks, task, events = _dispatch_setup(tmp_path, CrashingRunner(), monkeypatch)
    holder["tasks"] = tasks

    async def scenario() -> None:
        supervisor.resume()
        try:
            await _until(
                lambda: (
                    tasks.require(task.task_id).status
                    not in {MemoryTaskStatus.PENDING, MemoryTaskStatus.RUNNING}
                )
            )
        finally:
            await supervisor.shutdown()

    asyncio.run(scenario())

    failures = _dispatch_failures(events, task.task_id)
    assert failures and failures[0]["error_type"] == "RuntimeError"
    settled = tasks.require(task.task_id)
    assert settled.status is MemoryTaskStatus.FAILED
    assert settled.last_error_code == "memory_task_dispatch_failed"


def test_a_failure_the_runner_already_settled_keeps_the_runners_state(tmp_path, monkeypatch):
    """The timeout path settles the task itself, then raises.

    A wall-clock timeout can fire after the HY call was already in flight, and
    HY has no idempotency key, so the task is settled `unknown` - never
    retryable. The supervisor must not turn that into a terminal failure on
    top; the settlement already happened.
    """
    from one_memory.hy_memory_bridge import HyMemoryBridgeError
    from one_memory.memory_tasks import MemoryTaskStatus

    holder: dict[str, object] = {}
    raised: list[str] = []

    class TimingOutRunner:
        async def run(self, task_id: str, *, timeout: float | None = None) -> None:
            store = holder["tasks"]
            _task, token = store.claim(task_id)
            store.record_hy_invocation(task_id, runner_token=token)
            store.recover_one_running(task_id, reason="hy_memory_timeout")
            raised.append(task_id)
            raise HyMemoryBridgeError("hy_memory_timeout")

    supervisor, tasks, task, events = _dispatch_setup(tmp_path, TimingOutRunner(), monkeypatch)
    holder["tasks"] = tasks

    async def scenario() -> None:
        supervisor.resume()
        try:
            await _until(lambda: bool(raised))
            await asyncio.sleep(0.05)
        finally:
            await supervisor.shutdown()

    asyncio.run(scenario())

    assert raised, "the runner never ran, so this proves nothing"
    settled = tasks.require(task.task_id)
    assert settled.status is MemoryTaskStatus.UNKNOWN
    assert settled.last_error_code == "model_content_outcome_unknown"
    assert _dispatch_failures(events, task.task_id) == []
