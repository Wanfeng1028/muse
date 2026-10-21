"""Trusted host sessions. A directory is a relevance hint, not an identity."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from one_memory.call_event_store import HostId
from one_memory.database_access import main_database

#: Schema owned by `memory_server.migrations` (migration 6). No local copy,
#: so the migration cannot drift from what this module actually creates.
from one_memory.memory_server.migrations import trusted_sessions_ddl

_SCHEMA = trusted_sessions_ddl("sqlite")


class SessionIdentityError(Exception):
    pass


class AmbiguousWorkspace(SessionIdentityError):
    pass


class ForgedSession(SessionIdentityError):
    pass


@dataclass(frozen=True)
class TrustedSession:
    session_key: str
    installation_id: str
    host_id: HostId
    native_session_id: str
    runtime_instance: str
    workspace: str | None


class SessionRegistry:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path

    def initialize(self) -> None:
        with main_database(self._path).write() as db, db:
            db.execute(_SCHEMA)

    def open(
        self,
        *,
        installation_id: str,
        host_id: HostId,
        native_session_id: str,
        runtime_instance: str,
        workspace: str | None,
    ) -> TrustedSession:
        if not installation_id or not native_session_id or not runtime_instance:
            raise SessionIdentityError("incomplete_session")
        key = _identity_key(installation_id, host_id, native_session_id, runtime_instance)
        with main_database(self._path).write() as db, db:
            row = db.execute(
                "SELECT session_key FROM trusted_sessions WHERE session_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                db.execute(
                    """
                    INSERT INTO trusted_sessions (
                        session_key, installation_id, host_id, native_session_id,
                        runtime_instance, workspace
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, installation_id, host_id, native_session_id, runtime_instance, workspace),
                )
        return self.require(key)

    def require(self, session_key: str) -> TrustedSession:
        with main_database(self._path).read() as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM trusted_sessions WHERE session_key = ?",
                (session_key,),
            ).fetchone()
        if row is None:
            raise ForgedSession(session_key)
        return _session(row)

    def in_workspace(self, workspace: str) -> tuple[TrustedSession, ...]:
        with main_database(self._path).read() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM trusted_sessions WHERE workspace = ? ORDER BY session_key",
                (workspace,),
            ).fetchall()
        return tuple(_session(row) for row in rows)

    def matching_native(
        self, host_id: HostId, native_session_id: str
    ) -> tuple[TrustedSession, ...]:
        with main_database(self._path).read() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT * FROM trusted_sessions
                WHERE host_id = ? AND native_session_id = ?
                ORDER BY session_key
                """,
                (host_id, native_session_id),
            ).fetchall()
        return tuple(_session(row) for row in rows)

    def sole_session(self, workspace: str) -> TrustedSession:
        found = self.in_workspace(workspace)
        if len(found) == 1:
            return found[0]
        raise AmbiguousWorkspace(workspace)


def _identity_key(
    installation_id: str,
    host_id: str,
    native_session_id: str,
    runtime_instance: str,
) -> str:
    material = "\n".join((installation_id, host_id, native_session_id, runtime_instance))
    return hashlib.sha256(material.encode()).hexdigest()


def _session(row: sqlite3.Row) -> TrustedSession:
    return TrustedSession(
        session_key=row["session_key"],
        installation_id=row["installation_id"],
        host_id=row["host_id"],
        native_session_id=row["native_session_id"],
        runtime_instance=row["runtime_instance"],
        workspace=row["workspace"],
    )
