"""One-time loopback exchange for the Web Console.

The browser must never receive the Core bearer token. This module holds the
short-lived exchange codes and opaque browser sessions; persistence is not
needed because both lifetimes are measured in seconds and are bound to one
Core instance.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

EXCHANGE_TTL = timedelta(seconds=60)
SESSION_TTL = timedelta(hours=12)


@dataclass
class _Exchange:
    instance_id: str
    expires_at: datetime


@dataclass
class _Session:
    instance_id: str
    expires_at: datetime


@dataclass
class UISessionStore:
    """In-memory one-time codes and browser sessions for one Core process."""

    instance_id: str
    _exchanges: dict[str, _Exchange] = field(default_factory=dict)
    _sessions: dict[str, _Session] = field(default_factory=dict)

    def issue_exchange(self, *, now: datetime | None = None) -> tuple[str, datetime]:
        now = now or datetime.now(UTC)
        self._prune(now)
        code = secrets.token_urlsafe(32)
        expires_at = now + EXCHANGE_TTL
        self._exchanges[code] = _Exchange(instance_id=self.instance_id, expires_at=expires_at)
        return code, expires_at

    def consume_exchange(self, code: str, *, now: datetime | None = None) -> str | None:
        """Atomically consume a code and return a browser session id.

        A code is removed before the caller can use it, so a replay can only
        fail. A code minted by another Core instance is refused even if the
        random value somehow collides.
        """
        now = now or datetime.now(UTC)
        self._prune(now)
        exchange = self._exchanges.pop(code, None)
        if exchange is None or exchange.expires_at <= now:
            return None
        if exchange.instance_id != self.instance_id:
            return None
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = _Session(
            instance_id=self.instance_id,
            expires_at=now + SESSION_TTL,
        )
        return session_id

    def valid_session(self, session_id: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        self._prune(now)
        session = self._sessions.get(session_id)
        return session is not None and session.instance_id == self.instance_id

    def revoke_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _prune(self, now: datetime) -> None:
        for code, exchange in tuple(self._exchanges.items()):
            if exchange.expires_at <= now:
                self._exchanges.pop(code, None)
        for session_id, session in tuple(self._sessions.items()):
            if session.expires_at <= now:
                self._sessions.pop(session_id, None)
