"""Runtime anti-downgrade gate for the SQLite business database.

The migration catalog can refuse a future schema, but only if something reads
the recorded version. Production startup did not, so an older build could open
a database a newer build had written. This module runs before any store opens:

- a database that records a schema newer than this build refuses to start;
- a freshly-created, empty database records this build's schema version;
- a legacy database with business tables but no ledger is left untouched (its
  applied version cannot be invented), so nothing is fabricated.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from one_memory.database_access import main_database
from one_memory.memory_server.migrations import MIGRATIONS, SCHEMA_TABLE

BUILD_SCHEMA_VERSION = max((migration.version for migration in MIGRATIONS), default=0)

#: Tables that mean "this database already holds a user's memory". Their
#: presence without a ledger means a legacy database, not an empty one.
_BUSINESS_TABLES = frozenset({"evidence", "governed_memories"})


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer build; refuse to open it."""

    def __init__(self, *, found: int, known: int) -> None:
        super().__init__(f"database_schema_too_new: {found} > {known}")
        self.code = "database_schema_too_new"
        self.found = found
        self.known = known


def guard_schema_version(database_path: Path) -> int:
    """Fail closed on a future schema; return the effective schema version.

    Returns this build's version for a fresh/empty database, the recorded
    version when a ledger exists, or `0` for a legacy database without a
    ledger (nothing is fabricated and nothing is rewritten).
    """
    if not database_path.exists():
        # A brand-new library: create the ledger now so a later downgrade is
        # detectable even before any store has run.
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with main_database(database_path).write() as connection, connection:
            _record_build_version(connection)
        return BUILD_SCHEMA_VERSION

    with main_database(database_path).read() as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if SCHEMA_TABLE in tables:
            row = connection.execute(f"SELECT MAX(version) FROM {SCHEMA_TABLE}").fetchone()
            found = int(row[0]) if row and row[0] is not None else 0
            if found > BUILD_SCHEMA_VERSION:
                raise SchemaTooNewError(found=found, known=BUILD_SCHEMA_VERSION)
            return found
        if tables >= _BUSINESS_TABLES:
            # Legacy database: leave it exactly as found.
            return 0

    # Fresh database: record this build's schema so a later downgrade can be
    # detected. Written through the single writer, after the read above.
    with main_database(database_path).write() as connection, connection:
        _record_build_version(connection)
    return BUILD_SCHEMA_VERSION


def _record_build_version(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    connection.execute(
        f"INSERT OR REPLACE INTO {SCHEMA_TABLE} (version, name, applied_at) VALUES (?,?,?)",
        (
            BUILD_SCHEMA_VERSION,
            "runtime_schema_gate",
            datetime.now(UTC).isoformat(),
        ),
    )
