import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from one_memory import ingest_journal
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.sources.registry import RootCandidateKind
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.config_state import ConfigStore
from one_memory.retrieval.chunking import TextChunk
from one_memory.retrieval.index_store import EncoderIdentity, RetrievalIndexStore
from one_memory.retrieval.models import TimeRange


@pytest.fixture
def fixture(tmp_path):
    path = tmp_path / "data.sqlite3"
    evidence = EvidenceStore(path)
    grants = SourceGrantStore(path, home=tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    grants.grant(
        user_id="local", source_id="codex", root=source, candidate_kind=RootCandidateKind.DEFAULT
    )
    store = RetrievalIndexStore(path)
    identity = EncoderIdentity("test", "a" * 64, "b" * 64, 3)
    return path, evidence, grants, store, identity


def put(evidence, text="original text", message="one"):
    return evidence.put(
        EvidenceInput(
            source_id="codex",
            conversation_id="thread",
            message_id=message,
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim=text,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record


def initialize(f):
    path, _, _, store, identity = f
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)
        return store.create_generation(db, identity)


def test_constructor_and_reads_do_not_create_database_or_schema(tmp_path):
    store = RetrievalIndexStore(tmp_path / "missing")
    assert not store.database_path.exists()
    with pytest.raises(sqlite3.Error):
        store.status("missing")
    assert not store.database_path.exists()


def test_explicit_initialization_rolls_back_and_never_grants_model_policy(fixture):
    path, evidence, _, store, _ = fixture
    row = put(evidence)
    with closing(sqlite3.connect(path)) as db:
        with pytest.raises(RuntimeError):
            store.initialize(db)
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)
        event = ingest_journal.current(db, row.evidence_id)
        assert not event.generation_eligible and event.kind == "migration_baseline"
        db.rollback()
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='retrieval_index_state'"
        ).fetchone()
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='evidence_ingest_events'"
        ).fetchone()
    initialize(fixture)
    with closing(sqlite3.connect(path)) as db:
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='continuous_policy_history'"
        ).fetchone()


def test_consumer_and_jobs_commit_together(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    with closing(sqlite3.connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        assert store.consume(db, generation) == 1
        assert db.execute("SELECT COUNT(*) FROM retrieval_documents").fetchone()[0] == 1
        db.rollback()
    assert store.status(generation)["after_seq"] == 0
    assert store.consume_pending(generation) == 1
    assert store.consume_pending(generation) == 0
    lease = store.claim(generation, "worker", now=100)
    assert lease.evidence_id == row.evidence_id


def test_lease_expiry_old_owner_and_publish_manifest(fixture):
    _, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "one", now=100, lease_seconds=10)
    assert store.claim(generation, "two", now=105) is None
    replacement = store.claim(generation, "two", now=111)
    chunks = (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),)
    with pytest.raises(ValueError, match="lease"):
        store.publish(lease, chunks, vectors_verified=True, now=112)
    with pytest.raises(ValueError, match="vectors"):
        store.publish(replacement, chunks, vectors_verified=False, now=112)
    store.publish(replacement, chunks, vectors_verified=True, now=112)
    assert store.status(generation)["ready"] == 1
    assert store.active_chunks(generation) == ()
    store.activate_generation(generation)
    assert len(store.active_chunks(generation)) == 1
    assert store.claim(generation, "three", now=113) is None


@pytest.mark.parametrize("change", ["revision", "unrecorded", "revoke", "deleted"])
def test_changed_inputs_cannot_publish_or_be_read(fixture, change):
    path, evidence, grants, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    if change == "revision":
        put(evidence, "updated text")
    elif change == "unrecorded":
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "UPDATE evidence SET verbatim='unrecorded' WHERE evidence_id=?", (row.evidence_id,)
            )
    elif change == "revoke":
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE source_grants SET revoked_at='2026-09-19' WHERE source_id='codex'")
    else:
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM evidence_origins WHERE evidence_id=?", (row.evidence_id,))
            db.execute("DELETE FROM evidence WHERE evidence_id=?", (row.evidence_id,))
            ingest_journal.record(db, row.evidence_id, cause="delete")
    with pytest.raises(ValueError):
        store.publish(
            lease,
            (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),),
            vectors_verified=True,
            now=101,
        )
    assert store.active_chunks(generation) == ()


