"""A1-02: the MySQL connection pool, health and transaction boundary.

Driver choice follows the HY Memory App: `aiomysql`. Two reasons it suits this
project rather than `asyncmy` or SQLAlchemy:

- It is pure Python over PyMySQL, so it ships without a per-platform compiled
  artifact. A local app bundled for macOS arm64/x64, Linux and Windows would
  otherwise need a build matrix for the driver alone.
- It is the combination the adjacent service already runs in production, so
  its failure modes are documented rather than being discovered here.

Pool parameters follow the HY Memory App's job store (`charset=utf8mb4`,
`minsize=1`, `connect_timeout=5`), with two deliberate differences:

- `autocommit=False`. Their queue commits per statement because it enqueues
  single rows. A2-06 requires Evidence, job and cursor boundary to commit in
  *one* transaction, so transactions are explicit and `commit()` is owned by
  `transaction()`.
- `maxsize` is small and configurable. This is one user's machine, not a
  server handling many tenants; a large pool only lets more work pile up
  against a single disk.

One failure mode is carried over deliberately: HY Memory App hit
`attached to a different loop` when a pool created on one asyncio loop was
used from another. A pool here is bound to the loop that created it, and using
it from elsewhere raises rather than corrupting connections.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)

#: Max simultaneous connections. Local single-user instance; deliberately small.
DEFAULT_MAX_SIZE = 8


@dataclass(frozen=True)
class DatabaseConfig:
    """How to reach the local MySQL instance."""

    #: Path to the Unix socket inside One Memory Home. Preferred over TCP:
    #: nothing else on the machine can reach it, so it needs no credentials
    #: reachable by other processes.
    unix_socket: str | None = None
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "one_memory"
    #: Named, not stored: see `password`.
    password_env: str = "ONE_MEMORY_MYSQL_PASSWORD"
    database: str = "one_memory"
    max_size: int = DEFAULT_MAX_SIZE

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        max_raw = os.getenv("ONE_MEMORY_MYSQL_POOL_MAX_SIZE")
        return cls(
            unix_socket=os.getenv("ONE_MEMORY_MYSQL_SOCKET") or None,
            host=os.getenv("ONE_MEMORY_MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("ONE_MEMORY_MYSQL_PORT", "3306")),
            user=os.getenv("ONE_MEMORY_MYSQL_USER", "one_memory"),
            database=os.getenv("ONE_MEMORY_MYSQL_DATABASE", "one_memory"),
            max_size=int(max_raw) if max_raw else DEFAULT_MAX_SIZE,
        )

    @property
    def password(self) -> str:
        """Read at use time, not copied into the dataclass.

        A frozen dataclass holding the secret would print it in any traceback
        or log that reprs the config, so it is fetched only when connecting.
        """
        return os.getenv(self.password_env, "")


class WrongLoopError(RuntimeError):
    """A pool was used from a different event loop than the one that made it."""


class Database:
    """A pool bound to one event loop."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        """Open the pool, pinned to UTC.

        MySQL `DATETIME` carries no zone, and the server's session zone defaults
        to the machine's local time. Writing a UTC value and reading it back
        then returns it shifted by the local offset — measured here as +08:00,
        which silently corrupted every timestamp comparison (a store's
        optimistic-concurrency check reads "stale" on a row that is current).

        Pinning the session to UTC makes `DATETIME` round-trip as written. This
        is set per connection at checkout rather than globally, so it cannot be
        undone by another part of the process changing the session state.
        """
        # aiomysql ships no type stubs. This matches how the repo already
        # handles the untyped hy_memory SDK rather than loosening mypy globally.
        import aiomysql  # type: ignore[import-untyped]

        self._loop = asyncio.get_running_loop()
        self._pool = await aiomysql.create_pool(
            unix_socket=self._config.unix_socket,
            host=None if self._config.unix_socket else self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            db=self._config.database,
            charset="utf8mb4",
            minsize=1,
            maxsize=self._config.max_size,
            autocommit=False,
            connect_timeout=5,
            #: Runs on every new connection, so a recycled one cannot lose it.
            init_command="SET time_zone = '+00:00'",
        )

    def _check_loop(self) -> None:
        """Refuse cross-loop use instead of silently corrupting connections.

        HY Memory App saw `attached to a different loop` in production from
        exactly this. Failing here turns an opaque driver error into one that
        names the actual mistake.
        """
        if self._pool is None:
            raise RuntimeError("database is not connected")
        current = asyncio.get_running_loop()
        if self._loop is not None and current is not self._loop:
            raise WrongLoopError(
                "pool was created on a different event loop; create a separate Database per loop"
            )

    @property
    def connected(self) -> bool:
        return self._pool is not None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        self._check_loop()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """One explicit transaction: commits on success, rolls back on error.

        A2-06 needs Evidence, the write job and the ingest cursor boundary to
        land together. This is the unit that makes that possible, and why the
        pool is not in autocommit mode.
        """
        self._check_loop()
        async with self.connection() as conn:
            try:
                async with conn.cursor() as cursor:
                    yield cursor
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def health(self) -> dict[str, Any]:
        """A cheap liveness probe. Never raises; callers need a value, not a trap."""
        try:
            self._check_loop()
            async with self.connection() as conn, conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                row = await cursor.fetchone()
            return {"ok": row == (1,), "connected": True}
        except Exception as error:
            return {"ok": False, "connected": self._pool is not None, "error": str(error)}

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self._loop = None
