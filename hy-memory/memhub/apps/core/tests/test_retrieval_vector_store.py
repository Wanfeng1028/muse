import math
import socket
from time import monotonic

import numpy as np
import pytest

from one_memory.retrieval.vector_store import (
    RawVectorRecord,
    RawVectorStore,
    VectorStoreError,
    _unit_vector,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        pytest.fail("vector adapter attempted network")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


@pytest.fixture
def store(tmp_path):
    value = RawVectorStore.create(
        tmp_path / "retrieval-vectors", generation_id="generation-a", dimensions=3
    )
    try:
        yield value
    finally:
        value.close()


def record(chunk="chunk-a", *, build="build-a", generation="generation-a", vector=(1.0, 0.0, 0.0)):
    return RawVectorRecord(chunk, build, generation, vector)


def test_constructor_does_no_io_and_unopened_calls_do_not_create(tmp_path):
    directory = tmp_path / "never-created"
    value = RawVectorStore(directory, generation_id="generation-a", dimensions=3)
    assert not directory.exists()
    with pytest.raises(VectorStoreError, match="not_open"):
        value.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 1)
    assert not directory.exists()
    value.close()


def test_open_existing_missing_store_or_collection_never_creates(tmp_path, store):
    missing = tmp_path / "missing"
    with pytest.raises(VectorStoreError, match="not_found"):
        RawVectorStore.open_existing(missing, generation_id="generation-a", dimensions=3)
    assert not missing.exists()
    before = store._client.list_collections()
    with pytest.raises(VectorStoreError, match="not_found"):
        RawVectorStore.open_existing(store.directory, generation_id="other", dimensions=3)
    assert store._client.list_collections() == before


def test_real_chroma_collection_has_no_embedding_function_or_documents(store):
    store.upsert([record()])
    collection = store._collection
    assert collection._embedding_function is None
    result = collection.get(ids=["chunk-a"], include=["embeddings", "metadatas", "documents"])
    assert result["documents"] == [None]
    assert result["metadatas"][0]["chunk_id"] == "chunk-a"
    assert result["metadatas"][0]["build_id"] == "build-a"
    assert result["metadatas"][0]["generation_id"] == "generation-a"
    assert len(result["embeddings"][0]) == 3
    store.verify([record()])


def test_existing_read_handle_cannot_write_or_repair_and_releases_shared_client(store):
    store.upsert([record()])
    opened = RawVectorStore.open_existing(
        store.directory, generation_id="generation-a", dimensions=3
    )
    try:
        result = opened.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 10)
        assert result.complete and result.hits[0].chunk_id == "chunk-a"
        with pytest.raises(VectorStoreError, match="read_only"):
            opened.upsert([record("new")])
        opened.verify([record()])
    finally:
        opened.close()
    store.verify([record()])
    with pytest.raises(VectorStoreError, match="closed"):
        opened.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 1)


@pytest.mark.parametrize("changed", [record(build="different"), record(vector=(0.0, 1.0, 0.0))])
def test_immutable_id_rejects_different_metadata_or_vector_without_overwriting(store, changed):
    store.upsert([record()])
    store.upsert([record()])
    with pytest.raises(VectorStoreError, match="immutable_conflict"):
        store.upsert([record("new"), changed])
    store.verify([record()])
    assert store._collection.get(ids=["new"])["ids"] == []


def test_verify_detects_missing_and_tampered_records(store):
    with pytest.raises(VectorStoreError, match="missing"):
        store.verify([record()])
    store.upsert([record()])
    store._collection.update(ids=["chunk-a"], embeddings=[[0.0, 1.0, 0.0]])
    with pytest.raises(VectorStoreError):
        store.verify([record()])
    with pytest.raises(VectorStoreError):
        store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 10)


@pytest.mark.parametrize(
    "vector",
    [
        (1.0, 0.0),
        (1.0, 0.0, math.nan),
        (math.inf, 0.0, 1.0),
        (0.0, 0.0, 0.0),
        (True, 0.0, 1.0),
        (1e100, 0.0, 1.0),
    ],
)
def test_invalid_vectors_refused_before_writes_or_search(store, vector):
    with pytest.raises(VectorStoreError):
        store.upsert([record(vector=vector)])
    with pytest.raises(VectorStoreError):
        store.search(vector, [], 1, monotonic() + 1)
    assert store._collection.count() == 0


