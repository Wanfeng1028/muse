import asyncio
import socket
import threading
import time
from dataclasses import FrozenInstanceError

import pytest

from one_memory.retrieval.index_supervisor import RetrievalIndexSupervisor
from one_memory.retrieval.index_worker import IndexWorkResult


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("supervisor tests must remain offline")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)


class Worker:
    def __init__(self, state="idle", blocking=False):
        self.state = state
        self.entered = threading.Event()
        self.release = threading.Event()
        self.exited = threading.Event()
        self.cancel = None
        self.blocking = blocking
        self.calls = []
        self.thread_ids = set()
        self.active = 0
        self.maximum = 0
        self.closed = False

    def run_once(self, *, cancel=None):
        self.cancel = cancel
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.calls.append(time.monotonic())
        self.thread_ids.add(threading.get_ident())
        self.entered.set()
        try:
            if self.blocking:
                assert self.release.wait(3), "test cleanup failed"
            if self.state == "exception":
                raise RuntimeError("SECRET_RAW_ERROR")
            if self.state == "invalid":
                return object()
            return IndexWorkResult(self.state, "SECRET_REASON")
        finally:
            self.active -= 1
            self.exited.set()

    def close(self):
        self.closed = True


async def until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.002)


def test_stop_waits_for_native_exit_and_does_not_close_resources():
    async def run():
        worker = Worker(blocking=True)
        supervisor = RetrievalIndexSupervisor(worker)
        supervisor.start()
        await until(worker.entered.is_set)
        stopping = asyncio.create_task(supervisor.stop())
        try:
            await until(lambda: worker.cancel.is_set())
            await asyncio.sleep(0.03)
            assert not stopping.done() and not worker.exited.is_set()
            assert supervisor.snapshot().thread_alive
        finally:
            worker.release.set()
            await stopping
        assert worker.exited.is_set()
        assert not supervisor.snapshot().thread_alive
        assert not worker.closed
        assert supervisor.snapshot().state == "stopped"

    asyncio.run(run())


@pytest.mark.parametrize("method", ["stop", "wait"])
def test_async_cancellation_repeatedly_waits_for_native_thread(method):
    async def run():
        worker = Worker(blocking=True)
        supervisor = RetrievalIndexSupervisor(worker)
        supervisor.start()
        await until(worker.entered.is_set)
        task = asyncio.create_task(getattr(supervisor, method)())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await until(lambda: worker.cancel.is_set())
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done()
            assert not worker.exited.is_set()
        finally:
            worker.release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            await supervisor.stop()
        assert worker.exited.is_set() and not supervisor.snapshot().thread_alive
        assert not worker.closed

    asyncio.run(run())


def test_idle_no_trigger_no_spin_and_duplicate_start_rejected():
    async def run():
        worker = Worker()
        supervisor = RetrievalIndexSupervisor(worker, idle_wait_seconds=0.3)
        assert not supervisor.trigger()
        assert worker.calls == []
        supervisor.start()
        try:
            with pytest.raises(RuntimeError, match="index_supervisor_already_started"):
                supervisor.start()
            await until(lambda: len(worker.calls) == 1)
            await asyncio.sleep(0.06)
            assert len(worker.calls) == 1
            assert supervisor.snapshot().last_result == "idle"
        finally:
            await supervisor.stop()
        with pytest.raises(RuntimeError, match="index_supervisor_already_started"):
            supervisor.start()
        assert not supervisor.trigger()

    asyncio.run(run())


def test_trigger_storm_coalesces_during_native_call_without_parallel_workers():
    async def run():
        worker = Worker(blocking=True)
        supervisor = RetrievalIndexSupervisor(worker, idle_wait_seconds=0.5)
        supervisor.start()
        await until(worker.entered.is_set)
        try:
            for _ in range(200):
                assert supervisor.trigger()
            worker.release.set()
            await until(lambda: len(worker.calls) >= 2)
            await asyncio.sleep(0.05)
            assert len(worker.calls) == 2
            assert worker.maximum == 1 and len(worker.thread_ids) == 1
        finally:
            worker.release.set()
            await supervisor.stop()

    asyncio.run(run())


def test_interactive_activity_pauses_index_slices_then_resumes() -> None:
    async def run() -> None:
        worker = Worker()
        interactive = True
        supervisor = RetrievalIndexSupervisor(
            worker,
            yield_wait_seconds=0.02,
            background_should_yield=lambda: interactive,
        )
        supervisor.start()
        try:
            await asyncio.sleep(0.06)
            assert worker.calls == []
            interactive = False
            supervisor.trigger()
            await until(lambda: len(worker.calls) == 1)
        finally:
            await supervisor.stop()

    asyncio.run(run())


@pytest.mark.parametrize(
    "state,code",
    [
        ("exception", "index_worker_failed"),
        ("invalid", "index_worker_invalid_result"),
        ("blocked", "index_worker_blocked"),
    ],
)
def test_failures_have_fixed_error_and_backoff_even_with_triggers(state, code):
    async def run():
        worker = Worker(state)
        supervisor = RetrievalIndexSupervisor(worker, failure_wait_seconds=0.2)
        supervisor.start()
        try:
            await until(lambda: supervisor.snapshot().error_code is not None)
            for _ in range(100):
                supervisor.trigger()
            await asyncio.sleep(0.05)
            assert len(worker.calls) == 1
            snapshot = supervisor.snapshot()
            assert snapshot.error_code == code
            assert "SECRET" not in repr(snapshot)
            await until(lambda: len(worker.calls) >= 2)
            assert worker.calls[1] - worker.calls[0] >= 0.18
        finally:
            await supervisor.stop()

    asyncio.run(run())


