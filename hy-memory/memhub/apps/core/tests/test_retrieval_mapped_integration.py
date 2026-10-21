import socket
import sqlite3
import time
from contextlib import closing
from dataclasses import replace

import pytest

from one_memory.retrieval.chunking import TextChunk
from one_memory.retrieval.index_store import RetrievalIndexStore
from one_memory.retrieval.index_worker import RetrievalIndexWorker
from one_memory.retrieval.mapped_content import chunk_mapped_content, prepare_mapped_content
from one_memory.retrieval.raw_candidates import read_raw_semantic_candidates
from one_memory.retrieval.raw_evidence import materialize_raw_candidates
from one_memory.retrieval.vector_store import RawVectorStore
from tests.test_retrieval_index_store import fixture, initialize, put  # noqa: F401
from tests.test_retrieval_index_worker import Encoder


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no network permitted")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(socket.socket, "connect_ex", fail)


def migrate(f):
    initialize(f)
    identity = replace(f[4], normalizer_version=2, chunker_version=2)
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("BEGIN IMMEDIATE")
        f[3].migrate_v2(db)
        generation = f[3].create_generation(db, identity)
    return generation, identity


@pytest.fixture
def mapped_setup(fixture, tmp_path):  # noqa: F811
    generation, identity = migrate(fixture)
    encoder = Encoder(identity)
    vectors = RawVectorStore.create(
        tmp_path / "mapped-vectors", generation_id=generation, dimensions=3
    )
    worker = RetrievalIndexWorker(
        fixture[3], vectors, encoder, generation_id=generation, owner="mapped"
    )
    try:
        yield fixture, generation, encoder, vectors, worker
    finally:
        vectors.close()


def candidates(f, generation, vectors):
    return read_raw_semantic_candidates(
        f[3],
        vectors,
        [1.0, 0.5, 0.25],
        generation_id=generation,
        source_ids=frozenset({"codex"}),
        deadline=time.monotonic() + 10,
    )


def materialize(f, generation, hits):
    return materialize_raw_candidates(
        f[3],
        hits,
        generation_id=generation,
        source_ids=frozenset({"codex"}),
        deadline=time.monotonic() + 10,
    )


def test_empty_materialization_rechecks_excluded_map(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "token=private-value")
    assert worker.run_once().state == "excluded"
    f[3].activate_generation(generation)
    empty = candidates(f, generation, vectors)
    assert empty.complete and not empty.hits
    assert materialize(f, generation, empty).complete
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("DELETE FROM retrieval_build_maps")
    assert not materialize(f, generation, empty).complete


def test_completed_excluded_missing_active_binding_is_not_empty_success(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "token=private-value")
    assert worker.run_once().state == "excluded"
    f[3].activate_generation(generation)
    assert candidates(f, generation, vectors).complete
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("UPDATE retrieval_documents SET active_build_id=NULL")
    result = candidates(f, generation, vectors)
    assert not result.complete and result.reason == "index_unavailable"


def test_old_empty_completion_is_invalidated_when_a_new_indexed_record_arrives(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "token=private-value")
    assert worker.run_once().state == "excluded"
    f[3].activate_generation(generation)
    empty = candidates(f, generation, vectors)
    assert empty.complete and not empty.hits
    put(f[1], "new actual content", message="new")
    assert worker.run_once().state == "ready"
    result = materialize(f, generation, empty)
    assert not result.complete and result.reason == "evidence_changed"


