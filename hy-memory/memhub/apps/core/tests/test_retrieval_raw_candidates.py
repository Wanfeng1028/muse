import sqlite3
import time
from contextlib import closing
from datetime import datetime

import pytest

from one_memory.imports.models import EvidenceInput
from one_memory.retrieval.index_worker import RetrievalIndexWorker
from one_memory.retrieval.models import TimeRange
from one_memory.retrieval.raw_candidates import (
    compose_raw_retrieval_path,
    read_raw_semantic_candidates,
)
from one_memory.retrieval.vector_store import RawVectorStore
from tests.test_retrieval_index_store import fixture, initialize, put  # noqa: F401
from tests.test_retrieval_index_worker import Encoder, forbid_network  # noqa: F401


@pytest.fixture
def indexed(fixture, tmp_path):  # noqa: F811
    generation = initialize(fixture)
    record = put(fixture[1])
    encoder = Encoder(fixture[4])
    vectors = RawVectorStore.create(tmp_path / "vectors", generation_id=generation, dimensions=3)
    worker = RetrievalIndexWorker(
        fixture[3], vectors, encoder, generation_id=generation, owner="test"
    )
    assert worker.run_once().state == "ready"
    fixture[3].activate_generation(generation)
    try:
        yield fixture, generation, record, vectors
    finally:
        vectors.close()


def search(indexed, **kwargs):
    f, generation, _, vectors = indexed
    options = dict(source_ids=frozenset({"codex"}), deadline=time.monotonic() + 10)
    options.update(kwargs)
    return read_raw_semantic_candidates(
        f[3], vectors, [1.0, 0.5, 0.25], generation_id=generation, **options
    )


def test_positive_only_current_authorized_published_chunks_are_searched(indexed):
    result = search(indexed)
    assert result.complete and len(result.hits) == 1
    assert result.hits[0].chunk.evidence_id == indexed[2].evidence_id
    assert result.coverage == "indexed_only"


