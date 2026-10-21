"""A2: a synchronous facade over the async MySQL store.

Why this exists: `MainDatabase` is a *synchronous* context manager
(`@contextmanager`) and all 74 call sites use `with`. `MysqlStore` is
necessarily async — MySQL I/O must not block the event loop. Changing every
call site means turning each function async, which propagates to every caller;
that is a cross-module change with no way to verify it incrementally while
MySQL is not yet in the user's environment.

So this facade runs the async store on a **dedicated thread with its own event
loop** and exposes the same synchronous shape the call sites already use. The
point is that the migration becomes a one-line change per call site — swap the
accessor function, keep the `with` — instead of an async rewrite.

Three deliberate constraints:

- **One dedicated loop, one thread, reused.** Creating a loop per call would
  bind and discard pools and is also wrong: `Database` binds its pool to the
  loop that created it (WrongLoopError otherwise).
- **`run_coroutine_threadsafe`, not `loop.run_until_complete`.** The facade's
  thread must never block the caller's loop; and if the caller *is* the loop
  thread, `run_until_complete` would deadlock. This submits and waits on the
  calling thread instead.
- **Deadlock guard.** Calling this from the facade's own thread would wait on
  work only that thread can run, so it refuses loudly rather than hanging.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from contextlib import contextmanager
from typing import Any


def _sys_exc_info() -> tuple[Any, Any, Any]:
    return sys.exc_info()


class FacadeReentry(RuntimeError):
    """The facade was used from its own worker thread. That would deadlock."""


class SyncStoreFacade:
    """Runs an async store on one background loop, behind synchronous `with`."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="one-memory-store-facade", daemon=True
        )
        self._started = threading.Event()
        self._thread.start()
        self._started.wait(timeout=10)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def _submit(self, coro: Any) -> Any:
        if threading.current_thread() is self._thread:
            # Close the coroutine: refusing leaves it un-awaited, and an
            # un-awaited coroutine is a RuntimeWarning at GC time.
            coro.close()
            raise FacadeReentry(
                "SyncStoreFacade used from its own worker thread; "
                "that would wait on work only this thread can run"
            )
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    @contextmanager
    def _checkout(self, kind: str, busy_timeout_ms: int | None) -> Any:
        """Enter and exit ONE context manager instance.

        Re-calling `store.write()` would build a *second* manager, so `__aexit__`
        would run on a different object than `__aenter__` — the pool would never
        be released. The manager is created once here and both halves use it.
        """
        manager = self._store.write() if kind == "write" else self._store.read()
        handle = self._submit(manager.__aenter__())
        try:
            yield handle
        except BaseException:
            self._submit(manager.__aexit__(*_sys_exc_info()))
            raise
        else:
            self._submit(manager.__aexit__(None, None, None))

    @contextmanager
    def write(self, *, busy_timeout_ms: int | None = None, autocommit: bool = False) -> Any:
        """Mirror the sync shape of `MainDatabase.write`.

        `autocommit` is accepted and ignored: MySQL commits at checkout exit.
        Accepting it — rather than making callers branch on the engine — is
        what keeps a migrated call site looking the same on both engines.
        """
        with self._checkout("write", busy_timeout_ms) as handle:
            yield handle

    @contextmanager
    def read(self, *, busy_timeout_ms: int | None = None, autocommit: bool = False) -> Any:
        with self._checkout("read", busy_timeout_ms) as handle:
            yield handle

    def stats(self) -> Any:
        return self._store.stats()

    def back_up(self, target: Any) -> None:
        """Mirror the port's `back_up`.

        `MysqlStore.back_up` deliberately raises (the dump is built by
        `mysql_platform.backup_argv`), so this propagates that rather than
        pretending a copy was made. A caller that catches it must treat the
        backup as NOT taken — which is why `library_upgrade` refuses to proceed.
        """
        self._store.back_up(target)

    def connect(self) -> None:
        """Connect the underlying database on this facade's loop.

        Exposed as a method rather than done in `__init__` so the caller decides
        when the pool is created, and so a construction-time failure (no server,
        bad credentials) surfaces at a call the caller can attribute instead of
        inside a constructor.
        """
        database = getattr(self._store, "_database", None)
        if database is None:
            return
        self._submit(database.connect())

    def close(self) -> None:
        """Stop the worker loop. Idempotent: callers may close twice."""
        if self._loop.is_closed():
            return
        # Close the pool ON the worker loop first: aiomysql connections are bound
        # to the loop that created them, and garbage-collecting them afterwards
        # warns "Event loop is closed" while leaking the underlying sockets.
        #
        # `MysqlStore.close()` deliberately does nothing (the Database owns the
        # pool), so the pool is reached through the Database instead; both are
        # attempted and neither may raise out of close().
        try:
            database = getattr(self._store, "_database", None)
            if database is not None:
                self._submit(database.close())
        except Exception:  # noqa: BLE001 - close must not raise
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=10)
        self._loop.close()
