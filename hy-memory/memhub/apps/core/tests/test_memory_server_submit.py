"""A3-01/A3-04: one front door, and what "the same write twice" means.

A3 exists so that Function, MCP, the scanner and Hooks cannot each grow their
own path to HY. These tests pin the two properties that make a shared door
safe: a replay is recognised, and a conflicting reuse is refused rather than
silently resolved either way.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from one_memory.database_access import main_database
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.contracts import BatchIdentity, WriteRequest
from one_memory.memory_server.submit import (
    SubmittedEvidenceMismatch,
    WriteConflictError,
    build_reconcile_request,
    build_request,
    build_request_from_evidence,
    payload_fingerprint,
    submit_write,
)


def test_first_submission_enqueues() -> None:
    request = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e1"]
    )
    result = submit_write(request)
    assert result.enqueued is True
    assert result.request_id == request.request_key


def test_identical_replay_does_not_enqueue_again() -> None:
    """A replayed scan must not produce a second write for the same batch."""
    request = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e1"]
    )
    first = submit_write(request)
    known = {request.request_key: payload_fingerprint(request)}
    replay = submit_write(request, known=known)
    assert first.enqueued is True
    assert replay.enqueued is False


def test_same_key_different_evidence_is_a_conflict() -> None:
    """Same batch, different evidence: refusing is better than either guess.

    Overwriting would drop the first evidence set; accepting would leave two
    different writes under one identity.
    """
    original = build_request(
        internal_session_id="s1",
        first_round=1,
        last_round=5,
        evidence_ids=["e1"],
        idempotency_key="fixed",
    )
    changed = build_request(
        internal_session_id="s1",
        first_round=1,
        last_round=5,
        evidence_ids=["e2"],
        idempotency_key="fixed",
    )
    known = {original.request_key: payload_fingerprint(original)}
    with pytest.raises(WriteConflictError):
        submit_write(changed, known=known)


def test_same_key_different_round_range_is_a_conflict() -> None:
    original = build_request(
        internal_session_id="s1",
        first_round=1,
        last_round=5,
        evidence_ids=["e1"],
        idempotency_key="fixed",
    )
    changed = build_request(
        internal_session_id="s1",
        first_round=6,
        last_round=10,
        evidence_ids=["e1"],
        idempotency_key="fixed",
    )
    known = {original.request_key: payload_fingerprint(original)}
    with pytest.raises(WriteConflictError):
        submit_write(changed, known=known)


def test_default_key_is_the_batch_id() -> None:
    """Deriving the key from the batch is what makes replays recognisable."""
    request = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e1"]
    )
    assert request.request_key == request.batch_identity.batch_id


def test_same_batch_different_session_gets_a_different_key() -> None:
    first = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e1"]
    )
    second = build_request(
        internal_session_id="s2", first_round=1, last_round=5, evidence_ids=["e1"]
    )
    assert first.request_key != second.request_key


def test_fingerprint_ignores_evidence_order() -> None:
    """The same evidence in a different order is the same write."""
    first = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e1", "e2"]
    )
    second = build_request(
        internal_session_id="s1", first_round=1, last_round=5, evidence_ids=["e2", "e1"]
    )
    assert payload_fingerprint(first) == payload_fingerprint(second)


def test_evidence_is_required() -> None:
    with pytest.raises(ValueError):
        build_request(internal_session_id="s1", first_round=1, last_round=5, evidence_ids=[])


def test_backwards_round_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_request(internal_session_id="s1", first_round=5, last_round=1, evidence_ids=["e1"])


def _put(
    store: EvidenceStore,
    *,
    conversation_id: str,
    message_id: str,
    source_id: str = "source",
) -> str:
    return store.put(
        EvidenceInput(
            source_id=source_id,
            conversation_id=conversation_id,
            message_id=message_id,
            source_ordinal=message_id,
            role="user",
            written_by=WrittenBy.PERSON,
            created_at=datetime.now(UTC),
            verbatim=f"body {conversation_id}/{message_id}",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record.evidence_id


def test_build_request_from_evidence_uses_the_store_order(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    first = _put(store, conversation_id="c1", message_id="m1")
    second = _put(store, conversation_id="c1", message_id="m2")

    write = build_request_from_evidence(
        [second, first],
        evidence=store,
        first_round=1,
        last_round=1,
    )

    assert write.internal_session_id == "c1"
    assert write.evidence_ids == [first, second]
    assert write.batch_identity.first_round == 1
    assert write.batch_identity.last_round == 1


def test_build_request_from_evidence_orders_iso_times_as_instants(tmp_path: Path) -> None:
    """ISO offsets must not turn the turn order into a lexical sort.

    `2026-09-09T08:00:00+08:00` is 00:00 UTC and precedes
    `2026-09-09T01:00:00+00:00`, but lexical order puts the 01:00 string
    first. The queue must preserve the actual evidence order, not the
    rendering's offset.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    first_instant = _put(store, conversation_id="c1", message_id="m1")
    second_instant = _put(store, conversation_id="c1", message_id="m2")
    with sqlite3.connect(path) as connection, connection:
        connection.execute(
            "UPDATE evidence SET created_at=? WHERE evidence_id=?",
            ("2026-09-09T08:00:00+08:00", first_instant),
        )
        connection.execute(
            "UPDATE evidence SET created_at=? WHERE evidence_id=?",
            ("2026-09-09T01:00:00+00:00", second_instant),
        )

    write = build_request_from_evidence(
        [second_instant, first_instant],
        evidence=store,
        first_round=1,
        last_round=1,
    )

    assert write.evidence_ids == [first_instant, second_instant]