def test_schema2_roundtrip_only_encodes_copy_and_separates_original_spans(mapped_setup):
    f, generation, encoder, vectors, worker = mapped_setup
    original = (
        "<rules>private wrapper</rules><user_query>before token=private-value after</user_query>"
    )
    record = put(f[1], original)
    result = worker.run_once()
    assert result.state == "ready" and result.chunk_count == 2
    assert encoder.calls == [["before ", " after"]]
    f[3].activate_generation(generation)
    hits = candidates(f, generation, vectors)
    assert hits.complete and len(hits.hits) == 2
    output = materialize(f, generation, hits)
    assert output.complete and len(output.items) == 1
    assert [s.text for s in output.items[0].spans] == ["before ", " after"]
    assert all(original[s.start_cp : s.end_cp] == s.text for s in output.items[0].spans)
    with closing(sqlite3.connect(f[0])) as db:
        rows = db.execute(
            "SELECT source_map_json,map_digest,coverage_state FROM retrieval_build_maps"
        ).fetchall()
        assert len(rows) == 1 and rows[0][2] == "indexable"
        assert "before" not in rows[0][0] and "private" not in rows[0][0]
        assert rows[0][1] == prepare_mapped_content(record).metadata.digest
    assert RetrievalIndexStore(f[0]).active_chunks(generation)


def test_explicit_migration_rolls_back_and_v1_remains_readable(fixture):  # noqa: F811
    f = fixture
    generation = initialize(f)
    row = put(f[1], "legacy text")
    f[3].consume_pending(generation)
    lease = f[3].claim(generation, "legacy")
    f[3].publish(
        lease, (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),), vectors_verified=True
    )
    f[3].activate_generation(generation)
    before = f[3].active_chunks(generation)
    with closing(sqlite3.connect(f[0])) as db:
        with pytest.raises(RuntimeError):
            f[3].migrate_v2(db)
        db.execute("BEGIN IMMEDIATE")
        f[3].migrate_v2(db)
        db.rollback()
        assert db.execute("SELECT schema_version FROM retrieval_index_state").fetchone()[0] == 1
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='retrieval_build_maps'"
        ).fetchone()
    assert f[3].active_chunks(generation) == before
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("BEGIN IMMEDIATE")
        f[3].migrate_v2(db)
        f[3].migrate_v2(db)
    assert f[3].active_chunks(generation) == before
    from one_memory.retrieval.raw_candidates import RawCandidateBatch, RawSemanticCandidate

    output = materialize(
        f, generation, RawCandidateBatch(tuple(RawSemanticCandidate(c, 0.0) for c in before), True)
    )
    assert output.complete and output.items[0].spans[0].text == "legacy text"


def test_version2_requires_explicit_schema_upgrade(fixture):  # noqa: F811
    f = fixture
    initialize(f)
    with closing(sqlite3.connect(f[0])) as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="schema"):
            f[3].create_generation(db, replace(f[4], normalizer_version=2, chunker_version=2))
        assert db.execute("SELECT schema_version FROM retrieval_index_state").fetchone()[0] == 1


@pytest.mark.parametrize("text", ["token=private", "<rules>only wrapper</rules>"])
def test_excluded_completion_has_no_vectors_and_is_not_ready(mapped_setup, text):
    f, generation, encoder, vectors, worker = mapped_setup
    put(f[1], text)
    result = worker.run_once()
    assert result.state == "excluded" and result.chunk_count == 0
    assert encoder.calls == []
    assert f[3].status(generation)["excluded"] == 1
    assert f[3].status(generation)["ready"] == 0
    f[3].activate_generation(generation)
    assert candidates(f, generation, vectors).hits == ()


@pytest.mark.parametrize("tamper", ["json", "digest", "offset", "missing_map", "missing_chunk"])
def test_persisted_tampering_rejected_at_candidate_and_final_read(mapped_setup, tamper):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "before token=private after")
    assert worker.run_once().state == "ready"
    f[3].activate_generation(generation)
    hits = candidates(f, generation, vectors)
    with closing(sqlite3.connect(f[0])) as db, db:
        if tamper == "json":
            db.execute("UPDATE retrieval_build_maps SET source_map_json='{}'")
        elif tamper == "digest":
            db.execute("UPDATE retrieval_build_maps SET map_digest=?", ("0" * 64,))
        elif tamper == "offset":
            db.execute("UPDATE retrieval_chunks SET end_cp=end_cp+1 WHERE ordinal=0")
        elif tamper == "missing_map":
            db.execute("DELETE FROM retrieval_build_maps")
        else:
            db.execute("DELETE FROM retrieval_chunks WHERE ordinal=1")
    assert not candidates(f, generation, vectors).complete
    final = materialize(f, generation, hits)
    assert not final.complete and not final.items