def test_current_read_rejects_revised_published_content_before_consumer_catches_up(fixture):
    _, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    store.publish(
        lease,
        (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),),
        vectors_verified=True,
        now=101,
    )
    store.activate_generation(generation)
    assert store.active_chunks(generation)
    put(evidence, "new version")
    assert store.active_chunks(generation) == ()
    store.consume_pending(generation)
    updated = store.claim(generation, "worker", now=102)
    assert updated.build_id != lease.build_id


def test_pausing_harness_sync_does_not_hide_published_memory(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    store.publish(
        lease,
        (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),),
        vectors_verified=True,
        now=101,
    )
    store.activate_generation(generation)
    before = store.active_chunks(generation)
    assert before

    config = ConfigStore(path.parent)
    config.set_sync("codex", True)
    config.set_sync("codex", False)

    assert store.active_chunks(generation) == before


def test_partial_or_fabricated_chunk_manifest_never_publishes(fixture):
    _, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    for chunks in [
        (),
        (TextChunk(0, 0, 3, 3, "ori"),),
        (TextChunk(0, 0, len(row.verbatim), 4, "not original"),),
    ]:
        with pytest.raises(ValueError, match="chunk"):
            store.publish(lease, chunks, vectors_verified=True, now=101)
    assert store.status(generation)["ready"] == 0


def test_incomplete_index_cannot_replace_existing_active_generation(fixture):
    path, evidence, _, store, identity = fixture
    first = initialize(fixture)
    row = put(evidence)
    store.consume_pending(first)
    lease = store.claim(first, "worker", now=100)
    chunks = (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),)
    store.publish(lease, chunks, vectors_verified=True, now=101)
    store.activate_generation(first)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        second = store.create_generation(db, EncoderIdentity("second", "c" * 64, "d" * 64, 3))
    with pytest.raises(ValueError, match="caught_up"):
        store.activate_generation(second)
    assert store.active_chunks(first)
    store.consume_pending(second)
    with pytest.raises(ValueError, match="incomplete"):
        store.activate_generation(second)
    claim = store.claim(second, "worker", now=102)
    store.publish(claim, chunks, vectors_verified=True, now=103)
    store.activate_generation(second)
    assert store.active_chunks(first) == () and store.active_chunks(second)


def test_block_and_explicit_retry_require_same_lease_and_authority(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    put(evidence)
    store.consume_pending(generation)
    first = store.claim(generation, "one", now=100, lease_seconds=1)
    second = store.claim(generation, "two", now=102)
    store.block(first)
    assert store.status(generation)["leased"] == 1
    store.block(second)
    assert store.status(generation)["blocked"] == 1
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE source_grants SET revoked_at='revoked'")
    assert store.retry_blocked(generation) == 0
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE source_grants SET revoked_at=NULL")
    assert store.retry_blocked(generation) == 1
    assert store.claim(generation, "three", now=103) is not None


def test_scope_filter_and_revocation_apply_before_exposing_manifest(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    assert store.read_lease(lease, now=101).verbatim == row.verbatim
    store.publish(
        lease,
        (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),),
        vectors_verified=True,
        now=101,
    )
    store.activate_generation(generation)
    assert store.active_chunks(generation, source_ids=frozenset()) == ()
    assert store.active_chunks(generation, source_ids=frozenset({"codex"}))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE source_grants SET revision=revision+1")
    assert store.active_chunks(generation) == ()


def test_source_and_time_eligibility_are_applied_before_manifest_validation(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    chunks = (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),)
    store.publish(lease, chunks, vectors_verified=True, now=101)
    store.activate_generation(generation)

    assert store.active_chunks(generation, source_ids=frozenset()) == ()
    assert store.active_chunks(generation, source_ids=frozenset({"other"})) == ()
    assert len(store.active_chunks(generation, source_ids=frozenset({"codex"}))) == 1
    assert (
        store.active_chunks(
            generation,
            time_range=TimeRange(
                start=datetime(2030, 1, 1, tzinfo=UTC),
                end=datetime(2030, 1, 2, tzinfo=UTC),
            ),
        )
        == ()
    )


def test_generation_and_metadata_survive_reopen_without_body_copy(fixture):
    path, evidence, _, store, identity = fixture
    generation = initialize(fixture)
    put(evidence, "sensitive-body-must-not-copy")
    store.consume_pending(generation)
    reopened = RetrievalIndexStore(path)
    assert reopened.status(generation) == store.status(generation)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        reopened.initialize(db)
        assert reopened.create_generation(db, identity) == generation
        rows = db.execute("SELECT * FROM retrieval_documents").fetchall()
        assert "sensitive-body-must-not-copy" not in str(rows)


def test_partial_schema_is_not_blessed_as_new_instance(fixture):
    path, _, _, store, _ = fixture
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE retrieval_chunks (unexpected TEXT)")
    with closing(sqlite3.connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="partial_initialization"):
            store.initialize(db)
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='retrieval_index_state'"
        ).fetchone()


