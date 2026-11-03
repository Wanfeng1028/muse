"""The recall read path must not acquire the single global writer.

`MemoryGovernanceStore.find_confirmed_matching_terms` is the recall read path.
It calls `_refresh_content_shadow`, which opened `_connection()` with the
default `writing=True`. That means every recall read checked out the ONE global
writer connection for a check that changes nothing on a migrated database —
serializing unrelated readers behind the writer and inflating `writer_waits`.

The absent-shadow case must still fail closed (`governance_schema_missing`),
and it must do so without taking the writer: the LIKE fallback already handles
a missing shadow, and migration 32 — not this read path — owns the table.
"""

from __future__ import annotations

import sqlite3

import pytest

from one_memory.database_access import main_database
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_governance import HyCreate, MemoryDraft, MemoryGovernanceStore


def _store(tmp_path):
    database = tmp_path / "one-memory.sqlite3"
    store = MemoryGovernanceStore(database)
    with store._connection() as connection:
        store._ensure_content_shadow(connection, backfill=False)
    evidence_id = (
        EvidenceStore(database)
        .put(
            EvidenceInput(
                source_id="cursor",
                conversation_id="conversation",
                message_id="m1",
                correlation_id="m1",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="发布窗口是周五上午。",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            )
        )
        .record.evidence_id
    )
    return store, database, evidence_id


def test_a_recall_read_does_not_check_out_the_global_writer(tmp_path):
    store, database, evidence_id = _store(tmp_path)
    store.write_from_hy(
        HyCreate(
            draft=MemoryDraft(
                user_id="local",
                kind="schema",
                content="发布窗口是周五上午",
                scopes=("all-apps",),
                evidence_ids=(evidence_id,),
            ),
            request_id="r1",
            memory_id="m1",
        ),
        user_id="local",
        derivation=store.hy_derivation(),
    )
    db = main_database(database)
    # Warm once so any lazy one-time initialization is not attributed to the read.
    store.find_confirmed_matching_terms(user_id="local", terms=["发布"], limit=10)
    before = db.stats()
    store.find_confirmed_matching_terms(user_id="local", terms=["发布"], limit=10)
    after = db.stats()
    assert after.reader_checkouts - before.reader_checkouts >= 1
    assert after.writer_checkouts - before.writer_checkouts == 0, (
        "the recall read path must not take the single global writer"
    )


def test_a_missing_shadow_still_fails_closed_without_taking_the_writer(tmp_path):
    store, database, _evidence_id = _store(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE governed_memories_terms")
        connection.execute("DROP TABLE governed_memories_terms_meta")
    db = main_database(database)
    before = db.stats()
    with pytest.raises(Exception, match="governance_schema_missing"):
        store.find_confirmed_matching_terms(user_id="local", terms=["发布"], limit=10)
    after = db.stats()
    assert after.writer_checkouts - before.writer_checkouts == 0, (
        "a broken schema must fail closed on a read connection, not write"
    )
    with sqlite3.connect(database) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'governed_memories_terms%'"
            )
        }
    assert names == set(), "a read must not repair or recreate the shadow tables"