@pytest.mark.parametrize("change", ["secret", "revoke", "policy"])
def test_current_source_secret_revision_and_grant_changes_invalidate_hits(mapped_setup, change):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "before token=private-one after")
    assert worker.run_once().state == "ready"
    f[3].activate_generation(generation)
    hits = candidates(f, generation, vectors)
    if change == "secret":
        put(f[1], "before token=private-two after")
    else:
        with closing(sqlite3.connect(f[0])) as db, db:
            db.execute(
                "UPDATE source_grants SET revoked_at='revoked'"
                if change == "revoke"
                else "UPDATE source_grants SET revision=revision+1"
            )
    assert not materialize(f, generation, hits).items
    assert not f[3].active_chunks(generation)


def test_publish_recomputes_map_and_rejects_cross_gap_or_incomplete_manifest(mapped_setup):
    f, generation, encoder, _, _ = mapped_setup
    row = put(f[1], "before token=private after")
    f[3].consume_pending(generation)
    lease = f[3].claim(generation, "publisher")
    prepared = prepare_mapped_content(row)
    chunks = chunk_mapped_content(prepared, encoder)
    for bad in [chunks[:1], (TextChunk(0, 0, len(row.verbatim), 10, row.verbatim),)]:
        with pytest.raises(ValueError, match="manifest"):
            f[3].publish(lease, bad, vectors_verified=True, source_map=prepared.metadata)
    with pytest.raises(ValueError, match="map"):
        f[3].publish(
            lease,
            chunks,
            vectors_verified=True,
            source_map=replace(prepared.metadata, sanitized_sha256="0" * 64),
        )
    assert f[3].status(generation)["ready"] == 0


def test_many_copy_regions_remain_partial_not_a_cross_gap_quote(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], " token=private ".join([f"part-{i}" for i in range(6)]))
    assert worker.run_once().chunk_count == 6
    f[3].activate_generation(generation)
    final = materialize(f, generation, candidates(f, generation, vectors))
    assert not final.complete and len(final.items[0].spans) == 4
    assert all("token=" not in s.text for s in final.items[0].spans)


def test_local_onnx_chroma_mapped_roundtrip_without_download(fixture, tmp_path):  # noqa: F811
    from one_memory.retrieval.index_worker import LocalRetrievalEncoder

    f = fixture
    encoder = LocalRetrievalEncoder()
    assert encoder.identity.normalizer_version == encoder.identity.chunker_version == 2
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("BEGIN IMMEDIATE")
        f[3].initialize(db)
        f[3].migrate_v2(db)
        generation = f[3].create_generation(db, encoder.identity)
    row = put(
        f[1],
        "<user_query>\u4e2d\u6587\U0001f680e\u0301\n"
        + "\u524d\u6587" * 300
        + " token=private-value "
        + "\u540e\u6587" * 300
        + "</user_query>",
    )
    vectors = RawVectorStore.create(
        tmp_path / "native-mapped", generation_id=generation, dimensions=encoder.identity.dimensions
    )
    try:
        worker = RetrievalIndexWorker(
            f[3], vectors, encoder, generation_id=generation, owner="local"
        )
        result = worker.run_once()
        assert result.state == "ready" and result.chunk_count >= 4
        f[3].activate_generation(generation)
        hits = read_raw_semantic_candidates(
            f[3],
            vectors,
            encoder.encode_documents(["\u540e\u6587"])[0],
            generation_id=generation,
            source_ids=frozenset({"codex"}),
            deadline=time.monotonic() + 15,
        )
        final = materialize(f, generation, hits)
        assert final.complete and len(final.items[0].spans) == 2
        for span in final.items[0].spans:
            assert span.text == row.verbatim[span.start_cp : span.end_cp]
            assert "private-value" not in span.text and "redacted-secret" not in span.text
    finally:
        vectors.close()