def test_wrong_generation_and_duplicate_ids_rejected(store):
    with pytest.raises(VectorStoreError):
        store.upsert([record(generation="other")])
    with pytest.raises(VectorStoreError):
        store.upsert([record(), record()])
    assert store._collection.count() == 0


def test_empty_eligible_ids_never_queries_all_collection(store, monkeypatch):
    store.upsert([record()])
    monkeypatch.setattr(
        store._collection, "query", lambda **kwargs: pytest.fail("unfiltered query")
    )
    result = store.search((1.0, 0.0, 0.0), [], 3, monotonic() - 1)
    assert result.complete and result.hits == ()
    assert result.eligible_count == result.searched_count == 0


def test_real_in_filter_excludes_closer_unapproved_id_and_matches_small_cosine_oracle(store):
    rows = [
        record("denied", vector=(1.0, 0.0, 0.0)),
        record("b", vector=(0.9, 0.1, 0.0)),
        record("c", vector=(0.0, 1.0, 0.0)),
        record("d", vector=(-1.0, 0.0, 0.0)),
    ]
    store.upsert(rows)
    result = store.search((1.0, 0.0, 0.0), ["b", "c", "d"], 3, monotonic() + 10)
    assert result.complete and result.searched_count == 3
    assert [hit.chunk_id for hit in result.hits] == ["b", "c", "d"]
    for hit, row in zip(result.hits, rows[1:], strict=True):
        vector = np.array(row.vector, dtype=np.float32)
        expected = 1 - float(vector[0] / np.linalg.norm(vector))
        assert hit.distance == pytest.approx(expected, abs=1e-5)


def test_eligible_batches_cover_more_than_2048_and_merge_topk(store, monkeypatch):
    ids = [f"chunk-{i:04d}" for i in range(2053)]
    rows = [record(chunk, vector=(float(i + 1), 1.0, 0.0)) for i, chunk in enumerate(ids)]
    store.upsert(rows)
    calls = []
    get = store._collection.get

    def tracked(**kwargs):
        calls.append(kwargs)
        return get(**kwargs)

    monkeypatch.setattr(store._collection, "get", tracked)
    result = store.search((1.0, 0.0, 0.0), ids, 3, monotonic() + 30)
    assert result.complete and result.searched_count == 2053
    assert len(calls) == 2
    assert [len(call["ids"]) for call in calls] == [2048, 5]
    assert set().union(*(set(call["ids"]) for call in calls)) == set(ids)
    assert all(call["include"] == ["embeddings", "metadatas"] for call in calls)
    assert len(result.hits) == 3
    # The exact ranking over every eligible chunk, not one batch's local top-K:
    # a per-batch top-K would have kept the second batch's steepest vectors out.
    # Distances come from the stored unit vectors, so float32 rounding decides
    # the top of this ranking just as it does for the adapter.
    stored = {row.chunk_id: np.array(_unit_vector(row.vector), dtype=np.float32) for row in rows}
    expected = {
        chunk_id: float(1 - np.dot(unit, np.array([1.0, 0.0, 0.0], dtype=np.float32)))
        for chunk_id, unit in stored.items()
    }
    ranked = sorted(expected.items(), key=lambda pair: (pair[1], pair[0]))[:3]
    assert [hit.chunk_id for hit in result.hits] == [chunk for chunk, _ in ranked]
    for hit in result.hits:
        assert hit.distance == pytest.approx(expected[hit.chunk_id], abs=1e-6)


def test_deadline_before_query_and_late_batch_return_are_partial(store, monkeypatch):
    store.upsert([record()])
    calls = []
    now = [0.0]
    store._clock = lambda: now[0]
    get = store._collection.get

    def late(**kwargs):
        calls.append(kwargs)
        result = get(**kwargs)
        now[0] = 2.0
        return result

    monkeypatch.setattr(store._collection, "get", late)
    first = store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, 0.0)
    assert not first.complete and first.reason == "deadline" and first.hits == ()
    assert calls == []
    second = store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, 1.0)
    assert not second.complete and second.searched_count == 0 and second.hits == ()
    assert len(calls) == 1


