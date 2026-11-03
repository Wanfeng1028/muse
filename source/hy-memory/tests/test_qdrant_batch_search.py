from types import SimpleNamespace

import pytest

from hy_memory.data.vector_store_qdrant import QdrantVectorStore
from hy_memory.models.memory import MemoryLayer, MemoryStatus


class _BatchClient:
    def __init__(self):
        self.calls = []

    def query_batch_points(self, *, collection_name, requests):
        self.calls.append((collection_name, requests))
        return [
            SimpleNamespace(
                points=[SimpleNamespace(
                    payload={"node_id": f"n{index}"}, score=0.9 - index * 0.1,
                )]
            )
            for index, _request in enumerate(requests)
        ]


def _store():
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._client = _BatchClient()
    store._collection_name = "test"
    store._is_local = False
    store._supports_fulltext = True
    store._sparse_name = "bm25"
    store._payload_to_node = lambda payload: SimpleNamespace(
        node_id=payload["node_id"], content=payload["node_id"]
    )
    return store


@pytest.mark.asyncio
async def test_dense_search_batch_uses_one_qdrant_rpc(monkeypatch):
    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "hy_memory.data.vector_store_qdrant._run_in_vdb_pool", direct,
    )
    store = _store()
    requests = [
        {
            "query_embedding": [1.0, 0.0],
            "user_id": "u1",
            "layers": [MemoryLayer.L2_FACT],
            "limit": 20,
            "score_threshold": 0.2,
            "status_filter": [MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
            "only_latest": False,
        },
        {
            "query_embedding": [0.0, 1.0],
            "user_id": "u1",
            "layers": [MemoryLayer.L2_FACT],
            "limit": 10,
            "score_threshold": 0.0,
            "status_filter": [MemoryStatus.ACTIVE],
            "only_latest": True,
        },
    ]

    result = await store.search_batch(requests)

    assert [[hit["node_id"] for hit in row] for row in result] == [["n0"], ["n1"]]
    assert len(store._client.calls) == 1
    _collection, queries = store._client.calls[0]
    assert [query.limit for query in queries] == [20, 10]
    assert [query.score_threshold for query in queries] == [0.2, 0.0]
    assert queries[0].filter.must[0].match.value == "u1"


@pytest.mark.asyncio
async def test_keyword_search_batch_uses_one_qdrant_rpc(monkeypatch):
    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "hy_memory.data.vector_store_qdrant._run_in_vdb_pool", direct,
    )
    store = _store()
    monkeypatch.setenv("MEMORY_BM25_STABLE_TIES_ENABLED", "false")
    monkeypatch.setattr(
        "hy_memory.pipelines._retrieval.bm25_fastembed.is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "hy_memory.pipelines._retrieval.bm25_fastembed.encode_query",
        lambda text: ([len(text)], [1.0]),
    )

    result = await store.keyword_search_batch([
        {
            "query": "alpha",
            "top_k": 60,
            "user_id": "u1",
            "layers": [MemoryLayer.L2_FACT],
            "status_filter": [MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
            "only_latest": False,
        },
        {
            "query": "beta",
            "top_k": 40,
            "user_id": "u1",
            "layers": [MemoryLayer.L2_FACT],
            "status_filter": [MemoryStatus.ACTIVE],
            "only_latest": True,
        },
    ])

    assert [[hit["node_id"] for hit in row] for row in result] == [["n0"], ["n1"]]
    assert len(store._client.calls) == 1
    _collection, queries = store._client.calls[0]
    assert [query.limit for query in queries] == [60, 40]
    assert all(query.using == "bm25" for query in queries)
