"""A4-10: the MySQL implementation of the scanner's `CursorStore`.

The contract lives in `tests/test_scanner_store_contract.py` and is written
against the interface, so this class must pass that file unchanged — that is
the point of having written it that way.

Two properties carry the whole design:

- **One query per page, never one per file.** `get_many` issues a single
  `WHERE file_key IN (...)` for the whole page. A per-file lookup is the N+1
  the metadata gate forbids, and it is what a slow "metadata-first" scanner
  quietly regresses into. The batch counter exists so a test can see it.
- **Upsert, not insert.** `put_many` uses `ON DUPLICATE KEY UPDATE`, because a
  scan re-writes cursors for files it has already seen; a plain INSERT would
  fail on the second cycle, and "DELETE then INSERT" would lose the row if the
  process died between the two.

Writes go through `Database.transaction()`, not a bare connection: the commit
is what makes a cursor durable, and a cursor that was never committed means the
next scan re-reads a file it had already ingested. Reads use a plain
connection because there is nothing to commit.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

from one_memory.memory_server.scanner.classifier import StoredFileCursor
from one_memory.memory_server.scanner.service import CursorStore

_log = logging.getLogger(__name__)

#: Columns in `source_file_cursors` order, excluding `updated_at` (server-set).
_COLUMNS = (
    "file_key",
    "file_identity",
    "observed_size",
    "observed_modified_ns",
    "checkpoint",
    "read_to_end",
)


class AsyncCursorStore(ABC):
    """The async shape of the cursor store.

    Deliberately NOT a subclass of `CursorStore`: MySQL access is inherently
    awaitable, and pretending otherwise would make `get_many` return a
    coroutine where callers expect a mapping — a latent bug that mypy catches
    and that would only surface at runtime as "coroutine was never awaited",
    i.e. silently empty cursors and therefore re-reading every file.

    `SyncCursorStoreAdapter` below is the seam back to the synchronous port.
    """

    @abstractmethod
    async def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        """One query for the whole page; only found keys, never None."""

    @abstractmethod
    async def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        """Upsert the page's cursors, committed as one unit."""


class MysqlCursorStore(AsyncCursorStore):
    """Cursor storage on MySQL, one query per page."""

    def __init__(self, database: Any) -> None:
        self._db = database
        #: Number of batch lookups issued. Counted here as well as by the
        #: scanner so a test can see the store did not cheat.
        self.batch_lookups = 0

    @asynccontextmanager
    async def _read_cursor(self) -> Any:
        """A cursor on a pooled connection, with nothing to commit."""
        # `Database.connection` is an @asynccontextmanager *property*, so the
        # attribute is a decorator until it is called; `self._db.connection()`
        # is the manager.
        async with self._db.connection() as connection, connection.cursor() as cursor:
            yield cursor

    def _row_to_cursor(self, row: dict[str, Any]) -> StoredFileCursor:
        return StoredFileCursor(
            file_key=row["file_key"],
            file_identity=row["file_identity"],
            observed_size=int(row["observed_size"]),
            observed_modified_ns=int(row["observed_modified_ns"]),
            checkpoint=int(row["checkpoint"]),
            read_to_end=bool(row["read_to_end"]),
            anchor=None,
        )

    async def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        """Fetch every cursor for this page in ONE query.

        Returning only the keys that exist — with no None placeholders — is
        part of the contract, because a None would let a call site treat
        "no cursor yet" as "cursor at offset 0" and re-read the whole file.
        """
        if not keys:
            return {}
        self.batch_lookups += 1

        placeholders = ", ".join(["%s"] * len(keys))
        sql = (
            "SELECT file_key, file_identity, observed_size, observed_modified_ns, "
            f"checkpoint, read_to_end FROM source_file_cursors WHERE file_key IN ({placeholders})"
        )
        async with self._read_cursor() as cursor:
            await cursor.execute(sql, tuple(keys))
            rows = await cursor.fetchall()

        # aiomysql without a dict cursor returns tuples; normalise once here so
        # callers never have to care which engine or cursor class is in play.
        out: dict[str, StoredFileCursor] = {}
        for row in rows:
            values = row if isinstance(row, dict) else dict(zip(_COLUMNS, row, strict=False))
            out[values["file_key"]] = self._row_to_cursor(values)
        return out

    async def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        """Upsert the page's cursors in one statement."""
        if not cursors:
            return
        rows = [
            (
                cursor.file_key,
                cursor.file_identity,
                cursor.observed_size,
                cursor.observed_modified_ns,
                cursor.checkpoint,
                1 if cursor.read_to_end else 0,
            )
            for cursor in cursors.values()
        ]
        values = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(rows))
        flat: list[Any] = [value for row in rows for value in row]

        sql = (
            "INSERT INTO source_file_cursors "
            "(file_key, file_identity, observed_size, observed_modified_ns, "
            "checkpoint, read_to_end) VALUES "
            f"{values} ON DUPLICATE KEY UPDATE "
            "file_identity = VALUES(file_identity), "
            "observed_size = VALUES(observed_size), "
            "observed_modified_ns = VALUES(observed_modified_ns), "
            "checkpoint = VALUES(checkpoint), "
            "read_to_end = VALUES(read_to_end)"
        )
        # Committed as one unit: a page of cursors that half-landed would make
        # the next scan re-read files that were already ingested.
        async with self._db.transaction() as cursor:
            await cursor.execute(sql, tuple(flat))


def cursor_store_for(database: Any) -> MysqlCursorStore:
    """Build the MySQL cursor store over a `memory_server.db.Database`."""
    return MysqlCursorStore(database)


class SyncCursorStoreAdapter(CursorStore):
    """Drive the async MySQL store from synchronous code.

    The `CursorStore` interface is synchronous because the scanner's
    classification is a pure function and its tests must not need an event
    loop; MySQL access is inherently async. This adapter is the seam, so the
    async store can still be run through
    `tests/test_scanner_store_contract.py` unchanged.

    It owns its loop and is therefore not thread-safe by construction, which is
    correct: one scanner owns one root, and `lease.py` enforces that.
    """

    def __init__(self, inner: MysqlCursorStore) -> None:
        self._inner = inner
        self._loop = asyncio.new_event_loop()

    @property
    def batch_lookups(self) -> int:
        return self._inner.batch_lookups

    def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        return self._loop.run_until_complete(self._inner.get_many(keys))

    def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        self._loop.run_until_complete(self._inner.put_many(cursors))

    def close(self) -> None:
        self._loop.close()
