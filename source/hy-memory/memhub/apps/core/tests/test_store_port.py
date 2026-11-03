"""A1-04/A2: the store port, and that real implementations satisfy it.

Async cases use `asyncio.run` rather than an async test plugin: this repo has
no pytest-asyncio installed, and a plugin-based async test would be *skipped
silently* if the plugin were missing — which is worse than no test, because the
suite would look green.
"""

from __future__ import annotations

import asyncio

import pytest

from one_memory.memory_server.mysql_store import (
    MysqlStore,
    NestedCheckoutError,
    NoDatabase,
)
from one_memory.memory_server.store_port import StoreStats, conforms


def test_a_complete_store_conforms() -> None:
    ok, missing = conforms(MysqlStore)
    assert ok, f"missing: {missing}"
    assert missing == ()


@pytest.mark.parametrize("absent", ["write", "read", "back_up", "stats", "close"])
def test_a_store_missing_an_operation_does_not_conform(absent: str) -> None:
    class Partial:
        write = None if absent == "write" else (lambda self: None)
        read = None if absent == "read" else (lambda self: None)
        back_up = None if absent == "back_up" else (lambda self, t: None)
        stats = None if absent == "stats" else (lambda self: StoreStats())
        close = None if absent == "close" else (lambda self: None)

    ok, missing = conforms(Partial)
    assert ok is False
    assert absent in missing


def test_conformance_is_structural_not_by_inheritance() -> None:
    """A store that cannot import this module can still be checked."""

    class Unrelated:
        def write(self, **kwargs):
            raise NotImplementedError

        def read(self, **kwargs):
            raise NotImplementedError

        def back_up(self, target):
            raise NotImplementedError

        def stats(self):
            return StoreStats()

        def close(self):
            return None

    assert conforms(Unrelated)[0] is True


def test_the_live_sqlite_store_satisfies_the_port() -> None:
    """The store in use today must meet the port, or the port is fiction.

    This is the check that makes the port trustworthy: if the implementation
    everyone depends on does not satisfy it, then "swap the implementation"
    cannot work, and the port is describing a shape nothing has.
    """
    from one_memory.database_access import MainDatabase

    ok, missing = conforms(MainDatabase)
    assert ok, f"MainDatabase does not satisfy the store port; missing: {missing}"


class _FakeDatabase:
    def __init__(self, connected: bool = True) -> None:
        self._connected = connected
        self.acquired = 0
        self.commits = 0

    @property
    def connected(self) -> bool:
        return self._connected

    def connection(self):
        outer = self

        class _Conn:
            async def __aenter__(self_inner):
                outer.acquired += 1
                return outer

            async def __aexit__(self_inner, *_exc):
                return None

        return _Conn()

    def commit(self) -> None:
        self.commits += 1


def test_a_write_checkout_acquires_and_commits() -> None:
    database = _FakeDatabase()
    store = MysqlStore(database)

    async def run() -> None:
        async with store.write() as connection:
            assert connection is database

    asyncio.run(run())
    assert database.acquired == 1
    assert database.commits == 1
    assert store.stats().write_waits == 1


def test_a_read_checkout_does_not_commit() -> None:
    database = _FakeDatabase()
    store = MysqlStore(database)

    async def run() -> None:
        async with store.read():
            pass

    asyncio.run(run())
    assert database.commits == 0
    assert store.stats().read_waits == 1


def test_nested_checkout_is_refused() -> None:
    """A second handle on the same work would commit twice."""
    store = MysqlStore(_FakeDatabase())

    async def run() -> None:
        # Two nested checkouts: the inner one must be refused.
        async with store.write(), store.write():
            pass

    with pytest.raises(NestedCheckoutError):
        asyncio.run(run())
    assert store.stats().refused == 1


def test_no_server_means_no_checkout() -> None:
    store = MysqlStore(_FakeDatabase(connected=False))

    async def run() -> None:
        async with store.write():
            pass

    with pytest.raises(NoDatabase):
        asyncio.run(run())


def test_stats_default_to_zero() -> None:
    stats = MysqlStore(_FakeDatabase()).stats()
    assert stats == StoreStats()
