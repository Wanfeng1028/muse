"""A2: the MySQL implementation of the store port.

This is the class that lets `database_access.MainDatabase` be replaced. It wraps
the async `Database` from `memory_server.db` and exposes the same operations the
SQLite store exposes, so call sites do not change shape when the engine does.

Two things worth stating plainly:

- **It is not wired in yet.** Nothing constructs it. Wiring it is the actual
  migration step, and doing that before the bundled server can start (A1-07's
  remaining platform work) would break a working product on a machine with no
  mysqld. So it is built and tested as an implementation, not installed.

- **Checkout is async.** `Database.connection()` is an async context manager.
  Kept async rather than blocking the loop to acquire a connection: blocking is
  how a slow query becomes a stalled server.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

from one_memory.memory_server.db import Database, DatabaseConfig
from one_memory.memory_server.store_port import Store, StoreStats


class NoDatabase(RuntimeError):
    """The MySQL server is not reachable."""


class NestedCheckoutError(RuntimeError):
    """A checkout was attempted inside another."""


class MysqlStore(Store):
    """A store backed by the bundled MySQL."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._checked_out = False
        self._write_waits = 0
        self._read_waits = 0
        self._refused = 0

    def write(self, *, busy_timeout_ms: int | None = None) -> AbstractAsyncContextManager[Any]:
        return self._checkout("write")

    def read(self, *, busy_timeout_ms: int | None = None) -> AbstractAsyncContextManager[Any]:
        return self._checkout("read")

    def _checkout(self, kind: str) -> AbstractAsyncContextManager[Any]:
        return _checkout_context(self, kind)

    def back_up(self, target: Path) -> None:
        """A consistent copy, taken by the platform layer.

        The dump uses `--single-transaction`, so it is consistent without
        locking. Declared here because the port requires it, but the command
        itself is built by `mysql_platform.backup_argv` — a store should not
        shell out on its own.
        """
        raise NotImplementedError("backup is performed by mysql_platform.backup_argv")

    def stats(self) -> StoreStats:
        return StoreStats(
            write_waits=self._write_waits,
            read_waits=self._read_waits,
            refused=self._refused,
        )

    def close(self) -> None:
        # The pool owns the connections; closing them here would leave the
        # Database holding a closed pool. The Database is closed by whoever
        # created it.
        return None


@asynccontextmanager
async def _checkout_context(store: MysqlStore, kind: str) -> Any:
    if store._checked_out:
        # Nested checkout is what the SQLite store also refuses: a second handle
        # on the same work would commit twice.
        store._refused += 1
        raise NestedCheckoutError(f"{kind} inside another checkout")
    if not store._database.connected:
        raise NoDatabase("MySQL is not connected")

    store._checked_out = True
    if kind == "write":
        store._write_waits += 1
    else:
        store._read_waits += 1
    try:
        async with store._database.connection() as connection:
            yield connection
            if kind == "write":
                await _commit(connection)
    finally:
        store._checked_out = False


async def _commit(connection: Any) -> None:
    """Commit across sync and async handles.

    aiomysql's commit is a coroutine; sqlite3's is synchronous. Both are handled
    so the store need not know which engine it holds.
    """
    commit = getattr(connection, "commit", None)
    if commit is None:
        return
    result = commit()
    if hasattr(result, "__await__"):
        await result


def store_from_env() -> MysqlStore:
    """Build a store the way Runtime will once wiring lands."""
    return MysqlStore(Database(DatabaseConfig.from_env()))
