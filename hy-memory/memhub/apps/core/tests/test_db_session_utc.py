"""The MySQL session must be pinned to UTC.

This guards a bug that cost real debugging time: `DATETIME` carries no zone, so
with the server's default local-time session a UTC value written and read back
came back shifted by the local offset (+08 here). It raised nothing — it just
made every stored timestamp wrong, and surfaced as an optimistic-concurrency
check calling a current row "stale".

The assertions here are the general form, not tied to one module, so the same
bug cannot come back through a different store.

Enable it against an isolated MySQL instance with `ONE_MEMORY_MYSQL_SOCKET`;
optional `ONE_MEMORY_MYSQL_USER` selects a non-root test user. The test creates
and removes only the `tz_probe` table in the `one_memory` test database.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from one_memory.memory_server.db import Database, DatabaseConfig

SOCKET = os.environ.get("ONE_MEMORY_MYSQL_SOCKET")

pytestmark = [
    pytest.mark.live,
    pytest.mark.serial,
    pytest.mark.mysql,
    pytest.mark.skipif(not SOCKET, reason="no MySQL socket configured"),
]


def _config(database: str) -> DatabaseConfig:
    return DatabaseConfig(
        unix_socket=SOCKET,
        user=os.environ.get("ONE_MEMORY_MYSQL_USER", "root"),
        database=database,
    )


def test_the_session_timezone_is_utc() -> None:
    """`NOW()` must equal `UTC_TIMESTAMP()`; otherwise writes are shifted."""

    async def scenario() -> bool:
        db = Database(_config("one_memory"))
        try:
            await db.connect()
            async with db.connection() as conn, conn.cursor() as cursor:
                await cursor.execute("SELECT NOW(), UTC_TIMESTAMP()")
                now, utc = await cursor.fetchone()
            return now == utc
        finally:
            await db.close()

    assert asyncio.run(scenario()), "MySQL session is not UTC; timestamps will drift"


def test_a_utc_timestamp_round_trips_exactly() -> None:
    """Write an aware UTC value, read it back, and it must be the same instant."""
    from datetime import UTC, datetime

    stamp = datetime(2026, 9, 26, 10, 6, 16, 212414, tzinfo=UTC)

    async def scenario() -> object:
        db = Database(_config("one_memory"))
        try:
            await db.connect()
            async with db.connection() as conn, conn.cursor() as cursor:
                await cursor.execute("DROP TABLE IF EXISTS tz_probe")
                await cursor.execute(
                    "CREATE TABLE tz_probe (id INT PRIMARY KEY, t DATETIME(6) NOT NULL)"
                )
                await cursor.execute("INSERT INTO tz_probe VALUES (1, %s)", (stamp,))
                await conn.commit()
                await cursor.execute("SELECT t FROM tz_probe WHERE id=1")
                row = await cursor.fetchone()
                await cursor.execute("DROP TABLE tz_probe")
                await conn.commit()
            return row[0]
        finally:
            await db.close()

    got = asyncio.run(scenario())
    # MySQL returns a naive datetime; the stored value is UTC, so attaching UTC
    # is a correction, not a guess.
    aware = got.replace(tzinfo=UTC) if got.tzinfo is None else got
    assert aware == stamp, f"timestamp drifted: wrote {stamp}, read {got}"