def test_search_never_scores_a_vector_the_caller_did_not_declare_eligible(store, monkeypatch):
    """Chroma's own filtered query is no longer used at all.

    It does not score every ID in its `where $in` allowlist, so a query could
    come back short while claiming completion, and a global query filtered
    afterwards would let unauthorized vectors take the eligible ones' places.
    """
    store.upsert([record(), record("denied", vector=(1.0, 0.0, 0.0))])
    monkeypatch.setattr(
        store._collection,
        "query",
        lambda **kwargs: pytest.fail("global or filtered ANN query is not used"),
    )
    result = store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 10)
    assert result.complete and [hit.chunk_id for hit in result.hits] == ["chunk-a"]


def test_an_eligible_vector_missing_from_the_backend_is_unavailable_not_a_miss(store):
    """The caller published this chunk, so an absent vector is a broken build."""
    store.upsert([record("present")])
    with pytest.raises(VectorStoreError, match="^vector_query_unavailable$"):
        store.search((1.0, 0.0, 0.0), ["present", "absent"], 2, monotonic() + 10)


def test_open_existing_validates_generation_dimensions_and_collection_config(store):
    with pytest.raises(VectorStoreError):
        RawVectorStore.open_existing(store.directory, generation_id="generation-a", dimensions=4)
    store._collection.modify(metadata={"generation_id": "other"})
    with pytest.raises(VectorStoreError):
        RawVectorStore.open_existing(store.directory, generation_id="generation-a", dimensions=3)


def test_open_existing_refuses_symlink_database_before_chroma(tmp_path):
    directory = tmp_path / "retrieval-vectors"
    directory.mkdir()
    target = tmp_path / "not-a-chroma-db"
    target.write_bytes(b"do not open")
    (directory / "chroma.sqlite3").symlink_to(target)
    with pytest.raises(VectorStoreError):
        RawVectorStore.open_existing(directory, generation_id="generation-a", dimensions=3)
    assert target.read_bytes() == b"do not open"


def test_writer_reopen_resumes_idempotently_but_query_handle_still_cannot_write(tmp_path):
    directory = tmp_path / "retrieval-vectors"
    original = RawVectorStore.create(directory, generation_id="generation-a", dimensions=3)
    try:
        original.upsert([record(vector=(1.0, 1.0, 0.0))])
    finally:
        original.close()
    writer = RawVectorStore.open_writer_existing(
        directory, generation_id="generation-a", dimensions=3
    )
    try:
        writer.upsert([record(vector=(1.0, 1.0, 0.0))])
        writer.verify([record(vector=(1.0, 1.0, 0.0))])
        with pytest.raises(VectorStoreError, match="immutable_conflict"):
            writer.upsert([record(build="other", vector=(1.0, 1.0, 0.0))])
        with pytest.raises(VectorStoreError, match="immutable_conflict"):
            writer.upsert([record(vector=(2.0, 2.0, 0.0))])
        assert writer._collection.count() == 1
    finally:
        writer.close()
    reader = RawVectorStore.open_existing(directory, generation_id="generation-a", dimensions=3)
    try:
        with pytest.raises(VectorStoreError, match="read_only"):
            reader.upsert([record("new")])
        result = reader.search((1.0, 1.0, 0.0), ["chunk-a"], 1, monotonic() + 10)
        assert result.complete and result.hits[0].distance == pytest.approx(0, abs=1e-5)
    finally:
        reader.close()


def test_writer_existing_does_not_create_missing_store_or_collection(tmp_path, store):
    missing = tmp_path / "writer-missing"
    with pytest.raises(VectorStoreError, match="not_found"):
        RawVectorStore.open_writer_existing(missing, generation_id="generation-a", dimensions=3)
    assert not missing.exists()
    with pytest.raises(VectorStoreError, match="not_found"):
        RawVectorStore.open_writer_existing(store.directory, generation_id="other", dimensions=3)


