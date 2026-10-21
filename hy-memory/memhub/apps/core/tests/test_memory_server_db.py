"""A1-02: pool configuration, transaction boundary and loop binding.

No MySQL runs on this machine, so the driver is faked at the `aiomysql` module
boundary rather than skipped. That distinction matters: a skipped test proves
nothing, while a fake pool still exercises *our* logic — commit, rollback and
loop binding are all ours, not the driver's.

The fakes record what was asked for, which lets tests assert the pool settings
that came from the HY Memory App (charset, minsize, connect timeout) and the
ones that deliberately differ (autocommit off).
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from one_memory.memory_server.db import (
    DEFAULT_MAX_SIZE,
    Database,
    DatabaseConfig,
    WrongLoopError,
)


@pytest.fixture()
def fake_aiomysql(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace aiomysql with a recorder that never touches the network."""
    calls: dict[str, Any] = {}

    class FakeCursor:
        def __init__(self) -> None:
            self.executed: list[str] = []

        async def execute(self, sql: str, *_args: object) -> None:
            self.executed.append(sql)

        async def fetchone(self) -> tuple[int]:
            return (1,)

        # The real aiomysql cursor is an async context manager; the fake must
        # match the interface the code under test actually uses.
        async def __aenter__(self) -> FakeCursor:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def cursor(self) -> FakeCursor:
            return FakeCursor()

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            self.rollbacks += 1

    class FakePool:
        def __init__(self) -> None:
            self.conn = FakeConnection()
            self.closed = False
            self.waited = False

        def acquire(self) -> FakeAcquire:
            return FakeAcquire(self.conn)

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            self.waited = True

    class FakeAcquire:
        def __init__(self, conn: FakeConnection) -> None:
            self._conn = conn

        async def __aenter__(self) -> FakeConnection:
            return self._conn

        async def __aexit__(self, *_exc: object) -> None:
            return None

    async def create_pool(**kwargs: Any) -> FakePool:
        calls["create_pool"] = kwargs
        pool = FakePool()
        calls["pool"] = pool
        return pool

    module = types.ModuleType("aiomysql")
    module.create_pool = create_pool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiomysql", module)
    return calls


def test_connect_uses_utf8mb4_and_a_connect_timeout(fake_aiomysql: dict) -> None:
    """Settings carried over from the HY Memory App job store."""

    async def run() -> None:
        database = Database(DatabaseConfig())
        await database.connect()

    asyncio.run(run())
    kwargs = fake_aiomysql["create_pool"]
    assert kwargs["charset"] == "utf8mb4"
    assert kwargs["connect_timeout"] == 5
    assert kwargs["minsize"] == 1


def test_pool_is_not_in_autocommit(fake_aiomysql: dict) -> None:
    """Deliberate difference from HY Memory App: transactions are explicit.

    A2-06 needs Evidence, job and cursor boundary to commit together, which is
    impossible if the pool commits each statement on its own.
    """

    async def run() -> None:
        await Database(DatabaseConfig()).connect()

    asyncio.run(run())
    assert fake_aiomysql["create_pool"]["autocommit"] is False


def test_pool_size_is_bounded_for_a_local_instance(fake_aiomysql: dict) -> None:
    async def run() -> None:
        await Database(DatabaseConfig()).connect()

    asyncio.run(run())
    assert fake_aiomysql["create_pool"]["maxsize"] == DEFAULT_MAX_SIZE


def test_unix_socket_preferred_over_tcp(fake_aiomysql: dict) -> None:
    """A socket inside One Memory Home is unreachable by other processes."""

    async def run() -> None:
        await Database(DatabaseConfig(unix_socket="/tmp/om.sock")).connect()

    asyncio.run(run())
    kwargs = fake_aiomysql["create_pool"]
    assert kwargs["unix_socket"] == "/tmp/om.sock"
    assert kwargs["host"] is None


def test_password_is_read_at_connect_time(
    monkeypatch: pytest.MonkeyPatch, fake_aiomysql: dict
) -> None:
    """The secret must not be copied onto a dataclass that can be reprd."""
    monkeypatch.setenv("ONE_MEMORY_MYSQL_PASSWORD", "s3cret")
    config = DatabaseConfig()
    assert "s3cret" not in repr(config)
    assert config.password == "s3cret"

    async def run() -> None:
        await Database(config).connect()

    asyncio.run(run())
    assert fake_aiomysql["create_pool"]["password"] == "s3cret"


def test_transaction_commits_on_success(fake_aiomysql: dict) -> None:
    async def run() -> None:
        database = Database(DatabaseConfig())
        await database.connect()
        async with database.transaction() as cursor:
            await cursor.execute("INSERT INTO evidence VALUES (1)")

    asyncio.run(run())
    assert fake_aiomysql["pool"].conn.commits == 1
    assert fake_aiomysql["pool"].conn.rollbacks == 0


def test_transaction_rolls_back_on_error(fake_aiomysql: dict) -> None:
    """A failed write must leave nothing behind; half a write is worse than none."""

    async def run() -> None:
        database = Database(DatabaseConfig())
        await database.connect()
        with pytest.raises(RuntimeError):
            async with database.transaction() as cursor:
                await cursor.execute("INSERT INTO evidence VALUES (1)")
                raise RuntimeError("boom")

    asyncio.run(run())
    assert fake_aiomysql["pool"].conn.rollbacks == 1
    assert fake_aiomysql["pool"].conn.commits == 0


def test_cross_loop_use_is_refused(fake_aiomysql: dict) -> None:
    """HY Memory App hit `attached to a different loop` from exactly this."""

    async def make() -> Database:
        database = Database(DatabaseConfig())
        await database.connect()
        return database

    database = asyncio.run(make())

    async def use_elsewhere() -> None:
        with pytest.raises(WrongLoopError):
            async with database.transaction():
                pass

    asyncio.run(use_elsewhere())


def test_use_before_connect_raises() -> None:
    async def run() -> None:
        with pytest.raises(RuntimeError):
            async with Database(DatabaseConfig()).transaction():
                pass

    asyncio.run(run())


def test_health_reports_failure_without_raising(fake_aiomysql: dict) -> None:
    """Health must return a value, not throw; callers render it, not catch it."""

    async def run() -> dict:
        database = Database(DatabaseConfig())
        await database.connect()
        return await database.health()

    assert asyncio.run(run())["ok"] is True


def test_health_of_unconnected_database_is_not_ok() -> None:
    async def run() -> dict:
        return await Database(DatabaseConfig()).health()

    report = asyncio.run(run())
    assert report["ok"] is False
    assert report["connected"] is False


def test_close_releases_the_pool(fake_aiomysql: dict) -> None:
    async def run() -> None:
        database = Database(DatabaseConfig())
        await database.connect()
        await database.close()
        assert not database.connected

    asyncio.run(run())
    assert fake_aiomysql["pool"].closed is True
    assert fake_aiomysql["pool"].waited is True


def test_config_from_env_reads_socket_and_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONE_MEMORY_MYSQL_SOCKET", "/tmp/x.sock")
    monkeypatch.setenv("ONE_MEMORY_MYSQL_POOL_MAX_SIZE", "3")
    config = DatabaseConfig.from_env()
    assert config.unix_socket == "/tmp/x.sock"
    assert config.max_size == 3
