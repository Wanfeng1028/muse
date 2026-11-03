"""Legacy durable change events retained while automatic production is paused."""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from one_memory.database_access import main_database

#: The schema is owned by `memory_server.migrations` (migration 4). A1-03
#: forbids a business module declaring its own tables, and a second copy of the
#: DDL would drift from the migration that claims to define it.
#:
#: This store still runs on SQLite today, so it asks the migration for the
#: SQLite rendering of the same definition. There is no local copy.
from one_memory.memory_server.migrations import change_outbox_ddl

_SCHEMA = change_outbox_ddl("sqlite")


def evidence_event_id(evidence_id: str, revision: int) -> str:
    return hashlib.sha256(f"{evidence_id}:{revision}:import".encode()).hexdigest()


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    cause: str
    evidence_id: str | None
    evidence_revision: int | None
    permission_epoch: int
    notified: bool


class ChangeOutbox:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path

    def initialize(self) -> None:
        with main_database(self._path).write() as db, db:
            db.execute(_SCHEMA)

    def record(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        cause: str,
        evidence_id: str | None,
        evidence_revision: int | None,
        permission_epoch: int,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("change_outbox_requires_caller_transaction")
        connection.execute(
            """
            INSERT OR IGNORE INTO change_outbox (
                event_id, cause, evidence_id, evidence_revision,
                permission_epoch, created_at, notified_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                event_id,
                cause,
                evidence_id,
                evidence_revision,
                permission_epoch,
                datetime.now(UTC).isoformat(),
            ),
        )

    def pending(self) -> tuple[OutboxEvent, ...]:
        with main_database(self._path).read() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT event_id, cause, evidence_id, evidence_revision,
                       permission_epoch, notified_at
                FROM change_outbox
                WHERE notified_at IS NULL
                ORDER BY created_at, event_id
                """
            ).fetchall()
        return tuple(
            OutboxEvent(
                event_id=row["event_id"],
                cause=row["cause"],
                evidence_id=row["evidence_id"],
                evidence_revision=row["evidence_revision"],
                permission_epoch=row["permission_epoch"],
                notified=False,
            )
            for row in rows
        )
