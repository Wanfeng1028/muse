"""Chroma list_by_user filter ordering and raw-layer visibility regressions."""

import asyncio
import threading
import uuid

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode, MemoryStatus


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _node(user_id, content, *, layer=MemoryLayer.L2_FACT,
          status=MemoryStatus.ACTIVE):
    node = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id=user_id,
        agent_id="a1",
        session_id="s1",
        content=content,
        layer=layer,
        status=status,
        is_latest=True,
    )
    node.embedding = [1.0, 0.0, 0.0]
    return node


@pytest.mark.asyncio
async def test_vdb_pool_recovers_if_executor_wakeup_is_lost(monkeypatch):
    """A completed worker must not leave an otherwise-idle loop asleep."""
    from hy_memory.data import vector_store_chroma as chroma_module

    loop = asyncio.get_running_loop()
    worker_ran = threading.Event()

    # Simulate the observed runtime failure: call_soon_threadsafe queues the
    # completion callback, but its self-pipe write does not wake the selector.
    monkeypatch.setattr(loop, "_write_to_self", lambda: None)

    def _work():
        worker_ran.set()
        return 42

    assert await chroma_module._run_in_vdb_pool(_work) == 42
    assert worker_ran.is_set()


@pytest.mark.asyncio
async def test_vdb_pool_preserves_worker_timeout_error():
    from hy_memory.data import vector_store_chroma as chroma_module

    def _work():
        raise TimeoutError("backend timeout")

    with pytest.raises(TimeoutError, match="backend timeout"):
        await chroma_module._run_in_vdb_pool(_work)


@pytest.fixture
def chroma_store(tmp_path, monkeypatch):
    from hy_memory.data import vector_store_chroma as chroma_module
    from hy_memory.data.vector_store_chroma import ChromaVectorStore

    async def _direct_vdb_call(func, *args, **kwargs):
        return func(*args, **kwargs)

    # The production implementation keeps Chroma calls in its dedicated thread
    # pool.  These narrow filter tests run them inline to avoid executor startup
    # noise and exercise the exact same Chroma collection/query semantics.
    monkeypatch.setattr(chroma_module, "_run_in_vdb_pool", _direct_vdb_call)

    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"list_filters_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma"),
            "embedding_dims": 3,
        },
    })
    store = ChromaVectorStore(config)
    run(store.initialize())
    yield store
    run(store.close())


def test_status_filter_is_applied_before_limit(chroma_store):
    user_id = "status-limit-user"
    run(chroma_store.upsert_batch([
        _node(user_id, "shadow", status=MemoryStatus.SHADOW),
        _node(user_id, "active", status=MemoryStatus.ACTIVE),
    ]))

    nodes = run(chroma_store.list_by_user(
        user_id=user_id,
        layers=[MemoryLayer.L2_FACT],
        status_filter=[MemoryStatus.ACTIVE],
        limit=1,
        with_vectors=False,
    ))

    assert [node.content for node in nodes] == ["active"]


def test_status_filter_supports_multiple_values_before_limit(chroma_store):
    user_id = "multi-status-user"
    run(chroma_store.upsert_batch([
        _node(user_id, "shadow", status=MemoryStatus.SHADOW),
        _node(user_id, "superseded", status=MemoryStatus.SUPERSEDED),
        _node(user_id, "active", status=MemoryStatus.ACTIVE),
    ]))

    nodes = run(chroma_store.list_by_user(
        user_id=user_id,
        layers=[MemoryLayer.L2_FACT],
        status_filter=[MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
        limit=2,
        with_vectors=False,
    ))

    assert {node.content for node in nodes} == {"active", "superseded"}


def test_raw_is_hidden_by_default_and_explicitly_available(chroma_store):
    user_id = "raw-visibility-user"
    run(chroma_store.upsert_batch([
        _node(user_id, "raw", layer=MemoryLayer.L1_RAW),
        _node(user_id, "fact", layer=MemoryLayer.L2_FACT),
    ]))

    default_nodes = run(chroma_store.list_by_user(
        user_id=user_id, with_vectors=False,
    ))
    raw_nodes = run(chroma_store.list_by_user(
        user_id=user_id,
        layers=[MemoryLayer.L1_RAW],
        allow_raw_layer=True,
        with_vectors=False,
    ))

    assert [node.content for node in default_nodes] == ["fact"]
    assert [node.content for node in raw_nodes] == ["raw"]