def test_build_request_from_evidence_rejects_a_missing_id(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    _put(store, conversation_id="c1", message_id="m1")

    with pytest.raises(SubmittedEvidenceMismatch, match="missing evidence"):
        build_request_from_evidence(
            ["missing"],
            evidence=store,
            first_round=1,
            last_round=1,
        )


def test_build_request_from_evidence_rejects_multiple_conversations(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    first = _put(store, conversation_id="c1", message_id="m1")
    second = _put(store, conversation_id="c2", message_id="m1")

    with pytest.raises(SubmittedEvidenceMismatch, match="one conversation"):
        build_request_from_evidence(
            [first, second],
            evidence=store,
            first_round=1,
            last_round=2,
        )


def test_build_request_from_evidence_does_not_infer_the_round_range(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    evidence_id = _put(store, conversation_id="c1", message_id="m1")

    write = build_request_from_evidence(
        [evidence_id],
        evidence=store,
        first_round=6,
        last_round=10,
    )

    assert write.batch_identity.first_round == 6
    assert write.batch_identity.last_round == 10


def test_build_request_from_evidence_fails_closed_if_evidence_disappears(
    tmp_path: Path,
) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    evidence_id = _put(store, conversation_id="c1", message_id="m1")
    with main_database(path).write() as connection, connection:
        connection.execute("DELETE FROM evidence_origins WHERE evidence_id=?", (evidence_id,))
        connection.execute("DELETE FROM evidence WHERE evidence_id=?", (evidence_id,))

    with pytest.raises(SubmittedEvidenceMismatch, match="missing evidence"):
        build_request_from_evidence(
            [evidence_id],
            evidence=store,
            first_round=1,
            last_round=1,
        )


def test_build_request_from_evidence_uses_a_constant_number_of_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The batch boundary must not become one SQLite checkout per Evidence.

    A batch is allowed to hold many records, and queue submission runs on the
    same event loop as health checks. Counting the access-layer checkouts pins
    the guarantee that the adapter uses one read connection, not N+1.
    """
    from one_memory import database_access

    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    ids = [_put(store, conversation_id="c1", message_id=f"m{index}") for index in range(12)]
    original = database_access.MainDatabase._take_reader
    checkouts = 0

    def counted_take_reader(
        self: database_access.MainDatabase, me: int, busy_timeout_ms: int
    ) -> object:
        nonlocal checkouts
        checkouts += 1
        return original(self, me, busy_timeout_ms)

    monkeypatch.setattr(database_access.MainDatabase, "_take_reader", counted_take_reader)
    build_request_from_evidence(
        ids,
        evidence=store,
        first_round=1,
        last_round=1,
    )

    assert checkouts == 1


def test_build_request_from_evidence_is_idempotent_at_the_durable_boundary(
    tmp_path: Path,
) -> None:
    from one_memory.memory_server.durable_queue import DurableWriteQueue

    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    first = _put(store, conversation_id="c1", message_id="m1")
    second = _put(store, conversation_id="c1", message_id="m2")
    queue = DurableWriteQueue(path, evidence=store)

    request = build_request_from_evidence(
        [second, first],
        evidence=store,
        first_round=1,
        last_round=1,
    )
    accepted = queue.submit(request)
    replay = queue.submit(request)

    assert accepted.enqueued is True
    assert replay.job_id == accepted.job_id
    assert replay.enqueued is False


def test_build_reconcile_request_keeps_the_single_evidence_key_contract(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    orphan = _put(store, conversation_id="c1", message_id="m1")

    request = build_reconcile_request(
        [orphan],
        evidence=store,
        first_round=1,
        last_round=1,
    )

    assert request.request_key == f"reconcile:{orphan}"


def test_build_reconcile_request_is_order_independent_for_a_batch(tmp_path: Path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    first = _put(store, conversation_id="c1", message_id="m1")
    second = _put(store, conversation_id="c1", message_id="m2")

    forward = build_reconcile_request(
        [first, second],
        evidence=store,
        first_round=1,
        last_round=1,
    )
    reverse = build_reconcile_request(
        [second, first],
        evidence=store,
        first_round=1,
        last_round=1,
    )

    assert forward.request_key == reverse.request_key
    assert forward.request_key.startswith("reconcile:")


def test_build_reconcile_request_replays_without_a_second_job(tmp_path: Path) -> None:
    from one_memory.memory_server.durable_queue import DurableWriteQueue

    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    orphan = _put(store, conversation_id="c1", message_id="m1")
    queue = DurableWriteQueue(path, evidence=store)
    request = build_reconcile_request(
        [orphan],
        evidence=store,
        first_round=1,
        last_round=1,
    )

    first = queue.submit(request)
    replay = queue.submit(request)

    assert first.job_id == replay.job_id
    assert replay.enqueued is False
    assert queue.unsubmitted_evidence_ids() == ()


def test_build_reconcile_request_refuses_empty_evidence(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")

    with pytest.raises(SubmittedEvidenceMismatch, match="needs evidence"):
        build_reconcile_request(
            [],
            evidence=store,
            first_round=1,
            last_round=1,
        )


@pytest.mark.parametrize(
    "evidence_ids",
    [
        [""],
        [" "],
        ["\t"],
        ["e1", ""],
        ["e1", " "],
        ["e1", "e1"],
    ],
)
def test_write_request_rejects_empty_or_duplicate_evidence_ids(
    tmp_path: Path,
    evidence_ids: list[str],
) -> None:
    from one_memory.memory_server.durable_queue import DurableWriteQueue

    queue = DurableWriteQueue(tmp_path / "one-memory.sqlite3")

    with pytest.raises(ValueError):
        queue.submit(
            WriteRequest(
                internal_session_id="s",
                batch_identity=BatchIdentity(internal_session_id="s", first_round=1, last_round=1),
                evidence_ids=evidence_ids,
                idempotency_key="duplicate-or-empty",
            )
        )

    assert queue.get("duplicate-or-empty") is None
