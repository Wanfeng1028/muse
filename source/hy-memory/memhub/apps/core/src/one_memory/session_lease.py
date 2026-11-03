"""Online means an unexpired lease, not a session file that is still on disk."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from one_memory.database_access import main_database

#: Schema owned by `memory_server.migrations` (migration 5). No local copy,
#: so the migration cannot drift from what this module actually creates.
from one_memory.memory_server.migrations import session_leases_ddl
from one_memory.memory_server.sql_compat import (
    execute,
    execute_script,
    is_mysql,
    row_to_dict,
)
from one_memory.memory_server.store_binding import store_for
from one_memory.session_registry import SessionRegistry

#: Both renderings, chosen at use time (same reason as every migrated module:
#: the sqlite rendering carries SQLite types and index forms MySQL rejects).
SCHEMA_BY_ENGINE = {False: session_leases_ddl("sqlite"), True: session_leases_ddl("mysql")}


def schema_for(mysql: bool) -> str:
    return SCHEMA_BY_ENGINE[mysql]


#: The heartbeat upsert, per engine.
#:
#: `ON CONFLICT ... DO UPDATE` (SQLite) vs `ON DUPLICATE KEY UPDATE` (MySQL).
#: Wrong either way and a session's lease silently keeps its old expiry, which
#: reads as "session went offline" rather than as a database error.
BEAT_SQLITE = """
    INSERT INTO session_leases (session_key, pid, generation, expires_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(session_key) DO UPDATE SET
        pid = excluded.pid,
        generation = excluded.generation,
        expires_at = excluded.expires_at
"""
BEAT_MYSQL = """
    INSERT INTO session_leases (session_key, pid, generation, expires_at)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        pid = VALUES(pid),
        generation = VALUES(generation),
        expires_at = VALUES(expires_at)
"""
SELECT_SQLITE = "SELECT generation, expires_at FROM session_leases WHERE session_key = ?"
SELECT_MYSQL = "SELECT generation, expires_at FROM session_leases WHERE session_key = %s"


class SessionLease:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        self._store: Any = store_for(database_path)
        self._registry = SessionRegistry(database_path)

    def initialize(self) -> None:
        mysql = is_mysql(self._store)
        with self._connect(writing=True) as db:
            execute_script(db, mysql, schema_for(mysql))

    def beat(
        self,
        session_key: str,
        *,
        pid: int,
        generation: int,
        now: datetime,
        ttl_seconds: int,
    ) -> None:
        self._registry.require(session_key)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat()
        mysql = is_mysql(self._store)
        with self._connect(writing=True) as db:
            execute(
                db,
                mysql,
                BEAT_MYSQL if mysql else BEAT_SQLITE,
                (session_key, pid, generation, expires),
            )

    def online(
        self,
        session_key: str,
        *,
        now: datetime,
        generation: int,
        source_file: Path | None = None,
    ) -> bool:
        del source_file
        self._registry.require(session_key)
        mysql = is_mysql(self._store)
        with self._connect() as db:
            row = execute(
                db, mysql, SELECT_MYSQL if mysql else SELECT_SQLITE, (session_key,)
            ).fetchone()
        if row is None:
            return False
        # Named access only works on `sqlite3.Row`; MySQL gives a tuple, so the
        # row is normalised to a mapping on both engines first.
        values = row_to_dict(row, ("generation", "expires_at"), mysql)
        if int(values["generation"]) != generation:
            return False
        return now < _as_datetime(values["expires_at"], now)

    @contextmanager
    def _connect(self, *, writing: bool = False) -> Iterator[Any]:
        """A checkout on whichever engine is in force."""
        if is_mysql(self._store):
            checkout = self._store.write() if writing else self._store.read()
            with checkout as connection:
                yield connection
            return
        database = main_database(self._path)
        checkout = database.write() if writing else database.read(row_factory=sqlite3.Row)
        with checkout as connection, connection:
            yield connection


def _as_datetime(value: object, reference: datetime) -> datetime:
    """Parse the stored expiry, matching the caller's awareness.

    SQLite returns the stored ISO string so it parses aware. MySQL `DATETIME`
    returns a naive `datetime`, and comparing that with an aware `now` raises
    `TypeError` — a crash on a perfectly ordinary read. The stored value is the
    same instant, so the zone is taken from the caller's clock rather than
    assumed, which keeps the comparison meaningful either way.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None and reference.tzinfo is not None:
            return value.replace(tzinfo=reference.tzinfo)
        return value
    return datetime.fromisoformat(str(value))