def test_empty_authority_never_reads_database_or_vector(indexed, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized access")

    monkeypatch.setattr(indexed[0][3], "active_chunks", forbidden)
    monkeypatch.setattr(indexed[3], "search", forbidden)
    result = search(indexed, source_ids=frozenset())
    assert not result.hits and result.reason == "not_authorized"


def test_unapproved_source_never_enters_vector_query(indexed, monkeypatch):
    monkeypatch.setattr(indexed[3], "search", lambda *a, **k: pytest.fail("not eligible"))
    assert search(indexed, source_ids=frozenset({"cursor"})).hits == ()


@pytest.mark.parametrize("change", ["revoke", "revise", "policy"])
def test_mutation_during_vector_query_discards_stale_candidate(indexed, monkeypatch, change):
    f, _, _, vectors = indexed
    original = vectors.search

    def query(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == "revise":
            put(f[1], "changed text")
        elif change == "revoke":
            f[2].revoke(user_id="local", source_id="codex")
        else:
            with closing(sqlite3.connect(f[0])) as db, db:
                db.execute("UPDATE source_grants SET revision=revision+1")
        return result

    monkeypatch.setattr(vectors, "search", query)
    result = search(indexed)
    assert not result.hits and not result.complete and result.reason == "evidence_changed"


def test_expired_deadline_does_not_read_or_query(indexed, monkeypatch):
    monkeypatch.setattr(indexed[3], "search", lambda *a, **k: pytest.fail("late query"))
    result = search(indexed, deadline=time.monotonic() - 1)
    assert not result.hits and not result.complete and result.reason == "deadline"


def test_missing_published_vector_is_error_not_empty(indexed):
    indexed[3]._collection.delete(ids=[c.chunk_id for c in indexed[0][3].active_chunks(indexed[1])])
    result = search(indexed)
    assert not result.hits and not result.complete and result.reason == "vector_unavailable"


def test_small_allowlist_uses_query_as_integrity_check_without_duplicate_get(indexed, monkeypatch):
    monkeypatch.setattr(
        indexed[3],
        "verify_candidates",
        lambda *args, **kwargs: pytest.fail("small allowlist must not be read twice"),
    )
    result = search(indexed)
    assert result.complete and len(result.hits) == 1


def test_missing_event_time_never_matches_hard_range(indexed, monkeypatch):
    window = TimeRange(start="2026-09-18T00:00:00+08:00", end="2026-09-19T00:00:00+08:00")
    monkeypatch.setattr(indexed[3], "search", lambda *a, **k: pytest.fail("unknown event time"))
    assert search(indexed, time_range=window).hits == ()


@pytest.mark.parametrize("sources", [None, ["codex"], "codex"])
def test_caller_must_provide_explicit_resolved_authority(indexed, sources):
    with pytest.raises(ValueError, match="source"):
        search(indexed, source_ids=sources)


def test_event_time_uses_utc_half_open_range_not_import_time(indexed):
    f, generation, record, vectors = indexed
    f[1].put(
        EvidenceInput(
            source_id=record.source_id,
            conversation_id=record.conversation_id,
            message_id=record.message_id,
            role=record.role,
            written_by=record.written_by,
            verbatim=record.verbatim,
            created_at=datetime.fromisoformat("2026-09-18T16:00:00+00:00"),
            origin_meta=record.origin_meta,
        )
    )
    worker = RetrievalIndexWorker(
        f[3], vectors, Encoder(f[4]), generation_id=generation, owner="test"
    )
    assert worker.run_once().state == "ready"
    before = TimeRange(start="2026-09-18T00:00:00+08:00", end="2026-09-19T00:00:00+08:00")
    after = TimeRange(start="2026-09-19T00:00:00+08:00", end="2026-09-20T00:00:00+08:00")
    assert not search(indexed, time_range=before).hits
    result = search(indexed, time_range=after)
    assert result.complete and len(result.hits) == 1
    assert result.hits[0].chunk.event_time == after.start


def test_final_deadline_failure_discards_previously_found_hits(indexed, monkeypatch):
    from one_memory.retrieval import raw_candidates

    original = raw_candidates._check
    calls = []

    def check(deadline):
        calls.append(deadline)
        if len(calls) == 3:
            raise TimeoutError("late final revalidation")
        return original(deadline)

    monkeypatch.setattr(raw_candidates, "_check", check)
    result = search(indexed)
    assert len(calls) == 3 and not result.hits and result.reason == "deadline"


@pytest.mark.parametrize("corruption", ["all_missing", "tail_missing", "offset", "hash"])
def test_corrupted_published_manifest_is_unavailable_not_complete_empty(indexed, corruption):
    f, generation, _, vectors = indexed
    put(f[1], "long source text " * 90)
    worker = RetrievalIndexWorker(
        f[3], vectors, Encoder(f[4]), generation_id=generation, owner="test"
    )
    assert worker.run_once().state == "ready"
    assert len(search(indexed).hits) > 1
    with closing(sqlite3.connect(f[0])) as db, db:
        if corruption == "all_missing":
            db.execute("DELETE FROM retrieval_chunks")
        elif corruption == "tail_missing":
            db.execute("DELETE FROM retrieval_chunks WHERE ordinal>0")
        elif corruption == "offset":
            db.execute("UPDATE retrieval_chunks SET start_cp=3 WHERE ordinal=0")
        else:
            db.execute("UPDATE retrieval_chunks SET text_hash='broken'")
    result = search(indexed)
    assert not result.complete and not result.hits and result.reason == "index_unavailable"


def test_null_stored_grant_with_revocation_never_queries_vectors(indexed, monkeypatch):
    f, _, _, vectors = indexed
    assert search(indexed).hits
    with closing(sqlite3.connect(f[0])) as db, db:
        db.execute("UPDATE retrieval_documents SET grant_fingerprint=NULL")
    f[2].revoke(user_id="local", source_id="codex")
    monkeypatch.setattr(vectors, "search", lambda *a, **k: pytest.fail("revoked vector query"))
    assert not search(indexed).hits


def test_unpublished_authorized_evidence_cannot_claim_complete_empty(indexed):
    """A partial index with no hits is incomplete, not an honest empty library."""
    f, generation, _, _vectors = indexed
    put(f[1], "用户决定 One Memory 采用 MIT 协议发布。", message="unindexed")
    assert f[3].consume_pending(generation) >= 1
    pending = f[3].status(generation)
    assert pending["pending"] >= 1
    # Published chunks may still match a probe vector. The unpublished
    # authorized document is what forbids complete-empty, so the candidate
    # batch is forced empty: that is the lying-empty case, not a miss on
    # already-indexed text.
    empty = type(search(indexed))(hits=(), complete=True, reason="no_eligible_chunks")
    path = compose_raw_retrieval_path(
        empty, unpublished_authorized=pending["pending"] > 0, lexical_hit_count=0
    )
    assert path.coverage == "partial"
    assert path.status != "empty"
    assert "semantic" in path.searched_channels


def test_complete_index_with_no_hits_may_be_empty(indexed):
    batch = search(indexed, source_ids=frozenset({"codex"}))
    # Query vector still matches the only indexed chunk; force a no-hit batch.
    empty = type(batch)(hits=(), complete=True, reason="no_eligible_chunks")
    path = compose_raw_retrieval_path(empty, unpublished_authorized=False, lexical_hit_count=0)
    assert path.status == "empty"
    assert path.coverage == "complete"
