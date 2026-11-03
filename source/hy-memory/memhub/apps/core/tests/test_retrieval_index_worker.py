import socket
import sqlite3
import threading
import time
from contextlib import closing

import pytest

from one_memory.embedding_assets import assets_present
from one_memory.local_embedding import TokenizedText, TokenOffset
from one_memory.retrieval.index_store import RetrievalIndexStore
from one_memory.retrieval.index_worker import LocalRetrievalEncoder, RetrievalIndexWorker
from one_memory.retrieval.vector_store import RawVectorStore, VectorStoreError
from tests.test_retrieval_index_store import fixture, initialize, put  # noqa: F401


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("index worker must stay offline")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)


class Encoder:
    def __init__(self, identity):
        self.identity = identity
        self.calls = []
        self.after_encode = lambda: None

    def tokenize_with_offsets(self, text):
        return TokenizedText(
            tuple(range(len(text))), tuple(TokenOffset(i, i + 1) for i in range(len(text)))
        )

    def encode_documents(self, texts):
        self.calls.append(texts)
        self.after_encode()
        return [[1.0, 0.5, 0.25] for _ in texts]


@pytest.fixture
def setup(fixture, tmp_path):  # noqa: F811
    generation = initialize(fixture)
    store = fixture[3]
    encoder = Encoder(fixture[4])
    vectors = RawVectorStore.create(tmp_path / "vectors", generation_id=generation, dimensions=3)
    worker = RetrievalIndexWorker(store, vectors, encoder, generation_id=generation, owner="test")
    try:
        yield fixture, generation, encoder, vectors, worker
    finally:
        vectors.close()


def test_tick_indexes_complete_original_and_reopen_can_search(setup):
    f, generation, encoder, vectors, worker = setup
    record = put(f[1], "start " + "middle " * 180 + " end")
    assert worker.run_once().state == "ready"
    assert worker.run_once().state == "idle"
    assert all(len(batch) <= 8 for batch in encoder.calls)
    assert "".join(encoder.calls[0])  # Nonempty positive encoding control.
    f[3].activate_generation(generation)
    chunks = RetrievalIndexStore(f[0]).active_chunks(generation)
    assert len(chunks) > 1 and chunks[0].start_cp == 0
    assert chunks[-1].end_cp == len(record.verbatim)
    result = vectors.search(
        [1.0, 0.5, 0.25], [c.chunk_id for c in chunks], 8, time.monotonic() + 10
    )
    assert result.complete and result.hits
    with closing(sqlite3.connect(f[0])) as db:
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='continuous_policy_history'"
        ).fetchone()


@pytest.mark.parametrize("change", ["revision", "revoke"])
def test_change_during_native_encoding_never_publishes(setup, change):
    f, generation, encoder, vectors, worker = setup
    put(f[1])

    def mutate():
        if change == "revision":
            put(f[1], "changed original")
        else:
            with closing(sqlite3.connect(f[0])) as db, db:
                db.execute("UPDATE source_grants SET revoked_at='revoked'")

    encoder.after_encode = mutate
    result = worker.run_once()
    assert result.state == "blocked"
    assert f[3].status(generation)["ready"] == 0
    assert f[3].active_chunks(generation) == ()


def test_cancel_after_encode_does_not_publish_and_is_reclaimable(setup):
    f, generation, encoder, _, worker = setup
    put(f[1])
    cancel = threading.Event()
    encoder.after_encode = cancel.set
    assert worker.run_once(cancel=cancel).state == "cancelled"
    assert f[3].status(generation)["leased"] == 1
    assert f[3].claim(generation, "replacement", now=time.time() + 61)


def test_cancel_before_tick_does_not_consume_or_encode(setup):
    f, generation, encoder, _, worker = setup
    put(f[1])
    cancel = threading.Event()
    cancel.set()
    assert worker.run_once(cancel=cancel).state == "cancelled"
    assert f[3].status(generation)["after_seq"] == 0
    assert not encoder.calls


