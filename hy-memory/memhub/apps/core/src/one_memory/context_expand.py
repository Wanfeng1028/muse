"""Short-lived, authority-bound references for bounded raw conversation expansion."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from one_memory.context_models import ContextMessage
from one_memory.context_raw import _check, _connection, _execute, _message, _readable

_TOKEN_VERSION = 1
_MAX_TTL_SECONDS = 300
_MAX_DEPTH = 2
_MAX_MESSAGES = 4
_MAX_CHARACTERS = 6000


@dataclass(frozen=True)
class ExpansionAuthority:
    runtime_instance: str
    installation_id: str
    installation_revision: int
    host_id: str
    scopes: frozenset[str]
    source_ids: frozenset[str]


@dataclass(frozen=True)
class ExpansionGrant:
    runtime_instance: str
    installation_id: str
    installation_revision: int
    host_id: str
    scope_digest: str
    source_id: str
    conversation_id: str
    evidence_id: str
    evidence_revision: int
    expires_at: int
    remaining_depth: int
    remaining_messages: int
    remaining_characters: int


class ExpandedRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=512)
    revision: int = Field(ge=1)
    start_cp: int = Field(ge=0, strict=True)
    end_cp: int = Field(ge=0, strict=True)
    reason: Literal["included", "character_budget"] = "included"

    @model_validator(mode="after")
    def ordered(self) -> ExpandedRange:
        if self.end_cp < self.start_cp:
            raise ValueError("invalid_range")
        return self


class ExpansionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok", "degraded", "unavailable"]
    reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    messages: tuple[ContextMessage, ...] = Field(default=(), max_length=_MAX_MESSAGES)
    ranges: tuple[ExpandedRange, ...] = Field(default=(), max_length=_MAX_MESSAGES)
    used_characters: int = Field(ge=0, le=_MAX_CHARACTERS)
    truncated: bool
    next_ref: str | None = Field(default=None, max_length=4096)


class ExpansionRefError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _scope_digest(authority: ExpansionAuthority) -> str:
    payload = json.dumps(
        {
            "scopes": sorted(authority.scopes),
            "source_ids": sorted(authority.source_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ExpansionRefSigner:
    """Issue references that naturally expire when the process key changes."""

    def __init__(
        self, secret: bytes | None = None, *, clock: Callable[[], float] = time.time
    ) -> None:
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        if len(self._secret) < 32:
            raise ValueError("expansion_secret_too_short")
        self._clock = clock
        self._used: set[str] = set()
        self._lock = threading.Lock()

    def issue(
        self,
        *,
        authority: ExpansionAuthority,
        source_id: str,
        conversation_id: str,
        evidence_id: str,
        evidence_revision: int,
        ttl_seconds: int = _MAX_TTL_SECONDS,
        remaining_depth: int = 1,
        remaining_messages: int = _MAX_MESSAGES,
        remaining_characters: int = _MAX_CHARACTERS,
    ) -> str:
        if source_id not in authority.source_ids:
            raise ExpansionRefError("expansion_permission_denied")
        if not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ExpansionRefError("expansion_invalid_ttl")
        if not 1 <= remaining_depth <= _MAX_DEPTH:
            raise ExpansionRefError("expansion_invalid_depth")
        if not 1 <= remaining_messages <= _MAX_MESSAGES:
            raise ExpansionRefError("expansion_invalid_message_budget")
        if not 1 <= remaining_characters <= _MAX_CHARACTERS:
            raise ExpansionRefError("expansion_invalid_character_budget")
        grant = ExpansionGrant(
            runtime_instance=authority.runtime_instance,
            installation_id=authority.installation_id,
            installation_revision=authority.installation_revision,
            host_id=authority.host_id,
            scope_digest=_scope_digest(authority),
            source_id=source_id,
            conversation_id=conversation_id,
            evidence_id=evidence_id,
            evidence_revision=evidence_revision,
            expires_at=math.floor(self._clock()) + ttl_seconds,
            remaining_depth=remaining_depth,
            remaining_messages=remaining_messages,
            remaining_characters=remaining_characters,
        )
        body = json.dumps(
            {"v": _TOKEN_VERSION, **asdict(grant)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return f"{_b64encode(body)}.{_b64encode(hmac.digest(self._secret, body, 'sha256'))}"

    def verify(
        self, token: str, authority: ExpansionAuthority, *, consume: bool = True
    ) -> ExpansionGrant:
        try:
            encoded, signature = token.split(".", 1)
            body = _b64decode(encoded)
            expected = hmac.digest(self._secret, body, "sha256")
            if not hmac.compare_digest(expected, _b64decode(signature)):
                raise ExpansionRefError("expansion_invalid_ref")
            raw = json.loads(body)
            if set(raw) != {"v", *ExpansionGrant.__dataclass_fields__} or raw.pop("v") != 1:
                raise ExpansionRefError("expansion_invalid_ref")
            grant = ExpansionGrant(**raw)
        except ExpansionRefError:
            raise
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise ExpansionRefError("expansion_invalid_ref") from None
        if grant.expires_at < math.floor(self._clock()):
            raise ExpansionRefError("expansion_expired_ref")
        if (
            grant.runtime_instance != authority.runtime_instance
            or grant.installation_id != authority.installation_id
            or grant.installation_revision != authority.installation_revision
            or grant.host_id != authority.host_id
            or grant.scope_digest != _scope_digest(authority)
            or grant.source_id not in authority.source_ids
        ):
            raise ExpansionRefError("expansion_permission_denied")
        if consume:
            token_digest = hashlib.sha256(token.encode()).hexdigest()
            with self._lock:
                if token_digest in self._used:
                    raise ExpansionRefError("expansion_replayed_ref")
                self._used.add(token_digest)
        return grant


def expand_raw_context(
    database_path: Path,
    grant: ExpansionGrant,
    *,
    authority: ExpansionAuthority,
    deadline: float,
) -> ExpansionResult:
    """Expand only the signed conversation window after current-authority checks."""
    if (
        grant.runtime_instance != authority.runtime_instance
        or grant.installation_id != authority.installation_id
        or grant.installation_revision != authority.installation_revision
        or grant.host_id != authority.host_id
        or grant.source_id not in authority.source_ids
        or grant.scope_digest != _scope_digest(authority)
    ):
        raise ExpansionRefError("expansion_permission_denied")
    readable, values = _readable(authority.source_ids)
    body_limit = grant.remaining_characters + 1
    try:
        _check(deadline)
        with _connection(database_path, deadline) as db:
            anchor = _execute(
                db,
                deadline,
                f"""SELECT e.evidence_id,e.revision,e.role,e.written_by,e.created_at,
                       substr(e.verbatim,1,?) AS text,length(e.verbatim)>? AS body_truncated
                FROM evidence e
                WHERE {readable} AND e.evidence_id=? AND e.revision=?
                  AND e.source_id=? AND e.conversation_id=?""",
                [
                    body_limit,
                    body_limit - 1,
                    *values,
                    grant.evidence_id,
                    grant.evidence_revision,
                    grant.source_id,
                    grant.conversation_id,
                ],
            ).fetchone()
            if anchor is None:
                raise ExpansionRefError("expansion_stale_ref")
            neighbor_limit = grant.remaining_messages - 1
            before_limit = neighbor_limit // 2
            before = _execute(
                db,
                deadline,
                f"""SELECT e.evidence_id,e.revision,e.role,e.written_by,e.created_at,
                       substr(e.verbatim,1,?) AS text,length(e.verbatim)>? AS body_truncated
                FROM evidence e JOIN evidence seed ON seed.evidence_id=?
                WHERE {readable} AND e.source_id=? AND e.conversation_id=?
                  AND (coalesce(e.created_at,e.imported_at),
                       e.source_ordinal IS NOT NULL,coalesce(e.source_ordinal,''),e.evidence_id)
                      < (coalesce(seed.created_at,seed.imported_at),
                         seed.source_ordinal IS NOT NULL,coalesce(seed.source_ordinal,''),
                         seed.evidence_id)
                ORDER BY coalesce(e.created_at,e.imported_at) DESC,
                         e.source_ordinal DESC,e.evidence_id DESC LIMIT ?""",
                [
                    body_limit,
                    body_limit - 1,
                    grant.evidence_id,
                    *values,
                    grant.source_id,
                    grant.conversation_id,
                    before_limit,
                ],
            ).fetchall()[::-1]
            after_limit = neighbor_limit - len(before)
            after = _execute(
                db,
                deadline,
                f"""SELECT e.evidence_id,e.revision,e.role,e.written_by,e.created_at,
                       substr(e.verbatim,1,?) AS text,length(e.verbatim)>? AS body_truncated
                FROM evidence e JOIN evidence seed ON seed.evidence_id=?
                WHERE {readable} AND e.source_id=? AND e.conversation_id=?
                  AND (coalesce(e.created_at,e.imported_at),
                       e.source_ordinal IS NOT NULL,coalesce(e.source_ordinal,''),e.evidence_id)
                      > (coalesce(seed.created_at,seed.imported_at),
                         seed.source_ordinal IS NOT NULL,coalesce(seed.source_ordinal,''),
                         seed.evidence_id)
                ORDER BY coalesce(e.created_at,e.imported_at) ASC,
                         e.source_ordinal ASC,e.evidence_id ASC LIMIT ?""",
                [
                    body_limit,
                    body_limit - 1,
                    grant.evidence_id,
                    *values,
                    grant.source_id,
                    grant.conversation_id,
                    after_limit,
                ],
            ).fetchall()
            chronological = (*before, anchor, *after)
            priority = (anchor, *reversed(before), *after)
            selected: set[str] = set()
            ranges: list[ExpandedRange] = []
            range_ids: set[str] = set()
            used = 0
            truncated = False
            for row in priority:
                message = _message(row)
                if message.truncated or used + len(message.text) > grant.remaining_characters:
                    truncated = True
                    if message.evidence_id not in range_ids:
                        ranges.append(
                            ExpandedRange(
                                evidence_id=message.evidence_id,
                                revision=message.revision,
                                start_cp=0,
                                end_cp=0,
                                reason="character_budget",
                            )
                        )
                        range_ids.add(message.evidence_id)
                    continue
                selected.add(message.evidence_id)
                if message.evidence_id not in range_ids:
                    ranges.append(
                        ExpandedRange(
                            evidence_id=message.evidence_id,
                            revision=message.revision,
                            start_cp=0,
                            end_cp=len(message.text),
                        )
                    )
                    range_ids.add(message.evidence_id)
                used += len(message.text)
            messages = [
                _message(row) for row in chronological if str(row["evidence_id"]) in selected
            ]
            _check(deadline)
    except ExpansionRefError:
        raise
    except TimeoutError:
        return ExpansionResult(
            status="unavailable", reason="timeout_budget", used_characters=0, truncated=True
        )
    except (sqlite3.Error, OSError, ValueError):
        return ExpansionResult(
            status="unavailable", reason="read_unavailable", used_characters=0, truncated=False
        )
    return ExpansionResult(
        status="degraded" if truncated else "ok",
        reason="character_budget" if truncated else None,
        messages=tuple(messages),
        ranges=tuple(ranges),
        used_characters=used,
        truncated=truncated,
    )
