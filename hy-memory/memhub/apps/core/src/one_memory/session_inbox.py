"""Per-session incremental read. A pull or an ack is not adoption."""

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

#: Schema owned by `memory_server.migrations` (migration 11). No local copy.
from one_memory.change_outbox import evidence_event_id
from one_memory.database_access import main_database
from one_memory.derived_echo import echoed_event_ids, is_pure_echo
from one_memory.memory_server.migrations import session_inbox_ddl
from one_memory.session_registry import SessionRegistry

_SCHEMA = session_inbox_ddl("sqlite")


class CursorRejected(Exception):
    pass


@dataclass(frozen=True)
class InboxEvent:
    event_id: str
    evidence_id: str | None
    evidence_revision: int | None
    source_id: str | None


@dataclass(frozen=True)
class InboxPage:
    batch_id: str
    cursor: str
    state: str
    adoption: str
    events: tuple[InboxEvent, ...]


@dataclass(frozen=True)
class InboxPosition:
    """Where a cursor would stand once the events handed over are confirmed."""

    event_id: str | None
    permission_epoch: int
    handed_event_ids: frozenset[str] = frozenset()
    receipt_id: str | None = None


@dataclass(frozen=True)
class InboxPeek:
    events: tuple[InboxEvent, ...]
    position: InboxPosition


@dataclass(frozen=True)
class InboxAck:
    batch_id: str
    state: str
    adoption: str


@dataclass(frozen=True)
class InboxSignal:
    signal_id: str