@pytest.mark.parametrize(
    "text",
    [
        "<user_query>one</user_query><user_query>two</user_query>",
        "<dynamic_tool_catalog>generated</dynamic_tool_catalog>",
    ],
)
def test_ambiguous_generated_stay_blocked(mapped_setup, text):
    f, generation, encoder, _, worker = mapped_setup
    put(f[1], text)
    assert worker.run_once().state == "blocked"
    assert not encoder.calls
    with pytest.raises(ValueError, match="incomplete"):
        f[3].activate_generation(generation)


@pytest.mark.parametrize("change", ["revoke", "secret"])
def test_change_during_encoding_never_publishes(mapped_setup, change):
    f, generation, encoder, _, worker = mapped_setup
    put(f[1], "before token=private-one after")
    original = encoder.encode_documents

    def changed(texts):
        result = original(texts)
        if change == "secret":
            put(f[1], "before token=private-two after")
        else:
            f[2].revoke(user_id="local", source_id="codex")
        return result

    encoder.encode_documents = changed
    assert worker.run_once().state == "blocked"
    assert f[3].status(generation)["ready"] == 0
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute("SELECT * FROM retrieval_build_maps").fetchall()


def test_cancellation_inside_publish_rolls_back_map_chunks_and_completion(
    mapped_setup, monkeypatch
):
    import threading

    f, generation, _, _, worker = mapped_setup
    put(f[1], "before token=private after")
    cancel = threading.Event()
    original = f[3]._prepare

    def cancelled(*args):
        prepared = original(*args)
        cancel.set()
        return prepared

    monkeypatch.setattr(f[3], "_prepare", cancelled)
    assert worker.run_once(cancel=cancel).state == "cancelled"
    assert f[3].status(generation)["leased"] == 1
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute("SELECT * FROM retrieval_build_maps").fetchall()
        assert not db.execute("SELECT * FROM retrieval_chunks").fetchall()


def test_excluded_metadata_is_validated_on_activation_and_candidate_read(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "token=private")
    assert worker.run_once().state == "excluded"
    f[3].activate_generation(generation)
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("DELETE FROM retrieval_build_maps")
    assert not candidates(f, generation, vectors).complete
    with pytest.raises(ValueError, match="map"):
        f[3].activate_generation(generation)


def test_migration_preserves_an_existing_v1_lease_and_store_identity(fixture):  # noqa: F811
    f = fixture
    generation = initialize(f)
    row = put(f[1], "legacy leased")
    f[3].consume_pending(generation)
    lease = f[3].claim(generation, "legacy")
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("BEGIN IMMEDIATE")
        f[3].migrate_v2(db)
    assert f[3].read_lease(lease) == row
    f[3].publish(
        lease, (TextChunk(0, 0, len(row.verbatim), 4, row.verbatim),), vectors_verified=True
    )
    f[3].activate_generation(generation)
    assert f[3].active_chunks(generation)


def test_bad_token_offsets_leave_no_partial_mapped_manifest(mapped_setup):
    from one_memory.local_embedding import TokenizedText, TokenOffset

    f, generation, encoder, _, worker = mapped_setup
    put(f[1], "before token=private after")
    encoder.tokenize_with_offsets = lambda text: TokenizedText((1,), (TokenOffset(0, 1),))
    assert worker.run_once().state == "blocked"
    assert not encoder.calls
    assert f[3].status(generation)["ready"] == 0


def test_failed_migration_keeps_original_table_lease_and_schema(fixture):  # noqa: F811
    f = fixture
    generation = initialize(f)
    put(f[1], "preserved")
    f[3].consume_pending(generation)
    lease = f[3].claim(generation, "legacy")
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("CREATE TABLE retrieval_build_maps (foreign_value TEXT)")
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.Error):
            f[3].migrate_v2(db)
        assert db.execute("SELECT schema_version FROM retrieval_index_state").fetchone()[0] == 1
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='retrieval_documents_v2'"
        ).fetchone()
    assert f[3].read_lease(lease).verbatim == "preserved"


