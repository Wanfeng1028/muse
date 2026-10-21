"""A1-03: apply migrations and record what was applied.

The runner owns the transaction per migration: apply the SQL, then record the
version, together. Recording separately would let a schema change land without
its ledger entry, and then every later start would believe the database is at a
version it never actually reached.

Storage is injected the same way as the scanner's cursor store, so this can be
exercised without a live server. The store also owns the SQL dialect
(`MigrationStore.dialect`): under D56 that is SQLite, and the shipped
migrations render for it rather than hardcoding MySQL. Before that, the runner
could not execute against the engine actually in force at all.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from one_memory.database_access import main_database
from one_memory.memory_server.migrations import (
    SCHEMA_TABLE,
    Migration,
    current_version,
    plan_upgrade,
    validate_migrations,
)

_log = logging.getLogger(__name__)


class MigrationStore(Protocol):
    """The small surface the runner needs. Implemented over MySQL in A1-04."""

    #: Which SQL rendering the migrations must emit: "mysql" or "sqlite".
    dialect: str

    async def applied_versions(self) -> set[int]: ...
    async def record(self, migration: Migration) -> None: ...
    async def execute(self, sql: str) -> None: ...
    async def columns(self, table: str) -> set[str]: ...
    async def schema_objects(self, table: str) -> dict[str, str]: ...
    async def existing_tables(self, tables: Sequence[str]) -> set[str]: ...


class InMemoryMigrationStore:
    """Dict-backed store: records the SQL it was asked to run, for tests."""

    #: Defaults to MySQL because that is what the shipped migration bodies were
    #: written for; a caller that wants the SQLite rendering sets this.
    dialect = "mysql"

    def __init__(self) -> None:
        self.applied: set[int] = set()
        self.executed: list[str] = []

    async def applied_versions(self) -> set[int]:
        return set(self.applied)

    async def record(self, migration: Migration) -> None:
        self.applied.add(migration.version)

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)

    async def columns(self, table: str) -> set[str]:
        """No real schema to inspect; callers that need it use SQLite."""
        del table
        return set()

    async def schema_objects(self, table: str) -> dict[str, str]:
        """No real schema to inspect; callers that need it use SQLite."""
        del table
        return {}

    async def existing_tables(self, tables: Sequence[str]) -> set[str]:
        """No real schema to inspect; synthetic stores opt out of the audit."""
        return set(tables)


@dataclass(frozen=True)
class MigrationResult:
    before: int
    after: int
    applied: tuple[int, ...]


class DatabaseSchemaTooNewError(RuntimeError):
    """The database was written by a newer build. Refuse to touch it.

    A downgrade cannot know what a future migration changed, so "apply the
    migrations I know about" would leave a shape neither build understands, and
    any later write could corrupt it. Failing closed keeps the newer database
    intact and points at the real cause (newer build, older code).
    """

    def __init__(self, *, found: int, known: int) -> None:
        super().__init__(
            f"database schema version {found} is newer than this build's {known}; "
            "run the matching (newer) app or restore a backup"
        )
        self.found = found
        self.known = known


async def migrate(
    store: MigrationStore,
    migrations: Sequence[Migration],
) -> MigrationResult:
    """Bring the database up to date. Safe to call repeatedly."""
    validate_migrations(migrations)
    applied = await store.applied_versions()
    before = current_version(applied)

    # Refuse a rollback past a newer build's schema: we cannot know what its
    # migrations did, and proceeding would leave a shape neither build expects.
    known = max((item.version for item in migrations), default=0)
    if before > known:
        raise DatabaseSchemaTooNewError(found=before, known=known)

    await _verify_recorded_tables(store, migrations, applied)

    todo = plan_upgrade(migrations, before)
    done: list[int] = []
    for migration in todo:
        _log.info("applying migration %s: %s", migration.version, migration.name)
        await migration.apply(store)
        await _verify_declared_tables(store, migration)
        # Recorded only after the SQL succeeded, so a failure is retried rather
        # than skipped on the next start.
        await store.record(migration)
        done.append(migration.version)

    return MigrationResult(
        before=before,
        after=current_version(applied | set(done)),
        applied=tuple(done),
    )


async def _verify_recorded_tables(
    store: MigrationStore,
    migrations: Sequence[Migration],
    applied: set[int],
) -> None:
    """Fail closed when the ledger claims a migration whose tables are gone.

    `CREATE TABLE IF NOT EXISTS` makes an interrupted or externally damaged
    database look healthy on the next run: the version is already recorded, so
    the migration is skipped, but the table it owns may be missing. SQLite can
    also produce this state if a user removes a table manually or restores a
    partially overwritten file. The runner must not report an up-to-date
    database while the ledger and the schema disagree.
    """
    expected: set[str] = set()
    owners: dict[str, Migration] = {}
    for migration in migrations:
        if migration.version not in applied:
            continue
        for table in migration.tables:
            expected.add(table)
            owners.setdefault(table, migration)
    if not expected:
        return

    present = await store.existing_tables(tuple(sorted(expected)))
    # A table can be absent because an earlier migration shipped without it and
    # a later forward migration explicitly recreates it. The historical v28
    # preview omission is the concrete case: v28 is already recorded in real
    # databases, so v39 owns the corrective CREATE TABLE. Only that explicit,
    # not-yet-applied ownership may bridge the audit gap; otherwise this stays
    # fail-closed.
    repair_versions = {
        migration.version for migration in migrations if migration.version not in applied
    }
    repairable = {
        table
        for migration in migrations
        if migration.version in repair_versions
        for table in migration.tables
    }
    missing = expected - present - repairable
    if not missing:
        return
    details = ", ".join(
        f"{table} (migration {owners[table].version} {owners[table].name})"
        for table in sorted(missing)
    )
    raise MigrationSchemaMismatchError(details)


async def _verify_declared_tables(store: MigrationStore, migration: Migration) -> None:
    """Ensure a just-applied migration actually created what it declares.

    The ledger must not record a version whose declared tables are absent.
    Checking here catches a migration body that accidentally skips a table
    before the bad state becomes the next process's startup failure.
    """
    declared = getattr(migration, "tables", ())
    if not declared:
        return
    present = await store.existing_tables(tuple(sorted(declared)))
    missing = set(declared) - present
    if missing:
        details = ", ".join(
            f"{table} (migration {migration.version} {migration.name})" for table in sorted(missing)
        )
        raise MigrationSchemaMismatchError(details)


class MigrationSchemaMismatchError(RuntimeError):
    """The durable ledger records a schema that is not actually present."""

    def __init__(self, missing: str) -> None:
        super().__init__(f"recorded migration is missing its table: {missing}")
        self.missing = missing


def ledger_sql() -> str:
    """SQL to create the ledger table, for the first-ever run."""
    return (
        f"CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} ("
        "version INT PRIMARY KEY, name VARCHAR(255) NOT NULL, "
        "applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)) "
        "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    )


def ledger_sqlite_sql() -> str:
    """The D56 ledger: one durable record per applied migration."""
    return (
        f"CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "applied_at TEXT NOT NULL)"
    )


class SqliteMigrationStore:
    """A durable migration ledger on the SQLite business database.

    The runner already refuses to record a version whose SQL failed; what was
    missing is a ledger that survives the process. Without it, an interrupted
    upgrade cannot be resumed and a restart cannot prove which versions really
    landed.

    Each statement runs in its own transaction, so a crash between DDL and
    ledger write leaves the version unrecorded and therefore retried — the
    same guarantee the runner's in-memory store gives, persisted.
    """

    #: This store is the SQLite one under D56, so migrations emit the SQLite
    #: rendering. The MySQL rendering is not reachable (see `store_binding`).
    dialect = "sqlite"

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = threading.Lock()
        with self._write() as connection, connection:
            connection.execute(ledger_sqlite_sql())

    def _write(self) -> AbstractContextManager[sqlite3.Connection]:
        """The unified access layer's write connection, never a direct open.

        Business modules must not call `sqlite3.connect` themselves; the
        access layer owns the single writer, WAL and wait accounting.
        """
        return main_database(self.database_path).write()

    def _read(self) -> AbstractContextManager[sqlite3.Connection]:
        return main_database(self.database_path).read()

    async def applied_versions(self) -> set[int]:
        with self._lock, self._read() as connection:
            rows = connection.execute(f"SELECT version FROM {SCHEMA_TABLE}").fetchall()
        return {int(row[0]) for row in rows}

    async def record(self, migration: Migration) -> None:
        with self._lock, self._write() as connection, connection:
            # Update then insert. A single upsert statement would be another
            # SQLite-only dialect construct, and re-recording after an
            # interrupted upgrade should not add one.
            updated = connection.execute(
                f"UPDATE {SCHEMA_TABLE} SET name=?, applied_at=? WHERE version=?",
                (migration.name, datetime.now(UTC).isoformat(), migration.version),
            )
            if updated.rowcount == 0:
                connection.execute(
                    f"INSERT INTO {SCHEMA_TABLE} (version, name, applied_at) VALUES (?,?,?)",
                    (migration.version, migration.name, datetime.now(UTC).isoformat()),
                )

    async def execute(self, sql: str) -> None:
        with self._lock, self._write() as connection, connection:
            connection.execute(sql)

    async def columns(self, table: str) -> set[str]:
        """Column names for a table, read from the real schema."""
        with self._lock, self._read() as connection:
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}

    async def schema_objects(self, table: str) -> dict[str, str]:
        """Exact `sqlite_master.sql` text for a table and its indexes."""
        with self._lock, self._read() as connection:
            rows = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE tbl_name=? AND type IN ('table','index') AND sql IS NOT NULL",
                (table,),
            ).fetchall()
        return {str(name): str(sql) for name, sql in rows}

    async def existing_tables(self, tables: Sequence[str]) -> set[str]:
        """Which named tables actually exist in the SQLite schema."""
        requested = set(tables)
        if not requested:
            return set()
        with self._lock, self._read() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                f"({','.join('?' for _ in requested)})",
                tuple(requested),
            ).fetchall()
        return {str(row[0]) for row in rows}