def test_lease_renewal_rechecks_authority_and_rejects_old_expiry(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    renewed = store.renew(lease, now=125)
    assert renewed.expires_at == 185
    with pytest.raises(ValueError, match="lease_changed"):
        store.read_lease(lease, now=126)
    assert store.read_lease(renewed, now=126)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE source_grants SET revision=revision+1")
    with pytest.raises(ValueError, match="authority"):
        store.renew(renewed, now=127)


def test_regrant_requeues_and_reuses_immutable_manifest(fixture):
    path, evidence, grants, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    chunks = (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),)
    store.publish(lease, chunks, vectors_verified=True, now=101)
    store.activate_generation(generation)
    assert len(store.active_chunks(generation)) == 1
    grants.revoke(user_id="local", source_id="codex")
    assert store.active_chunks(generation) == ()
    grants.grant(
        user_id="local",
        source_id="codex",
        root=path.parent / "source",
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    assert store.active_chunks(generation) == ()
    assert store.retry_blocked(generation) == 1
    renewed = store.claim(generation, "worker", now=102)
    assert renewed.build_id == lease.build_id
    store.publish(renewed, chunks, vectors_verified=True, now=103)
    assert len(store.active_chunks(generation)) == 1


def test_retry_cursor_passes_ineligible_prefix_across_reopen(fixture):
    path, evidence, grants, store, _ = fixture
    generation = initialize(fixture)
    for index in range(257):
        put(evidence, message=str(index))
    store.consume_pending(generation)
    store.consume_pending(generation)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE retrieval_documents SET state='blocked',source_id='revoked'")
        last_id = db.execute(
            "SELECT evidence_id FROM retrieval_documents ORDER BY event_seq DESC LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "UPDATE retrieval_documents SET source_id='codex' WHERE evidence_id=?", (last_id,)
        )
    assert store.retry_blocked(generation) == 0
    reopened = RetrievalIndexStore(path)
    assert reopened.retry_blocked(generation) == 1
    assert reopened.claim(generation, "worker", now=100).evidence_id == last_id


def test_same_build_replay_requires_exact_complete_manifest(fixture):
    path, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    row = put(evidence)
    store.consume_pending(generation)
    lease = store.claim(generation, "worker", now=100)
    chunks = (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),)
    store.publish(lease, chunks, vectors_verified=True, now=101)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE retrieval_documents SET state='pending',active_build_id=NULL")
    replay = store.claim(generation, "worker", now=102)
    with pytest.raises(ValueError, match="manifest"):
        store.publish(
            replay,
            (TextChunk(0, 0, len(row.verbatim), 5, row.verbatim),),
            vectors_verified=True,
            now=103,
        )
    assert store.status(generation)["ready"] == 0
    store.publish(replay, chunks, vectors_verified=True, now=103)
    assert store.status(generation)["ready"] == 1


def test_origin_metadata_roundtrip_reuses_old_build_without_losing_new_event(fixture):
    _, evidence, _, store, _ = fixture
    generation = initialize(fixture)
    builds = []
    seqs = []
    for version in ("a", "b", "a"):
        row = evidence.put(
            EvidenceInput(
                source_id="codex",
                conversation_id="thread",
                message_id="one",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="unchanged original",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata(source_version=version)},
            )
        ).record
        assert row.revision == 1
        assert store.consume_pending(generation) == 1
        lease = store.claim(generation, "worker", now=100)
        builds.append(lease.build_id)
        seqs.append(lease.event_seq)
        store.publish(
            lease,
            (TextChunk(0, 0, len(row.verbatim), 5, row.verbatim),),
            vectors_verified=True,
            now=101,
        )
    assert builds[0] == builds[2] and builds[0] != builds[1]
    assert seqs[0] < seqs[1] < seqs[2]
    store.activate_generation(generation)
    assert len(store.active_chunks(generation)) == 1
