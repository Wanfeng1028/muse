"""Local Qdrant must keep its SQLite connection on one owner thread."""

import asyncio

import pytest

qdrant_client = pytest.importorskip("qdrant_client")

from qdrant_client import QdrantClient, models  # noqa: E402
from qdrant_client.local.persistence import CollectionPersistence  # noqa: E402

from hy_memory.config import MemoryConfig, VectorStoreConfig  # noqa: E402
from hy_memory.data.vector_store import create_vector_store  # noqa: E402
from hy_memory.models.memory import MemoryLayer, MemoryNode  # noqa: E402


def _config(directory, name="thread_probe"):
    config = MemoryConfig()
    config.vector_store = VectorStoreConfig(
        provider="qdrant",
        persist_directory=str(directory),
        collection_name=name,
        embedding_dims=4,
    )
    return config


def _node(index=0):
    return MemoryNode(
        node_id=f"test-node-{index}",
        user_id="test-user",
        agent_id="test-agent",
        session_id="test-session",
        layer=MemoryLayer.L2_FACT,
        content=f"Offline owner-thread test {index}",
        embedding=[1.0, 0.0, 0.0, float(index)],
    )


@pytest.fixture
def same_thread_qdrant(monkeypatch):
    monkeypatch.setattr(CollectionPersistence, "CHECK_SAME_THREAD", True)
    monkeypatch.setattr(
        "hy_memory.pipelines._retrieval.bm25_fastembed.is_available",
        lambda: False,
    )


@pytest.mark.asyncio
async def test_reopened_local_collection_writes_with_same_thread_check(
    tmp_path,
    same_thread_qdrant,
):
    client = QdrantClient(path=str(tmp_path))
    client.create_collection(
        "thread_probe_4",
        vectors_config=models.VectorParams(
            size=4,
            distance=models.Distance.COSINE,
        ),
    )
    client.close()

    store = create_vector_store(_config(tmp_path))
    await store.initialize()
    try:
        assert await store.upsert(_node()) == "test-node-0"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_fresh_local_collection_serializes_concurrent_writes_and_close(
    tmp_path,
    same_thread_qdrant,
):
    store = create_vector_store(_config(tmp_path))
    await store.initialize()
    try:
        ids = await asyncio.gather(*(store.upsert(_node(index)) for index in range(8)))
        assert ids == [f"test-node-{index}" for index in range(8)]
    finally:
        await store.close()