class SessionInbox:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        self._registry = SessionRegistry(database_path)

    def initialize(self) -> None:
        with main_database(self._path).write() as db, db:
            db.executescript(_SCHEMA)

    def subscribe(
        self,
        session_key: str,
        sources: tuple[str, ...],
        permission_epoch: int,
    ) -> None:
        self._registry.require(session_key)
        with main_database(self._path).write() as db, db:
            db.execute(
                """
                INSERT INTO session_subscriptions (
                    session_key, granted_sources, permission_epoch
                ) VALUES (?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    granted_sources = excluded.granted_sources,
                    permission_epoch = excluded.permission_epoch
                """,
                (session_key, json.dumps(list(sources)), permission_epoch),
            )

    def pull(self, session_key: str, cursor: str | None, limit: int) -> InboxPage:
        self._registry.require(session_key)
        with self._snapshot() as db:
            start_after, epoch = self._cursor_position(session_key, cursor, db)
            granted = self._granted(session_key, db)
            events = self._without_host_echo(self._events(db), db)
            current = self._epoch(session_key, db)
        selected, found = self._scan(granted, start_after, limit, events)
        state = "delivered"
        # A cursor whose event is gone, or whose permission epoch no longer
        # matches, must not look like "nothing new". Rebuild from the start.
        if cursor is not None and (not found or epoch != current):
            selected, _found = self._scan(granted, None, limit, events)
            state = "resync-required"
            epoch = current
        if selected:
            scanned_id = selected[-1].event_id
        elif state == "resync-required":
            scanned_id = None
        else:
            scanned_id = start_after
        return self._store_page(session_key, scanned_id, epoch, state, selected)

    def peek(self, session_key: str, limit: int) -> InboxPeek:
        """What the next pull from the latest cursor would return, without moving it."""

        self._registry.require(session_key)
        # Grants, epoch and events are read in one snapshot: a revoke landing
        # between them would pair the old grants with the new epoch.
        with self._snapshot() as db:
            cursor = self._latest_cursor(session_key, db)
            start_after, epoch = self._cursor_position(session_key, cursor, db)
            granted = self._granted(session_key, db)
            events = self._without_host_echo(self._events(db), db)
            current = self._epoch(session_key, db)
        selected, found = self._scan(granted, start_after, limit, events)
        if cursor is not None and (not found or epoch != current):
            selected, _found = self._scan(granted, None, limit, events)
            start_after = None
        end = selected[-1].event_id if selected else start_after
        receipt_id = None
        if selected:
            receipt_id = secrets.token_hex(16)
            receipt = self._new_receipt(
                session_key,
                position_event_id=str(end),
                permission_epoch=current,
                handed_event_ids=tuple(event.event_id for event in selected),
            )
            with main_database(self._path).write() as db, db:
                db.execute(
                    """
                    INSERT INTO session_snapshots (
                        snapshot_token, session_key, frozen_ids
                    )
                    VALUES (?, ?, ?)
                    """,
                    (receipt_id, session_key, receipt),
                )
        return InboxPeek(
            tuple(selected),
            InboxPosition(
                end,
                current,
                frozenset(event.event_id for event in selected),
                receipt_id,
            ),
        )

    @staticmethod
    def _new_receipt(
        session_key: str,
        *,
        position_event_id: str,
        permission_epoch: int,
        handed_event_ids: tuple[str, ...],
    ) -> str:
        return json.dumps(
            {
                "kind": "peek",
                "session_key": session_key,
                "event_id": position_event_id,
                "permission_epoch": permission_epoch,
                "handed_event_ids": list(handed_event_ids),
            },
            separators=(",", ":"),
        )

    def advance_to(self, session_key: str, position: InboxPosition) -> bool | None:
        """Move the latest cursor forward to a peeked position, never back.

        Two rounds may peek overlapping pages and confirm in either order. The
        cursor only ever moves to the furthest position actually handed over.
        """

        self._registry.require(session_key)
        if position.event_id is None:
            return False
        if position.receipt_id is None:
            raise CursorRejected("missing_peek_receipt")
        # IMMEDIATE takes the file's write lock at once: the confirming process
        # is not the one that peeked, so the in-process writer queue is not enough.
        with main_database(self._path).write() as db, db:
            db.execute("BEGIN IMMEDIATE")
            events = self._without_host_echo(self._events(db), db)
            order = [event.event_id for event in events]
            by_id = {event.event_id: event for event in events}
            receipt = self._peek_receipt(session_key, position, db)
            row = db.execute(
                "SELECT permission_epoch FROM session_subscriptions WHERE session_key = ?",
                (session_key,),
            ).fetchone()
            epoch = int(row[0]) if row is not None else 0
            handed = receipt
            if any(event_id not in order for event_id in handed):
                raise CursorRejected("handed_event_missing")
            granted = self._granted(session_key, db)
            target = by_id.get(position.event_id)
            if target is None or target.source_id not in granted:
                raise CursorRejected("target_not_selectable")
            if any(by_id[event_id].source_id not in granted for event_id in handed):
                raise CursorRejected("handed_event_not_selectable")
            if position.permission_epoch != epoch:
                return None
            latest_token = self._latest_cursor(session_key, db)
            cursor_position = -1
            if latest_token is not None:
                start_after, _cursor_epoch = self._cursor_position(session_key, latest_token, db)
                if start_after in order:
                    cursor_position = order.index(str(start_after))
            target_position = order.index(position.event_id)
            if cursor_position >= target_position:
                return None
            required = [
                event.event_id
                for event in events[cursor_position + 1 : target_position + 1]
                if event.source_id in granted
            ]
            handed_after_cursor = [
                event_id for event_id in handed if order.index(event_id) > cursor_position
            ]
            if handed_after_cursor != required:
                raise CursorRejected("incomplete_handed_range")
            latest = db.execute(
                """
                SELECT scanned_event_id, permission_epoch FROM session_inbox_cursors
                WHERE session_key = ? ORDER BY rowid DESC LIMIT 1
                """,
                (session_key,),
            ).fetchone()
            if (
                latest is not None
                and int(latest[1]) == epoch
                and latest[0] in order
                and order.index(latest[0]) > order.index(position.event_id)
            ):
                return None
            db.execute(
                """
                INSERT INTO session_inbox_cursors (
                    cursor_token, session_key, scanned_event_id, permission_epoch
                ) VALUES (?, ?, ?, ?)
                """,
                (secrets.token_hex(32), session_key, position.event_id, epoch),
            )
        return True

    @staticmethod
    def _peek_receipt(
        session_key: str, position: InboxPosition, db: sqlite3.Connection
    ) -> tuple[str, ...]:
        row = db.execute(
            """
            SELECT frozen_ids FROM session_snapshots
            WHERE snapshot_token = ? AND session_key = ?
            """,
            (position.receipt_id, session_key),
        ).fetchone()
        if row is None:
            raise CursorRejected("invalid_peek_receipt")
        try:
            receipt = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise CursorRejected("invalid_peek_receipt") from error
        if not isinstance(receipt, dict) or receipt.get("kind") != "peek":
            raise CursorRejected("invalid_peek_receipt")
        if receipt.get("session_key") != session_key:
            raise CursorRejected("peek_receipt_session_mismatch")
        if receipt.get("event_id") != position.event_id:
            raise CursorRejected("peek_receipt_target_mismatch")
        if receipt.get("permission_epoch") != position.permission_epoch:
            raise CursorRejected("peek_receipt_epoch_mismatch")
        handed = receipt.get("handed_event_ids")
        if not isinstance(handed, list) or any(not isinstance(item, str) for item in handed):
            raise CursorRejected("invalid_peek_receipt")
        loaded = tuple(handed)
        if frozenset(loaded) != position.handed_event_ids:
            raise CursorRejected("peek_receipt_handed_mismatch")
        return loaded

    def latest_cursor(self, session_key: str) -> str | None:
        self._registry.require(session_key)
        with main_database(self._path).read() as db:
            return self._latest_cursor(session_key, db)

    @staticmethod
    def _latest_cursor(session_key: str, db: sqlite3.Connection) -> str | None:
        row = db.execute(
            """
            SELECT cursor_token FROM session_inbox_cursors
            WHERE session_key = ? ORDER BY rowid DESC LIMIT 1
            """,
            (session_key,),
        ).fetchone()
        return None if row is None else str(row[0])

    @contextmanager
    def _snapshot(self) -> Iterator[sqlite3.Connection]:
        """One read transaction; under WAL every read in it sees the same state."""

        # A pooled reader does not open a transaction for a SELECT on its own;
        # the transaction is rolled back when the connection is handed back.
        with main_database(self._path).read() as db:
            db.execute("BEGIN")
            yield db

    def ack(self, session_key: str, batch_id: str) -> InboxAck:
        self._registry.require(session_key)
        with main_database(self._path).write() as db, db:
            row = db.execute(
                "SELECT session_key FROM session_inbox_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None or row[0] != session_key:
                raise CursorRejected(batch_id)
            db.execute(
                """
                UPDATE session_inbox_batches SET state = 'acknowledged'
                WHERE batch_id = ?
                """,
                (batch_id,),
            )
        return InboxAck(batch_id, "acknowledged", "unknown")

    def begin_snapshot(self, session_key: str) -> str:
        self._registry.require(session_key)
        frozen = json.dumps([event.event_id for event in self._events()])
        token = secrets.token_hex(16)
        with main_database(self._path).write() as db, db:
            db.execute(
                """
                INSERT INTO session_snapshots (snapshot_token, session_key, frozen_ids)
                VALUES (?, ?, ?)
                """,
                (token, session_key, frozen),
            )
        return token

    def finish_snapshot(self, session_key: str, token: str) -> InboxPage:
        self._registry.require(session_key)
        with main_database(self._path).read() as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT session_key FROM session_snapshots WHERE snapshot_token = ?",
                (token,),
            ).fetchone()
        if row is None or row["session_key"] != session_key:
            raise CursorRejected(token)
        # Events committed before finish belong in this page. The cursor stops
        # at the last event actually returned, so a late insert is not skipped.
        return self.pull(session_key, cursor=None, limit=128)

    def signal(self, session_key: str) -> InboxSignal:
        self._registry.require(session_key)
        return InboxSignal(secrets.token_hex(16))

    def _cursor_position(
        self, session_key: str, cursor: str | None, db: sqlite3.Connection
    ) -> tuple[str | None, int]:
        if cursor is None:
            return None, self._epoch(session_key, db)
        row = db.execute(
            """
            SELECT session_key, scanned_event_id, permission_epoch
            FROM session_inbox_cursors WHERE cursor_token = ?
            """,
            (cursor,),
        ).fetchone()
        if row is None or row[0] != session_key:
            raise CursorRejected(cursor)
        return row[1], int(row[2])

    @staticmethod
    def _scan(
        granted: set[str],
        start_after: str | None,
        limit: int,
        events: tuple[InboxEvent, ...],
    ) -> tuple[list[InboxEvent], bool]:
        found = start_after is None
        selected: list[InboxEvent] = []
        for event in events:
            if not found:
                if event.event_id == start_after:
                    found = True
                continue
            if event.source_id not in granted:
                continue
            if len(selected) >= limit:
                break
            selected.append(event)
        return selected, found

    def _store_page(
        self,
        session_key: str,
        scanned_id: str | None,
        epoch: int,
        state: str,
        selected: list[InboxEvent],
    ) -> InboxPage:
        token = secrets.token_hex(32)
        batch_id = secrets.token_hex(16)
        with main_database(self._path).write() as db, db:
            db.execute(
                """
                INSERT INTO session_inbox_cursors (
                    cursor_token, session_key, scanned_event_id, permission_epoch
                ) VALUES (?, ?, ?, ?)
                """,
                (token, session_key, scanned_id, epoch),
            )
            db.execute(
                """
                INSERT INTO session_inbox_batches (batch_id, session_key, state)
                VALUES (?, ?, ?)
                """,
                (batch_id, session_key, state),
            )
        return InboxPage(batch_id, token, state, "unknown", tuple(selected))

    @staticmethod
    def _epoch(session_key: str, db: sqlite3.Connection) -> int:
        row = db.execute(
            "SELECT permission_epoch FROM session_subscriptions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    @staticmethod
    def _granted(session_key: str, db: sqlite3.Connection) -> set[str]:
        row = db.execute(
            "SELECT granted_sources FROM session_subscriptions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        if row is None:
            return set()
        loaded = json.loads(row[0])
        return set(loaded) if isinstance(loaded, list) else set()

    def _events(self, db: sqlite3.Connection | None = None) -> tuple[InboxEvent, ...]:
        if db is None:
            with main_database(self._path).read() as own:
                return self._events(own)
        events: dict[str, tuple[str, InboxEvent]] = {}
        for evidence_id, revision, source_id, created_at in db.execute(
            "SELECT evidence_id, revision, source_id, updated_at FROM evidence"
        ):
            event_id = evidence_event_id(str(evidence_id), int(revision))
            events[event_id] = (
                str(created_at),
                InboxEvent(event_id, str(evidence_id), int(revision), str(source_id)),
            )
        for (
            event_id,
            evidence_id,
            revision,
            source_id,
            created_at,
        ) in db.execute(
            """
            SELECT o.event_id, o.evidence_id, o.evidence_revision, e.source_id, o.created_at
            FROM change_outbox o
            LEFT JOIN evidence e ON e.evidence_id = o.evidence_id
            """
        ):
            events.setdefault(
                str(event_id),
                (str(created_at), InboxEvent(str(event_id), evidence_id, revision, source_id)),
            )
        return tuple(
            event
            for _occurred_at, event in sorted(
                events.values(), key=lambda item: (item[0], item[1].event_id)
            )
        )

    @staticmethod
    def _without_host_echo(
        events: tuple[InboxEvent, ...], db: sqlite3.Connection
    ) -> tuple[InboxEvent, ...]:
        """The host can save our notice back; that is not a new decision."""

        known = {event.event_id for event in events}
        delivered: set[str] = set()
        kept: list[InboxEvent] = []
        for event in events:
            if event.evidence_id is None:
                kept.append(event)
                continue
            row = db.execute(
                "SELECT verbatim FROM evidence WHERE evidence_id = ?",
                (event.evidence_id,),
            ).fetchone()
            verbatim = "" if row is None else str(row[0])
            if is_pure_echo(verbatim, known):
                delivered.update(echoed_event_ids(verbatim))
                continue
            kept.append(event)
        return tuple(event for event in kept if event.event_id not in delivered)
