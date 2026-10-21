"""Tail metadata primitives.

The process-local lane below is deliberately still INERT: it is bounded and
best effort, and its queued callbacks are lost on process death. The durable
handoff store at the bottom is the implementation of the reliability contract:
it persists the minimal intent, claims it with a lease, and makes startup
reconciliation idempotent. Nothing in this module is wired into a route; a
composition-root change is still required and separately gated.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from one_memory.database_access import main_database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TailClaim:
    event_id: str
    token: str


@dataclass(frozen=True)
class TailHandoffRun:
    processed: int
    remaining: int
    timed_out: bool


class TailMetadataLane:
    """Bounded post-response retry lane for optional metadata writes."""

    def __init__(self, *, max_pending: int = 256) -> None:
        if type(max_pending) is not int or max_pending < 1:
            raise ValueError("max_pending must be a positive integer")
        self._pending: queue.Queue[tuple[Callable[[], Any], int]] = queue.Queue(maxsize=max_pending)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._dropped = 0
        self._lock = threading.Lock()

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    def submit(self, operation: Callable[[], Any], *, attempts: int = 3) -> bool:
        """Queue one post-response operation without blocking the caller."""
        if attempts < 1:
            raise ValueError("attempts must be positive")
        self._ensure_started()
        try:
            self._pending.put_nowait((operation, attempts))
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False
        return True

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="one-memory-tail-metadata",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                operation, attempts = self._pending.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                for attempt in range(attempts):
                    try:
                        operation()
                        break
                    except Exception:
                        if attempt + 1 >= attempts:
                            logger.warning("tail_metadata_write_failed")
                        else:
                            self._stop.wait(0.05 * (attempt + 1))
            finally:
                self._pending.task_done()

    def stop(self, *, drain: bool = False) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        if drain:
            while True:
                try:
                    operation, attempts = self._pending.get_nowait()
                except queue.Empty:
                    break
                try:
                    operation()
                finally:
                    self._pending.task_done()


class TailHandoffStore:
    """Durable, bounded handoff for optional tail metadata.

    Rows contain only an opaque identity and a small diagnostic payload. A
    completed row is terminal; a crashed `running` row is reclaimable after its
    lease expires. `record()` is idempotent on `event_id`.
    """

    _STATES = frozenset({"pending", "running", "completed", "failed", "unknown"})

    def __init__(
        self,
        database_path: Path,
        *,
        lease: timedelta = timedelta(seconds=30),
        max_pending: int = 256,
        max_payload_bytes: int = 16_384,
    ) -> None:
        self.database_path = database_path
        self.lease = lease
        self.max_pending = max_pending
        self.max_payload_bytes = max_payload_bytes
        if lease <= timedelta(0) or max_pending < 1:
            raise ValueError("invalid tail handoff limits")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def submit(self, event_id: str, payload: dict[str, object]) -> bool:
        """Persist one minimal handoff intent; identical replay is idempotent."""
        if not event_id or not isinstance(payload, dict):
            raise ValueError("invalid tail handoff")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.max_payload_bytes:
            raise ValueError("tail_handoff_payload_too_large")
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            existing = connection.execute(
                "SELECT payload_json, state FROM tail_handoff WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != encoded:
                    raise ValueError("tail_handoff_conflict")
                return False
            pending = connection.execute(
                "SELECT count(*) FROM tail_handoff WHERE state IN ('pending','running')"
            ).fetchone()[0]
            if pending >= self.max_pending:
                raise OverflowError("tail_handoff_capacity")
            connection.execute(
                "INSERT INTO tail_handoff"
                "(event_id,created_at,payload_json,state,attempts,lease_owner,"
                "lease_token,lease_expires_at,last_error,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_id, now, encoded, "pending", 0, None, None, None, None, now),
            )
            return True

    def claim(self, owner: str, *, limit: int = 1) -> tuple[TailClaim, ...]:
        if not owner or limit < 1:
            raise ValueError("invalid tail handoff claim")
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        expires = (now_dt + self.lease).isoformat()
        with main_database(self.database_path).write() as connection, connection:
            rows = connection.execute(
                "SELECT event_id FROM tail_handoff "
                "WHERE (state='pending' AND lease_expires_at IS NULL) OR "
                "(state='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?) "
                "ORDER BY created_at, event_id LIMIT ?",
                (now, limit),
            ).fetchall()
            claimed: list[TailClaim] = []
            for row in rows:
                event_id = str(row[0])
                token = uuid.uuid4().hex
                updated = connection.execute(
                    "UPDATE tail_handoff SET state='running', lease_owner=?, "
                    "lease_token=?, lease_expires_at=?, attempts=attempts+1, updated_at=? "
                    "WHERE event_id=? AND ((state='pending' AND lease_expires_at IS NULL) "
                    "OR (state='running' AND lease_expires_at IS NOT NULL "
                    "AND lease_expires_at < ?))",
                    (owner, token, expires, now, event_id, now),
                )
                if updated.rowcount == 1:
                    claimed.append(TailClaim(event_id, token))
            return tuple(claimed)

    def startup_reconcile(self) -> int:
        """Return expired running rows to pending so a new worker can retry them."""
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            updated = connection.execute(
                "UPDATE tail_handoff SET state='pending', lease_owner=NULL, "
                "lease_token=NULL, lease_expires_at=NULL, updated_at=? "
                "WHERE state='running' "
                "AND (lease_expires_at IS NULL OR lease_expires_at < ?)",
                (now, now),
            )
            return updated.rowcount

    def release(
        self,
        claim: TailClaim,
        *,
        owner: str,
    ) -> bool:
        """Return this worker's unexpired claim to pending without losing it."""
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            updated = connection.execute(
                "UPDATE tail_handoff SET state='pending', lease_owner=NULL, "
                "lease_token=NULL, lease_expires_at=NULL, updated_at=? "
                "WHERE event_id=? AND state='running' AND lease_owner=? AND lease_token=? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at >= ?",
                (now, claim.event_id, owner, claim.token, now),
            )
            return updated.rowcount == 1

    def drain_once(
        self,
        execute: Callable[[TailClaim], None],
        *,
        owner: str,
        limit: int = 1,
    ) -> TailHandoffRun:
        """Claim and settle one bounded batch; failures return to pending."""
        claims = self.claim(owner, limit=limit)
        processed = 0
        for claim in claims:
            try:
                execute(claim)
            except Exception:
                self.release(claim, owner=owner)
                continue
            if self.complete(claim.event_id, owner=owner, token=claim.token):
                processed += 1
        return TailHandoffRun(
            processed=processed,
            remaining=self.pending_count(),
            timed_out=False,
        )

    def exit_flush(
        self,
        execute: Callable[[TailClaim], None],
        *,
        owner: str,
        timeout_seconds: float,
        limit: int = 1,
    ) -> TailHandoffRun:
        """Bounded shutdown flush. Unsent work remains recoverable in the table."""
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        deadline = time.monotonic() + timeout_seconds
        processed = 0
        timed_out = False
        while time.monotonic() < deadline:
            claims = self.claim(owner, limit=limit)
            if not claims:
                break
            for claim in claims:
                if time.monotonic() >= deadline:
                    self.release(claim, owner=owner)
                    timed_out = True
                    continue
                try:
                    execute(claim)
                except Exception:
                    self.release(claim, owner=owner)
                    continue
                if self.complete(claim.event_id, owner=owner, token=claim.token):
                    processed += 1
        return TailHandoffRun(
            processed=processed,
            remaining=self.pending_count(),
            timed_out=timed_out,
        )

    def complete(self, event_id: str, *, owner: str, token: str) -> bool:
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            updated = connection.execute(
                "UPDATE tail_handoff SET state='completed', lease_owner=NULL, "
                "lease_expires_at=NULL, last_error=NULL, updated_at=? "
                "WHERE event_id=? AND state='running' AND lease_owner=? AND lease_token=? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at >= ?",
                (now, event_id, owner, token, now),
            )
            return updated.rowcount == 1

    def fail(self, event_id: str, *, owner: str, token: str, error_code: str) -> bool:
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            updated = connection.execute(
                "UPDATE tail_handoff SET state='failed', lease_owner=NULL, "
                "lease_expires_at=NULL, last_error=?, updated_at=? "
                "WHERE event_id=? AND state='running' AND lease_owner=? AND lease_token=? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at >= ?",
                (error_code, now, event_id, owner, token, now),
            )
            return updated.rowcount == 1

    def unknown(self, event_id: str, *, owner: str, token: str, error_code: str) -> bool:
        """Terminally park an outcome that may already have been delivered."""
        now = self._now()
        with main_database(self.database_path).write() as connection, connection:
            updated = connection.execute(
                "UPDATE tail_handoff SET state='unknown', lease_owner=NULL, "
                "lease_expires_at=NULL, last_error=?, updated_at=? "
                "WHERE event_id=? AND state='running' AND lease_owner=? AND lease_token=? "
                "AND lease_expires_at IS NOT NULL AND lease_expires_at >= ?",
                (error_code, now, event_id, owner, token, now),
            )
            return updated.rowcount == 1

    def pending_count(self) -> int:
        with main_database(self.database_path).read() as connection:
            return int(
                connection.execute(
                    "SELECT count(*) FROM tail_handoff WHERE state IN ('pending','running')"
                ).fetchone()[0]
            )

    def prune_terminal(self, *, older_than: timedelta = timedelta(days=7)) -> int:
        cutoff = (datetime.now(UTC) - older_than).isoformat()
        with main_database(self.database_path).write() as connection, connection:
            return connection.execute(
                "DELETE FROM tail_handoff "
                "WHERE state IN ('completed','failed','unknown') AND updated_at < ?",
                (cutoff,),
            ).rowcount
