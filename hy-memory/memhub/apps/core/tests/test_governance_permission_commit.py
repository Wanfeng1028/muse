import sqlite3

import pytest

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import MemoryDraft, MemoryGovernanceStore, MemoryKind
from tests.person_door import as_person


def test_permission_guard_is_rechecked_inside_write_transaction_and_rolls_back(tmp_path):
    database = tmp_path / "test.sqlite"
    evidence = EvidenceStore(database)
    original = evidence.put(
        EvidenceInput(
            source_id="fixture",
            conversation_id="one",
            message_id="one",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="synthetic",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    store = MemoryGovernanceStore(database)
    attempts = []

    def guard():
        attempts.append("check")
        if len(attempts) == 2:
            raise RuntimeError("permission revoked before commit")

    with pytest.raises(RuntimeError, match="revoked before commit"), store.guard_writes(guard):
        as_person(store).create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content="synthetic result",
                evidence_ids=(original.evidence_id,),
                scopes=("all-apps",),
            ),
            request_id="attempt",
        )
    assert attempts == ["check", "check"]
    assert store.list(user_id="local") == []
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM governed_memory_mutations").fetchone()[0] == 0


def test_guard_context_does_not_leak_into_subsequent_manual_actions(tmp_path):
    database = tmp_path / "test.sqlite"
    evidence = EvidenceStore(database)
    original = evidence.put(
        EvidenceInput(
            source_id="fixture",
            conversation_id="one",
            message_id="one",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="synthetic",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    store = MemoryGovernanceStore(database)

    def denied():
        raise RuntimeError("denied")

    with store.guard_writes(denied):
        assert store.list(user_id="local") == []
    result = as_person(store).create(
        MemoryDraft(
            user_id="local",
            kind=MemoryKind.CHAT,
            content="manual action",
            evidence_ids=(original.evidence_id,),
            scopes=("private",),
        ),
        request_id="manual",
    )
    assert result.content == "manual action"


def test_guard_check_and_commit_hold_database_write_authority(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    database = tmp_path / "test.sqlite"
    evidence = EvidenceStore(database)
    record = evidence.put(
        EvidenceInput(
            source_id="fixture",
            conversation_id="one",
            message_id="one",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="synthetic",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    store = MemoryGovernanceStore(database)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE permission_fixture (revoked INTEGER)")
        db.execute("INSERT INTO permission_fixture VALUES (0)")
    checks = []

    def revoke():
        with sqlite3.connect(database, timeout=0) as db:
            db.execute("UPDATE permission_fixture SET revoked=1")

    def guard():
        with (
            ThreadPoolExecutor(max_workers=1) as pool,
            pytest.raises(sqlite3.OperationalError, match="locked"),
        ):
            pool.submit(revoke).result(timeout=2)
        checks.append("write-locked")

    with store.guard_writes(guard):
        result = as_person(store).create(
            MemoryDraft(
                user_id="local",
                kind=MemoryKind.CHAT,
                content="permitted",
                evidence_ids=(record.evidence_id,),
                scopes=("private",),
            ),
            request_id="permission-checked",
        )
    assert checks == ["write-locked", "write-locked"]
    revoke()
    assert store.get(result.memory_id, user_id="local") is not None