def test_partial_vector_write_can_retry_same_build_without_duplicates(setup, monkeypatch):
    f, generation, encoder, vectors, worker = setup
    put(f[1], "long message " * 90)
    original = vectors.upsert

    def partial(records):
        original(records[:1])
        raise VectorStoreError("vector_write_unavailable")

    monkeypatch.setattr(vectors, "upsert", partial)
    assert worker.run_once().state == "blocked"
    assert f[3].status(generation)["ready"] == 0
    monkeypatch.setattr(vectors, "upsert", original)
    assert f[3].retry_blocked(generation) == 1
    assert worker.run_once().state == "ready"
    f[3].activate_generation(generation)
    assert len(f[3].active_chunks(generation)) > 1


def test_bad_vector_count_or_failed_verification_never_publishes(setup, monkeypatch):
    f, generation, encoder, vectors, worker = setup
    put(f[1])
    monkeypatch.setattr(encoder, "encode_documents", lambda _: [])
    assert worker.run_once().state == "blocked"
    assert f[3].status(generation)["ready"] == 0
    assert f[3].retry_blocked(generation) == 1
    monkeypatch.setattr(
        encoder, "encode_documents", lambda texts: [[1.0, 0.5, 0.25] for _ in texts]
    )
    monkeypatch.setattr(
        vectors, "verify", lambda _: (_ for _ in ()).throw(VectorStoreError("failure"))
    )
    assert worker.run_once().state == "blocked"
    assert f[3].status(generation)["ready"] == 0


@pytest.mark.parametrize(
    "text",
    ["token=example-secret-value", "<environment_context>system wrapper</environment_context>"],
)
def test_content_requiring_source_mapping_is_not_encoded_or_marked_ready(setup, text):
    f, generation, encoder, _, worker = setup
    put(f[1], text)
    result = worker.run_once()
    assert result.state == "blocked" and result.reason == "content_mapping_required"
    assert not encoder.calls
    assert f[3].status(generation)["ready"] == 0


def test_deadline_after_native_encode_discards_late_work(setup):
    f, generation, encoder, vectors, _ = setup
    put(f[1])
    clock = [1.0]
    encoder.after_encode = lambda: clock.__setitem__(0, 50.0)
    worker = RetrievalIndexWorker(
        f[3],
        vectors,
        encoder,
        generation_id=generation,
        owner="test",
        clock=lambda: clock[0],
        max_job_seconds=10,
    )
    assert worker.run_once().state == "deferred"
    assert f[3].status(generation)["ready"] == 0


def test_generation_encoder_mismatch_rejected_before_claim(setup):
    f, generation, encoder, vectors, _ = setup
    from dataclasses import replace

    encoder.identity = replace(encoder.identity, encoder_digest="f" * 64)
    with pytest.raises(ValueError, match="encoder_identity"):
        RetrievalIndexWorker(f[3], vectors, encoder, generation_id=generation, owner="other")
    assert f[3].status(generation)["leased"] == 0


@pytest.mark.skipif(not assets_present(), reason="locked local assets absent")
def test_real_local_encoder_chroma_full_text_chain(fixture, tmp_path):  # noqa: F811
    path, evidence, _, store, _ = fixture
    encoder = LocalRetrievalEncoder(content_version=1)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        store.initialize(db)
        generation = store.create_generation(db, encoder.identity)
    text = (
        "A long source message about source control and releases. " * 80
        + " Final artifact at /project/design/final.png"
    )
    record = put(evidence, text)
    vectors = RawVectorStore.create(
        tmp_path / "real-vectors", generation_id=generation, dimensions=encoder.identity.dimensions
    )
    try:
        worker = RetrievalIndexWorker(
            store, vectors, encoder, generation_id=generation, owner="real"
        )
        assert worker.run_once().state == "ready"
        store.activate_generation(generation)
        chunks = store.active_chunks(generation)
        assert len(chunks) > 1 and chunks[-1].end_cp == len(text)
        query = encoder.encode_documents([text[chunks[-1].start_cp : chunks[-1].end_cp]])[0]
        result = vectors.search(query, [c.chunk_id for c in chunks], 8, time.monotonic() + 10)
        assert result.complete and result.hits[0].chunk_id == chunks[-1].chunk_id
        assert record.verbatim.endswith("final.png")
    finally:
        vectors.close()
