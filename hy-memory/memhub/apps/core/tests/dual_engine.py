"""A harness for running one store operation on SQLite AND on MySQL.

Why: call sites are being migrated to work on both engines. If a migrated
module is only ever exercised on the engine that happened to be configured,
"it passes" means nothing about the other engine — and the failure would only
appear when a user actually switches.

Design decision, stated because it is the whole point: **when MySQL is not
reachable, `mysql_engine` raises instead of skipping.** A skip would let the
suite go green while the MySQL half was never run, which is exactly the false
green this harness exists to prevent. A test that cannot bear that can pass
`optional=True`, and that choice is visible at the call site.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineHandle:
    """One engine to run a migrated operation against."""

    kind: str  # "sqlite" | "mysql"
    available: bool
    #: For sqlite: the path. For mysql: the socket.
    target: str


def _mysql_socket() -> str | None:
    return os.environ.get("ONE_MEMORY_MYSQL_SOCKET") or None


def _mysql_reachable() -> bool:
    """Cheap reachability probe. Never raises."""
    sock = _mysql_socket()
    if not sock or not Path(sock).exists():
        return False
    try:
        import aiomysql  # type: ignore[import-untyped]
    except Exception:
        return False

    async def probe() -> bool:
        conn = await aiomysql.connect(
            unix_socket=sock,
            user=os.environ.get("ONE_MEMORY_MYSQL_USER", "root"),
            password=os.environ.get("ONE_MEMORY_MYSQL_PASSWORD", ""),
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
            return True
        finally:
            conn.close()

    try:
        import asyncio

        return asyncio.run(probe())
    except Exception:
        return False


@contextmanager
def sqlite_engine(path: Path) -> Iterator[EngineHandle]:
    """SQLite is always available; it is the engine in force today."""
    path.parent.mkdir(parents=True, exist_ok=True)
    yield EngineHandle(kind="sqlite", available=True, target=str(path))


@contextmanager
def mysql_engine(*, optional: bool = False) -> Iterator[EngineHandle]:
    """MySQL, raising when absent unless explicitly marked optional.

    `optional=True` is for tests that legitimately have nothing to prove on
    MySQL yet; it must be a visible decision at the call site, not a default.
    """
    sock = _mysql_socket()
    reachable = _mysql_reachable()
    if not reachable:
        if optional:
            yield EngineHandle(kind="mysql", available=False, target=sock or "")
            return
        raise RuntimeError(
            "MySQL is required for this check but is not reachable "
            f"(socket={sock!r}). Set ONE_MEMORY_MYSQL_SOCKET to a running "
            "server, or pass optional=True if this check has nothing to prove there."
        )
    yield EngineHandle(kind="mysql", available=True, target=sock or "")


def run_sqlite(handle: EngineHandle, sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Run one statement on the SQLite handle."""
    assert handle.kind == "sqlite"
    conn = sqlite3.connect(handle.target)
    try:
        rows = conn.execute(sql, params).fetchall()
        # Commit, or a later connection (and the caller's assertions) sees
        # nothing: without this an INSERT followed by a SELECT reads empty,
        # which looks like the SQL silently did nothing.
        conn.commit()
        return rows
    finally:
        conn.close()
