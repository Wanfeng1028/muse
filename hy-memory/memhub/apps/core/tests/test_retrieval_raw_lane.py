"""v1 raw lane must not claim complete empty when the derived index is partial."""

import asyncio
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from one_memory.context_models import ContextLaneResult, ContextSearchRequest
from one_memory.context_raw import read_raw_context
from one_memory.database_access import main_database
from one_memory.embedding_assets import assets_present
from one_memory.retrieval.raw_candidates import RawCandidateBatch
from one_memory.retrieval.raw_lane import fuse_raw_lane, read_raw_indexed_context
from tests.test_context_raw import database as database  # noqa: F401
from tests.test_context_raw import put


def _require_assets() -> None:
    """Make an absent local fixture explicit instead of a lease-style hang."""
    if not assets_present():
        pytest.skip("_assets_unavailable")


def test_unpublished_authorized_evidence_degrades_empty_lexical_lane():
    lexical = ContextLaneResult(status="empty", reason="lexical_only")
    result = fuse_raw_lane(
        lexical,
        RawCandidateBatch(complete=True, reason="no_eligible_chunks"),
        unpublished_authorized=True,
    )
    assert result.status == "degraded"
    assert result.reason == "lexical_only"
    assert result.items == ()


def test_complete_index_with_no_hits_stays_empty():
    lexical = ContextLaneResult(status="empty", reason="lexical_only")
    result = fuse_raw_lane(
        lexical,
        RawCandidateBatch(complete=True, reason="no_eligible_chunks"),
        unpublished_authorized=False,
    )
    assert result.status == "empty"
    assert result.items == ()


def test_interactive_raw_lane_reads_one_snapshot_while_a_writer_holds(database):
    """The read lane must not wait for an import writer, nor see its uncommitted row.

    This is the C4-owned half of the import-contention BLOCK: WAL readers are
    expected to proceed from the last committed snapshot even while the single
    writer holds a transaction. A regression that lets context reads block on
    the writer - or read its uncommitted row - makes this fail.
    """
    with sqlite3.connect(database) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        put(db, "committed", "needle committed row")
    writer_holds = threading.Event()
    release_writer = threading.Event()

    def hold_write_transaction() -> None:
        with main_database(database).write(autocommit=True) as writer:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                """INSERT INTO evidence
                (evidence_id,idempotency_key,user_id,source_id,conversation_id,role,
                 written_by,created_at,verbatim,content_hash,revision,imported_at,updated_at)
                VALUES ('uncommitted','uncommitted','local','cursor','c','user',
                        'person','2026-09-20','needle uncommitted row','synthetic',
                        1,'2026-09-20','2026-09-20')"""
            )
            writer_holds.set()
            assert release_writer.wait(5)
            writer.execute("ROLLBACK")

    thread = threading.Thread(target=hold_write_transaction)
    thread.start()
    assert writer_holds.wait(5)
    try:
        before = main_database(database).stats()
        started = time.monotonic()
        result = read_raw_context(
            database,
            ContextSearchRequest(query="needle", kinds=("raw",)),
            source_ids=frozenset({"cursor"}),
            deadline=time.monotonic() + 2,
        )
        elapsed = time.monotonic() - started
        after = main_database(database).stats()
    finally:
        release_writer.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert elapsed < 1.0
    assert after.reader_waits == before.reader_waits
    assert [item.anchor_evidence_id for item in result.items] == ["committed"]
    assert all(
        message.evidence_id != "uncommitted" for item in result.items for message in item.messages
    )


def test_authorization_and_unavailability_are_not_rewritten():
    denied = ContextLaneResult(status="not_authorized", reason="permission_required")
    assert (
        fuse_raw_lane(denied, RawCandidateBatch(), unpublished_authorized=True).status
        == "not_authorized"
    )
    missing = ContextLaneResult(status="unavailable", reason="read_unavailable")
    assert fuse_raw_lane(missing, RawCandidateBatch(), unpublished_authorized=True).status == (
        "unavailable"
    )