@pytest.mark.parametrize("state", ["ready", "excluded"])
def test_backlog_yields_after_maximum_slices(state):
    async def run():
        worker = Worker(state)
        supervisor = RetrievalIndexSupervisor(
            worker, max_consecutive_slices=3, yield_wait_seconds=0.15
        )
        supervisor.start()
        try:
            await until(lambda: len(worker.calls) >= 3)
            for _ in range(50):
                supervisor.trigger()
            await asyncio.sleep(0.04)
            assert len(worker.calls) == 3
            await until(lambda: len(worker.calls) >= 4)
            assert worker.calls[3] - worker.calls[2] >= 0.13
        finally:
            await supervisor.stop()
        assert worker.maximum == 1

    asyncio.run(run())


def test_concurrent_stop_is_idempotent_and_stop_before_start_is_terminal():
    async def run():
        worker = Worker()
        supervisor = RetrievalIndexSupervisor(worker)
        supervisor.start()
        await asyncio.gather(supervisor.stop(), supervisor.stop())
        assert not supervisor.snapshot().thread_alive
        unused = RetrievalIndexSupervisor(worker)
        await unused.stop()
        with pytest.raises(RuntimeError, match="index_supervisor_already_started"):
            unused.start()

    asyncio.run(run())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"idle_wait_seconds": 0},
        {"failure_wait_seconds": float("nan")},
        {"yield_wait_seconds": 0},
        {"max_consecutive_slices": True},
        {"max_consecutive_slices": 257},
    ],
)
def test_invalid_configuration_never_starts_worker(kwargs):
    worker = Worker()
    with pytest.raises(ValueError, match="index_supervisor_invalid_config"):
        RetrievalIndexSupervisor(worker, **kwargs)
    assert worker.calls == []


def test_idle_timeout_polls_again_and_stop_interrupts_long_wait():
    async def run():
        worker = Worker()
        supervisor = RetrievalIndexSupervisor(worker, idle_wait_seconds=0.04)
        supervisor.start()
        try:
            await until(lambda: len(worker.calls) >= 2)
            assert worker.calls[1] - worker.calls[0] >= 0.035
        finally:
            await supervisor.stop()
        long_idle = RetrievalIndexSupervisor(Worker(), idle_wait_seconds=300)
        long_idle.start()
        await until(lambda: long_idle.snapshot().slices == 1)
        started = time.monotonic()
        await long_idle.stop()
        assert time.monotonic() - started < 0.5

    asyncio.run(run())


def test_failure_clears_on_recovery_without_leaking_worker_reason():
    async def run():
        worker = Worker("exception")
        supervisor = RetrievalIndexSupervisor(worker, failure_wait_seconds=0.06)
        supervisor.start()
        try:
            await until(lambda: supervisor.snapshot().failures == 1)
            worker.state = "idle"
            await until(lambda: supervisor.snapshot().slices == 2)
            current = supervisor.snapshot()
            assert current.error_code is None and current.last_result == "idle"
            assert current.failures == 1
            assert "SECRET" not in repr(current)
            with pytest.raises(FrozenInstanceError):
                current.slices = 0
        finally:
            await supervisor.stop()

    asyncio.run(run())


def test_thread_start_failure_is_fixed_and_terminal(monkeypatch):
    def fail(_self):
        raise OSError("SECRET_THREAD_ERROR")

    monkeypatch.setattr(threading.Thread, "start", fail)
    supervisor = RetrievalIndexSupervisor(Worker())
    with pytest.raises(RuntimeError, match="^index_supervisor_start_failed$"):
        supervisor.start()
    assert not supervisor.snapshot().thread_alive
    assert supervisor.snapshot().state == "stopped"
    assert "SECRET" not in repr(supervisor.snapshot())
    asyncio.run(supervisor.stop())


@pytest.mark.parametrize("state", ["deferred", "cancelled"])
def test_nonprogress_results_do_not_drain_in_a_tight_loop(state):
    async def run():
        worker = Worker(state)
        supervisor = RetrievalIndexSupervisor(worker, idle_wait_seconds=0.3)
        supervisor.start()
        try:
            await until(lambda: supervisor.snapshot().slices == 1)
            await asyncio.sleep(0.05)
            assert len(worker.calls) == 1
        finally:
            await supervisor.stop()

    asyncio.run(run())


def test_thread_is_non_daemon_and_joined_without_default_executor_threads():
    async def run():
        before = set(threading.enumerate())
        worker = Worker(blocking=True)
        supervisor = RetrievalIndexSupervisor(worker)
        supervisor.start()
        await until(worker.entered.is_set)
        own = [t for t in threading.enumerate() if t.ident in worker.thread_ids]
        assert len(own) == 1 and not own[0].daemon
        try:
            task = asyncio.create_task(supervisor.stop())
            await until(lambda: worker.cancel.is_set())
            assert set(threading.enumerate()) - before == set(own)
        finally:
            worker.release.set()
            await task
        assert not own[0].is_alive()
        assert set(threading.enumerate()) == before

    asyncio.run(run())