def test_partial_keeps_only_completed_eligible_batches(store, monkeypatch):
    ids = [f"present-{i}" for i in range(2048)] + ["last"]
    store.upsert([*(record(chunk, vector=(1.0, float(i + 1), 0.0)) for i, chunk in enumerate(ids))])
    now = [0.0]
    store._clock = lambda: now[0]
    get = store._collection.get
    calls = []

    def timed(**kwargs):
        calls.append(kwargs)
        result = get(**kwargs)
        if len(calls) == 2:
            now[0] = 2.0
        return result

    monkeypatch.setattr(store._collection, "get", timed)
    result = store.search((1.0, 0.0, 0.0), ids, 2, 1.0)
    assert not result.complete and result.reason == "deadline"
    assert result.searched_count == 2048 and result.eligible_count == 2049
    assert [hit.chunk_id for hit in result.hits] == ["present-0", "present-1"]


@pytest.mark.parametrize("mutation", ["metadata", "dimension", "hash", "extra_id"])
def test_malformed_search_response_is_rejected_not_partial_success(store, monkeypatch, mutation):
    store.upsert([record()])
    get = store._collection.get

    def malformed(**kwargs):
        result = get(**kwargs)
        if mutation == "metadata":
            result["metadatas"][0][0]["generation_id"] = "wrong"
        elif mutation == "dimension":
            result["embeddings"] = [[1.0, 0.0]]
        elif mutation == "hash":
            result["metadatas"][0]["vector_sha256"] = "0" * 64
        else:
            result["ids"] = result["ids"] * 2
            result["metadatas"] = result["metadatas"] * 2
            result["embeddings"] = [result["embeddings"][0], result["embeddings"][0]]
        return result

    monkeypatch.setattr(store._collection, "get", malformed)
    with pytest.raises(VectorStoreError):
        store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 10)


@pytest.mark.parametrize(
    "ids,limit,deadline",
    [
        (["chunk-a", "chunk-a"], 1, 100.0),
        ("chunk-a", 1, 100.0),
        (["chunk-a"], 0, 100.0),
        (["chunk-a"], True, 100.0),
        (["chunk-a"], 1, math.inf),
        (["chunk-a"], 1, math.nan),
    ],
)
def test_invalid_query_parameters_do_not_reach_chroma(store, monkeypatch, ids, limit, deadline):
    monkeypatch.setattr(store._collection, "query", lambda **kwargs: pytest.fail("invalid query"))
    with pytest.raises(VectorStoreError):
        store.search((1.0, 0.0, 0.0), ids, limit, deadline)