def test_indexed_reader_without_runtime_matches_lexical_empty(database):
    with sqlite3.connect(database) as db, db:
        put(db, "e-unrelated", "alpha transcript only")
    request = ContextSearchRequest(query="no-matching-zzzzzz", kinds=("raw",))
    deadline = time.monotonic() + 5
    lexical = read_raw_context(
        database, request, source_ids=frozenset({"cursor"}), deadline=deadline
    )
    indexed = read_raw_indexed_context(
        database, request, source_ids=frozenset({"cursor"}), deadline=deadline, index=None
    )
    assert lexical.status == "empty"
    assert indexed == lexical
    assert indexed.searched_channels == ("lexical",)
    assert indexed.semantic_status == "not_searched"
    assert indexed.index_complete is False


def test_indexed_reader_with_unpublished_index_is_not_empty(database):
    with sqlite3.connect(database) as db, db:
        put(db, "e-unrelated", "alpha transcript only")
    request = ContextSearchRequest(query="no-matching-zzzzzz", kinds=("raw",))
    index = SimpleNamespace(
        lookup_raw=lambda query, *, source_ids, deadline: (
            RawCandidateBatch(complete=True, reason="no_eligible_chunks"),
            True,
        )
    )
    result = read_raw_indexed_context(
        database,
        request,
        source_ids=frozenset({"cursor"}),
        deadline=time.monotonic() + 5,
        index=index,
    )
    assert result.status == "degraded"
    assert result.items == ()
    assert result.searched_channels == ("lexical", "semantic")
    assert result.semantic_status == "completed"
    assert result.index_complete is False


def test_semantic_hit_without_lexical_overlap_is_not_released(database):
    from datetime import UTC, datetime

    from one_memory.retrieval.index_store import PublishedChunk
    from one_memory.retrieval.raw_candidates import RawSemanticCandidate

    with sqlite3.connect(database) as db, db:
        put(db, "e-mit", "用户决定 One Memory 采用 MIT 协议发布。")
    chunk = PublishedChunk(
        chunk_id="c1",
        build_id="b1",
        evidence_id="e-mit",
        revision=1,
        start_cp=0,
        end_cp=8,
        ordinal=0,
        source_id="cursor",
        event_time=datetime(2026, 9, 19, tzinfo=UTC),
    )
    index = SimpleNamespace(
        lookup_raw=lambda query, *, source_ids, deadline: (
            RawCandidateBatch(
                hits=(RawSemanticCandidate(chunk, 0.1),),
                complete=True,
            ),
            False,
        )
    )
    result = read_raw_indexed_context(
        database,
        ContextSearchRequest(query="开源许可证怎么选", kinds=("raw",)),
        source_ids=frozenset({"cursor"}),
        deadline=time.monotonic() + 5,
        index=index,
    )
    assert result.status == "degraded"
    assert result.reason == "lexical_only"
    assert result.items == ()
    assert result.searched_channels == ("lexical", "semantic")
    assert result.semantic_status == "completed"
    assert result.index_complete is True


def test_semantic_candidate_with_lexical_corroboration_is_released(database):
    from datetime import UTC, datetime

    from one_memory.retrieval.index_store import PublishedChunk
    from one_memory.retrieval.raw_candidates import RawSemanticCandidate

    with sqlite3.connect(database) as db, db:
        put(db, "e-mit", "用户决定 One Memory 采用 MIT 协议发布。")
    chunk = PublishedChunk(
        chunk_id="c1",
        build_id="b1",
        evidence_id="e-mit",
        revision=1,
        start_cp=0,
        end_cp=8,
        ordinal=0,
        source_id="cursor",
        event_time=datetime(2026, 9, 19, tzinfo=UTC),
    )
    index = SimpleNamespace(
        lookup_raw=lambda query, *, source_ids, deadline: (
            RawCandidateBatch(
                hits=(RawSemanticCandidate(chunk, 0.1),),
                complete=True,
            ),
            False,
        )
    )
    result = read_raw_indexed_context(
        database,
        ContextSearchRequest(query="MIT 协议", kinds=("raw",)),
        source_ids=frozenset({"cursor"}),
        deadline=time.monotonic() + 5,
        index=index,
    )
    assert result.status == "ok"
    assert [item.anchor_evidence_id for item in result.items] == ["e-mit"]


