"""A2: the sync facade must keep the sync shape call sites already use.

These tests use a fake async store so they run without MySQL, and cover what
breaks silently rather than loudly: entering and exiting *one* context manager,
propagating exceptions, and closing the pool on the right loop.

The behaviour against a real server is recorded in
`docs/contracts/backup-restore-real-mysql.md`'s sibling note and was verified on
8.4.4 (sync `with` -> insert -> SELECT).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from one_memory.memory_server.sync_facade import SyncStoreFacade


class FakeAsyncStore:
    """Records enter/exit pairs so a mismatched pair is observable."""

    def __init__(self) -> None:
        self.entered: list[str] = []
        self.exited: list[str] = []
        self.closed = False

    @asynccontextmanager
    async def _cm(self, kind: str):
        self.entered.append(kind)
        try:
            yield f"{kind}-handle"
        finally:
            self.exited.append(kind)

    def write(self):
        return self._cm("write")

    def read(self):
        return self._cm("read")

    def stats(self):
        return {"ok": True}


@pytest.fixture()
def facade():
    store = FakeAsyncStore()
    made = SyncStoreFacade(store)
    yield store, made
    made.close()


def test_write_yields_the_handle_and_exits_exactly_once(facade) -> None:
    """Enter and exit must be the SAME context manager instance.

    Calling `store.write()` again for the exit would build a second manager, so
    the pool would never be released — a leak that looks like normal operation
    until the pool is exhausted.
    """
    store, made = facade
    with made.write() as handle:
        assert handle == "write-handle"
    assert store.entered == ["write"]
    assert store.exited == ["write"], "exit must pair with the same manager"


def test_read_uses_the_read_path(facade) -> None:
    store, made = facade
    with made.read() as handle:
        assert handle == "read-handle"
    assert store.entered == ["read"] and store.exited == ["read"]


def test_an_exception_inside_the_block_still_exits(facade) -> None:
    """A leaked checkout on the error path is how a pool dies after one failure."""
    store, made = facade
    with pytest.raises(RuntimeError), made.write():
        raise RuntimeError("boom")
    assert store.exited == ["write"], "the checkout must be released on error"


def test_facade_runs_on_its_own_thread(facade) -> None:
    """The whole point: the caller's loop must not be the one doing MySQL I/O."""
    import threading

    store, made = facade
    seen: list[str] = []
    with made.write():
        seen.append(threading.current_thread().name)

    assert seen == [threading.main_thread().name], "the block runs on the caller"
    assert made._thread is not threading.current_thread()
    assert made._thread.name == "one-memory-store-facade"


def test_reentry_from_the_worker_thread_is_refused(facade) -> None:
    """Entering from the facade's own thread would wait on work only that
    thread can run. Refusing beats hanging.

    Submitted *as a coroutine on the facade loop*, so it really runs on the
    worker thread — `asyncio.to_thread` would run it on a different thread and
    would not exercise the guard at all.
    """
    from one_memory.memory_server.sync_facade import FacadeReentry

    store, made = facade

    async def on_worker_thread():
        with made.write():
            return "entered"

    future = asyncio.run_coroutine_threadsafe(on_worker_thread(), made._loop)
    with pytest.raises(FacadeReentry):
        future.result(timeout=10)


def test_close_is_idempotent(facade) -> None:
    store, made = facade
    made.close()
    made.close()  # must not raise