def test_query_backend_error_is_unavailable_not_complete_empty(store, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("backend request payload")

    monkeypatch.setattr(store._collection, "query", broken)
    with pytest.raises(VectorStoreError, match="^vector_query_unavailable$"):
        store.search((1.0, 0.0, 0.0), ["chunk-a"], 1, monotonic() + 10)


def test_last_owned_client_close_releases_chroma_system(tmp_path):
    from chromadb.api.shared_system_client import SharedSystemClient

    directory = tmp_path / "retrieval-vectors"
    writer = RawVectorStore.create(directory, generation_id="close-test", dimensions=3)
    reader = RawVectorStore.open_existing(directory, generation_id="close-test", dimensions=3)
    identifier = writer._client._identifier
    try:
        assert identifier in SharedSystemClient._identifier_to_system
        writer.close()
        assert identifier in SharedSystemClient._identifier_to_system
        reader.close()
        assert identifier not in SharedSystemClient._identifier_to_system
        reader.close()
    finally:
        reader.close()
        writer.close()


def test_open_existing_missing_collection_does_not_construct_a_client(store, monkeypatch):
    import chromadb

    monkeypatch.setattr(
        chromadb, "PersistentClient", lambda *args, **kwargs: pytest.fail("must preflight first")
    )
    with pytest.raises(VectorStoreError, match="collection_not_found"):
        RawVectorStore.open_existing(store.directory, generation_id="absent", dimensions=3)


def test_existing_dimension_mismatch_does_not_modify_collection(store):
    before = store._collection.metadata.copy()
    with pytest.raises(VectorStoreError):
        RawVectorStore.open_writer_existing(
            store.directory, generation_id="generation-a", dimensions=4
        )
    assert store._collection.metadata == before
    store.upsert([record()])
    store.verify([record()])


def test_verify_candidates_reader_checks_every_batch_without_writing(store, monkeypatch):
    rows = [record(f"candidate-{i}") for i in range(2050)]
    store.upsert(rows)
    reader = RawVectorStore.open_existing(
        store.directory, generation_id="generation-a", dimensions=3
    )
    try:
        calls = []
        get = reader._collection.get

        def tracked(**kwargs):
            calls.append(kwargs)
            return get(**kwargs)

        monkeypatch.setattr(reader._collection, "get", tracked)
        for name in ("add", "upsert", "update", "delete", "query"):
            monkeypatch.setattr(
                reader._collection, name, lambda **kwargs: pytest.fail("unexpected backend call")
            )
        assert (
            reader.verify_candidates(
                [(row.chunk_id, row.build_id) for row in rows], deadline=monotonic() + 30
            )
            is True
        )
        assert [len(call["ids"]) for call in calls] == [2048, 2]
        assert all(call["include"] == ["embeddings", "metadatas"] for call in calls)
    finally:
        reader.close()


def test_verify_candidates_empty_and_expired_do_not_read(store, monkeypatch):
    monkeypatch.setattr(store._collection, "get", lambda **kwargs: pytest.fail("unexpected read"))
    store._clock = lambda: 10.0
    assert store.verify_candidates([], deadline=0.0) is True
    assert store.verify_candidates([("chunk-a", "build-a")], deadline=10.0) is False


@pytest.mark.parametrize("expires", ["after_read", "between_batches"])
def test_verify_candidates_deadline_stops_before_another_batch(store, monkeypatch, expires):
    rows = [record(f"candidate-{i}") for i in range(2049)]
    store.upsert(rows)
    calls = []
    get = store._collection.get

    def tracked(**kwargs):
        calls.append(kwargs)
        return get(**kwargs)

    ticks = iter([0.0, 2.0] if expires == "after_read" else [0.0, 0.0, 2.0])
    store._clock = lambda: next(ticks)
    monkeypatch.setattr(store._collection, "get", tracked)
    assert (
        store.verify_candidates([(row.chunk_id, row.build_id) for row in rows], deadline=1.0)
        is False
    )
    assert len(calls) == 1 and len(calls[0]["ids"]) == 2048


@pytest.mark.parametrize("pair", [("missing", "build-a"), ("chunk-a", "other-build")])
def test_verify_candidates_missing_or_wrong_build_refuses(store, pair):
    store.upsert([record()])
    with pytest.raises(VectorStoreError, match="missing|identity_mismatch"):
        store.verify_candidates([pair], deadline=monotonic() + 10)


@pytest.mark.parametrize("mutation", ["generation", "dimension", "hash", "extra_id"])
def test_verify_candidates_corrupt_backend_record_refuses(store, monkeypatch, mutation):
    store.upsert([record()])
    get = store._collection.get

    def corrupt(**kwargs):
        data = get(**kwargs)
        if mutation == "generation":
            data["metadatas"][0]["generation_id"] = "other-generation"
        elif mutation == "dimension":
            data["embeddings"] = [[1.0, 0.0]]
        elif mutation == "hash":
            data["metadatas"][0]["vector_sha256"] = "0" * 64
        else:
            data["ids"][0] = "not-eligible"
        return data

    monkeypatch.setattr(store._collection, "get", corrupt)
    with pytest.raises(VectorStoreError):
        store.verify_candidates([("chunk-a", "build-a")], deadline=monotonic() + 10)


@pytest.mark.parametrize(
    "candidates",
    [
        [("chunk-a", "build-a"), ("chunk-a", "build-a")],
        [("chunk-a", "build-a"), ("chunk-a", "other")],
        [("../escape", "build-a")],
        [("chunk-a", "")],
        [("chunk-a", 123)],
        [("chunk-a",)],
        ["ab"],
        "ab",
        None,
    ],
)
def test_verify_candidates_invalid_input_refuses_before_read(store, monkeypatch, candidates):
    monkeypatch.setattr(store._collection, "get", lambda **kwargs: pytest.fail("unexpected read"))
    with pytest.raises(VectorStoreError):
        store.verify_candidates(candidates, deadline=monotonic() + 10)


@pytest.mark.parametrize("deadline", [math.nan, math.inf, True, "soon"])
def test_verify_candidates_invalid_deadline_refuses_even_empty(store, deadline):
    with pytest.raises(VectorStoreError, match="invalid_deadline"):
        store.verify_candidates([], deadline=deadline)