def test_raw_semantic_timeout_is_not_reported_as_complete_empty(database):
    with sqlite3.connect(database) as db, db:
        put(db, "e-unrelated", "alpha transcript only")
    index = SimpleNamespace(
        lookup_raw=lambda query, *, source_ids, deadline: (
            RawCandidateBatch(reason="deadline"),
            False,
        )
    )
    result = read_raw_indexed_context(
        database,
        ContextSearchRequest(query="no-matching-zzzzzz", kinds=("raw",)),
        source_ids=frozenset({"cursor"}),
        deadline=time.monotonic() + 5,
        index=index,
    )
    assert result.status == "degraded"
    assert result.semantic_status == "timed_out"
    assert result.index_complete is False
    assert result.timed_out


def test_real_built_index_semantic_only_hit_is_not_released_without_confirmation(tmp_path):
    """The whole chain for real: ONNX encode, Chroma, published chunks, authority.

    Every other test here hands the lane a hand-written candidate, so none of
    them can tell whether a real build would ever produce one. The query is
    chosen to share no term with the stored sentence, and the lexical-only read
    is asserted empty first, so an `ok` here can only have come from the index.
    """
    _require_assets()
    from one_memory.imports.grants import SourceGrantStore
    from one_memory.imports.sources.registry import RootCandidateKind
    from one_memory.retrieval.runtime import ExistingRetrievalRuntime
    from tests.test_retrieval_index_store import put as put_evidence
    from tests.test_retrieval_runtime import configured, until

    store, evidence, generation = configured(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    SourceGrantStore(store.database_path, home=tmp_path).grant(
        user_id="local",
        source_id="codex",
        root=source,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    put_evidence(evidence, "我们最后决定 One Memory 用 MIT 协议发布。")
    request = ContextSearchRequest(query="开源软件的授权条款如何挑选", kinds=("raw",))
    sources = frozenset({"codex"})

    lexical = read_raw_context(
        store.database_path, request, source_ids=sources, deadline=time.monotonic() + 5
    )
    assert lexical.status == "empty", "词法已经命中，这条测试证明不了语义"

    async def scenario():
        handle = ExistingRetrievalRuntime(tmp_path, minimum_free_bytes=0)
        assert await handle.start()
        try:
            await until(lambda: store.status(generation)["ready"] >= 1)
            return await asyncio.to_thread(
                read_raw_indexed_context,
                store.database_path,
                request,
                source_ids=sources,
                deadline=time.monotonic() + 10,
                index=handle,
            )
        finally:
            await handle.stop()

    result = asyncio.run(scenario())
    # The semantic lane found the row, but lexical-only evidence is not enough
    # confirmation to release it to a host. Keep the candidate visible as a
    # degraded coverage receipt until a relevance/corroboration gate exists.
    assert result.status == "degraded"
    assert result.reason == "lexical_only"
    assert result.items == ()


def test_real_built_index_skips_with_a_named_asset_reason(tmp_path, monkeypatch):
    """A missing untracked fixture must not look like a lease or worker hang."""
    monkeypatch.setattr("test_retrieval_raw_lane.assets_present", lambda: False)
    with pytest.raises(pytest.skip.Exception, match="_assets_unavailable"):
        test_real_built_index_semantic_only_hit_is_not_released_without_confirmation(tmp_path)


def test_revoked_source_semantic_hit_does_not_release_body(database):
    from datetime import UTC, datetime

    from one_memory.retrieval.index_store import PublishedChunk
    from one_memory.retrieval.raw_candidates import RawSemanticCandidate
    from one_memory.retrieval.raw_lane import load_raw_items_from_candidates
    from tests.test_context_raw import revoke

    with sqlite3.connect(database) as db, db:
        put(db, "e-revoked", "用户决定 One Memory 采用 MIT 协议发布。")
        revoke(db, "cursor")
    chunk = PublishedChunk(
        chunk_id="c1",
        build_id="b1",
        evidence_id="e-revoked",
        revision=1,
        start_cp=0,
        end_cp=8,
        ordinal=0,
        source_id="cursor",
        event_time=datetime(2026, 9, 19, tzinfo=UTC),
    )
    items = load_raw_items_from_candidates(
        database,
        RawCandidateBatch(hits=(RawSemanticCandidate(chunk, 0.1),), complete=True),
        source_ids=frozenset({"cursor"}),
        deadline=time.monotonic() + 5,
    )
    assert items == ()
