"""A3-01: acceptance and outcome recording for the unified write path."""

from __future__ import annotations

import pytest

from one_memory.memory_server.contracts import BatchIdentity, WriteRequest
from one_memory.memory_server.registry import NON_TERMINAL, WriteRegistry
from one_memory.memory_server.submit import WriteConflictError


def _request(
    *,
    session: str = "sess-1",
    first: int = 1,
    last: int = 5,
    evidence: list[str] | None = None,
    key: str | None = None,
) -> WriteRequest:
    batch = BatchIdentity(internal_session_id=session, first_round=first, last_round=last)
    return WriteRequest(
        internal_session_id=session,
        batch_identity=batch,
        evidence_ids=evidence or ["e1"],
        idempotency_key=key or batch.batch_id,
    )


def test_first_submission_is_accepted() -> None:
    registry = WriteRegistry()
    record, enqueued = registry.submit(_request())
    assert record.state == "accepted"
    assert enqueued is True


def test_a_replay_returns_the_same_record_without_re_enqueueing() -> None:
    """Duplicating a memory is worse than admitting it already exists."""
    registry = WriteRegistry()
    first, _ = registry.submit(_request())
    second, enqueued = registry.submit(_request())
    assert second.request_id == first.request_id
    assert enqueued is False


def test_a_conflicting_reuse_raises() -> None:
    """Overwriting would discard the earlier intent."""
    registry = WriteRegistry()
    request = _request()
    registry.submit(request)
    conflicting = WriteRequest(
        internal_session_id=request.internal_session_id,
        batch_identity=request.batch_identity,
        evidence_ids=["different"],
        idempotency_key=request.idempotency_key,
    )
    with pytest.raises(WriteConflictError):
        registry.submit(conflicting)


def test_outcome_can_be_recorded_and_read_back() -> None:
    registry = WriteRegistry()
    record, _ = registry.submit(_request())
    updated = registry.set_state(record.request_id, "completed")
    assert updated is not None
    assert updated.state == "completed"
    assert registry.get(record.request_id) is not None
    assert registry.get(record.request_id).state == "completed"


def test_unknown_is_not_treated_as_final() -> None:
    """`unknown` still needs resolving; treating it as final would be wrong."""
    registry = WriteRegistry()
    record, _ = registry.submit(_request())
    registry.set_state(record.request_id, "unknown")
    assert "unknown" in NON_TERMINAL
    assert registry.get(record.request_id).state in NON_TERMINAL


def test_setting_state_on_an_unknown_id_does_not_invent_a_record() -> None:
    """'We never accepted this' must not read as 'accepted and failed'."""
    registry = WriteRegistry()
    assert registry.set_state("nope", "failed") is None


def test_a_terminal_record_cannot_be_resurrected() -> None:
    """A completed write must not move back to a live state.

    The registry's `get` is what a client polls instead of retrying. Letting a
    completed record become `accepted` again would make a duplicate write look
    legitimate.
    """
    registry = WriteRegistry()
    record, _ = registry.submit(_request())
    registry.set_state(record.request_id, "completed")

    assert registry.set_state(record.request_id, "accepted") is None
    assert registry.get(record.request_id).state == "completed"

    # Terminal -> terminal is still allowed (an inquiry may re-attest it).
    assert registry.set_state(record.request_id, "failed") is not None
    assert registry.get(record.request_id).state == "failed"
    assert registry.get("nope") is None


def test_unknown_request_returns_none() -> None:
    registry = WriteRegistry()
    assert registry.get("absent") is None


def test_the_registry_guard_fires_even_without_a_known_map() -> None:
    """The registry must not depend on the caller passing `known` correctly.

    `submit_write` raises on a conflicting key when it is told about the
    existing fingerprint, but a caller that passes an empty map must still be
    refused — otherwise a stale or partial view silently overwrites an earlier
    intent. This pins the registry's own check, independent of the caller.
    """
    registry = WriteRegistry()
    first = _request()
    registry.submit(first)

    conflicting = WriteRequest(
        internal_session_id=first.internal_session_id,
        batch_identity=first.batch_identity,
        evidence_ids=["different"],
        idempotency_key=first.idempotency_key,
    )
    with pytest.raises(WriteConflictError):
        registry.submit(conflicting, known={})