@pytest.mark.parametrize(
    "text,expected", [("before token=private after", "ready"), ("token=private", "excluded")]
)
def test_regrant_reuses_immutable_map_and_manifest_only_after_explicit_retry(
    mapped_setup, text, expected
):
    from one_memory.imports.sources.registry import RootCandidateKind

    f, generation, _, _, worker = mapped_setup
    put(f[1], text)
    assert worker.run_once().state == expected
    f[3].activate_generation(generation)
    with closing(sqlite3.connect(f[0])) as db:
        original = db.execute("SELECT * FROM retrieval_build_maps").fetchall()
    f[2].revoke(user_id="local", source_id="codex")
    assert not f[3].active_chunks(generation)
    f[2].grant(
        user_id="local",
        source_id="codex",
        root=f[0].parent / "source",
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    assert not f[3].active_chunks(generation)
    assert f[3].retry_blocked(generation) == 1
    assert worker.run_once().state == expected
    with closing(sqlite3.connect(f[0])) as db:
        assert db.execute("SELECT * FROM retrieval_build_maps").fetchall() == original


def test_map_replay_conflict_rolls_back_new_chunks(mapped_setup):
    f, generation, encoder, _, _ = mapped_setup
    row = put(f[1], "before token=private after")
    f[3].consume_pending(generation)
    lease = f[3].claim(generation, "publisher")
    prepared = prepare_mapped_content(row)
    chunks = chunk_mapped_content(prepared, encoder)
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute(
            "INSERT INTO retrieval_build_maps VALUES (?,?,?,?)",
            (lease.build_id, "{}", "0" * 64, "indexable"),
        )
    with pytest.raises(ValueError, match="immutable_source_map"):
        f[3].publish(lease, chunks, vectors_verified=True, source_map=prepared.metadata)
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute("SELECT * FROM retrieval_chunks").fetchall()
    assert f[3].status(generation)["leased"] == 1


def test_deadline_expiring_during_publish_rolls_back_completion(mapped_setup, monkeypatch):
    f, generation, _, _, worker = mapped_setup
    put(f[1], "before token=private after")
    current = [0.0]
    worker.clock = lambda: current[0]
    worker.max_job_seconds = 10
    original = f[3]._prepare

    def expires(*args):
        result = original(*args)
        current[0] = 11
        return result

    monkeypatch.setattr(f[3], "_prepare", expires)
    result = worker.run_once()
    assert result.state == "deferred" and result.reason == "deadline"
    assert f[3].status(generation)["leased"] == 1
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute("SELECT * FROM retrieval_chunks").fetchall()
        assert not db.execute("SELECT * FROM retrieval_build_maps").fetchall()


def test_deadline_and_character_budget_never_release_cross_gap_spans(mapped_setup):
    f, generation, _, vectors, worker = mapped_setup
    put(f[1], "before token=private after")
    assert worker.run_once().state == "ready"
    f[3].activate_generation(generation)
    hits = candidates(f, generation, vectors)
    expired = materialize_raw_candidates(
        f[3],
        hits,
        generation_id=generation,
        source_ids=frozenset({"codex"}),
        deadline=time.monotonic() - 1,
    )
    assert not expired.items and expired.reason == "deadline"
    bounded = materialize_raw_candidates(
        f[3],
        hits,
        generation_id=generation,
        source_ids=frozenset({"codex"}),
        deadline=time.monotonic() + 10,
        character_budget=7,
    )
    assert not bounded.complete and bounded.reason == "character_budget"
    assert bounded.used_characters <= 7
    assert sum(len(item.spans) for item in bounded.items) == 1


def test_lease_expiring_inside_publish_cannot_commit(mapped_setup, monkeypatch):
    f, generation, _, _, worker = mapped_setup
    put(f[1], "before token=private after")
    current = [100.0]
    worker.wall_clock = lambda: current[0]
    original = f[3]._prepare

    def expires(*args):
        result = original(*args)
        current[0] = 1000.0
        return result

    monkeypatch.setattr(f[3], "_prepare", expires)
    assert worker.run_once().state == "blocked"
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute("SELECT * FROM retrieval_chunks").fetchall()
        assert not db.execute("SELECT * FROM retrieval_build_maps").fetchall()
    assert f[3].status(generation)["ready"] == 0
