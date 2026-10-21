"""Persisted extraction-window choice.

Kept apart from onboarding: the window can change long after the first run,
and it has to survive a restart so a widened window does not silently snap
back to ninety days.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from one_memory.database import (
    take_the_write_lock_first,
)
from one_memory.database_access import main_database
from one_memory.memory_queue import ExtractionWindowPreset

#: Schema owned by `memory_server.migrations` (migration 17). No local copy.
from one_memory.memory_server.migrations import extraction_settings_ddl
from one_memory.memory_server.store_binding import store_for


def _is_mysql(store: Any) -> bool:
    """Whether the bound store is the MySQL one.

    Asked of the store rather than guessed from a global, because two engines
    can exist in one process during the migration and a global would make the
    answer depend on whichever was resolved last.
    """
    from one_memory.memory_server.sync_facade import SyncStoreFacade

    return isinstance(store, SyncStoreFacade)


def _value(row: object, index: int) -> object:
    """Read a column from either a sqlite3.Row or a plain tuple.

    `sqlite3.Row` supports indexing by name and by position; a MySQL tuple only
    by position. Reading by position works on both, which is why the SELECT
    names its column explicitly.
    """
    try:
        return row[index]  # type: ignore[index]
    except (TypeError, KeyError):
        return row[index]  # type: ignore[index]


SCHEMA = extraction_settings_ddl("sqlite")

#: The upsert, per engine.
#:
#: SQLite has `ON CONFLICT ... DO UPDATE` and MySQL does not; MySQL spells the
#: same thing `ON DUPLICATE KEY UPDATE`. They are not interchangeable, and
#: getting this wrong does not raise — it either fails to update the existing
#: row or refuses to insert, so the setting silently keeps its old value.
UPSERT_SQLITE = """
    INSERT INTO extraction_settings (singleton, window_preset)
    VALUES (1, ?)
    ON CONFLICT(singleton) DO UPDATE SET window_preset = excluded.window_preset
"""
UPSERT_MYSQL = """
    INSERT INTO extraction_settings (singleton, window_preset)
    VALUES (1, %s)
    ON DUPLICATE KEY UPDATE window_preset = VALUES(window_preset)
"""


class ExtractionSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Left at THREE_MONTHS deliberately. Widening this to ALL makes the
    # deferral mechanism a no-op under the default config, which is a product
    # call about first-run cost, not part of the timeout fix.
    window_preset: ExtractionWindowPreset = ExtractionWindowPreset.THREE_MONTHS


class _SyncCursor:
    """A synchronous `.execute()` over an async MySQL connection.

    Exists so the calling code does not have to know which engine it is on:
    both engines expose `execute(sql, params)` returning something with
    `fetchone()`/`fetchall()`. Without it every call site would need two
    branches, which is the duplication this migration is trying to remove.

    Statements run on the facade's loop via `run_coroutine_threadsafe`, so the
    caller stays synchronous while the MySQL I/O happens off the main loop.
    """

    def __init__(self, connection: Any, loop: asyncio.AbstractEventLoop) -> None:
        self._connection = connection
        self._loop = loop

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _SyncResult:
        async def _run() -> Any:
            async with self._connection.cursor() as cursor:
                await cursor.execute(sql, params)
                try:
                    return await cursor.fetchall()
                except Exception:
                    return None
            return None

        rows = asyncio.run_coroutine_threadsafe(_run(), self._loop).result(timeout=30)
        return _SyncResult(rows)


class _SyncResult:
    """The small surface the call sites use: `fetchone` / `fetchall`."""

    def __init__(self, rows: Any) -> None:
        self._rows = rows or []

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> Any:
        return self._rows


class ExtractionSettingsStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._store: Any = store_for(database_path)
        self._initialize()

    def _initialize(self) -> None:
        """Create the table through the store, not a raw `executescript`.

        `executescript` is a sqlite3-only convenience; the MySQL path has no
        equivalent, so the schema goes through the ordinary checkout instead.
        """
        with self._connect(initialize=True) as connection:
            connection.execute(SCHEMA)

    def _upsert_sql(self) -> str:
        return UPSERT_MYSQL if _is_mysql(self._store) else UPSERT_SQLITE

    def get(self) -> ExtractionSettings:
        with self._connect(initialize=True) as connection:
            row = connection.execute(
                "SELECT window_preset FROM extraction_settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return ExtractionSettings()
        raw = _value(row, 0)
        return ExtractionSettings(window_preset=ExtractionWindowPreset(str(raw)))

    def set_window_preset(self, preset: ExtractionWindowPreset) -> ExtractionSettings:
        with self._connect(writing=True) as connection:
            connection.execute(self._upsert_sql(), (preset.value,))
        return self.get()

    @contextmanager
    def _connect(
        self,
        *,
        initialize: bool = False,
        writing: bool = False,
    ) -> Iterator[Any]:
        """A checkout that yields something with `.execute()` on both engines.

        On SQLite this is the existing behaviour, including the write lock and
        `sqlite3.Row`. On MySQL the facade hands back a connection whose
        `execute` is async, so statements are routed to the facade's loop and
        the caller still sees a synchronous `.execute(...)`.
        """
        if _is_mysql(self._store):
            checkout = self._store.write() if (initialize or writing) else self._store.read()
            with checkout as connection:
                yield _SyncCursor(connection, self._store._loop)
            return

        database = main_database(self.database_path)
        checkout = (
            database.write(autocommit=True, row_factory=sqlite3.Row)
            if initialize or writing
            else database.read(row_factory=sqlite3.Row)
        )
        with checkout as connection, connection:
            if writing:
                take_the_write_lock_first(connection)
            else:
                connection.autocommit = False
            yield connection
