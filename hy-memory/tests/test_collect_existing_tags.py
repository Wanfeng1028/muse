import pytest

from hy_memory.models.memory import MemoryNode
from hy_memory.pipelines.writer import MemoryWriter


class FakeVectorStore:
    def __init__(self, nodes=None, error=None):
        self.nodes = nodes or []
        self.error = error
        self.calls = []

    async def list_by_user(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.nodes


def _node_with_tags(*tags):
    node = MemoryNode(
        node_id="n1",
        user_id="u1",
        session_id="s1",
        content="content",
    )
    node.tags = list(tags)
    return node


@pytest.mark.asyncio
async def test_collect_existing_tags_does_not_fetch_vectors():
    store = FakeVectorStore([
        _node_with_tags("work", "python"),
        _node_with_tags("python", "memory"),
    ])
    writer = MemoryWriter.__new__(MemoryWriter)

    tags = await writer._collect_existing_tags(store, user_id="u1", agent_id="cursor")

    assert tags == ["memory", "python", "work"]
    assert store.calls == [{
        "user_id": "u1",
        "agent_id": "cursor",
        "limit": 10000,
        "with_vectors": False,
    }]


@pytest.mark.asyncio
async def test_collect_existing_tags_failure_is_non_fatal():
    store = FakeVectorStore(error=RuntimeError("vdb timeout"))
    writer = MemoryWriter.__new__(MemoryWriter)

    tags = await writer._collect_existing_tags(store, user_id="u1", agent_id=None)

    assert tags == []
    assert store.calls == [{
        "user_id": "u1",
        "agent_id": None,
        "limit": 10000,
        "with_vectors": False,
    }]


@pytest.mark.asyncio
async def test_collect_existing_tags_reuses_cached_bank_scan():
    store = FakeVectorStore([_node_with_tags("work", "python")])
    writer = MemoryWriter.__new__(MemoryWriter)

    first = await writer._collect_existing_tags(store, user_id="u1", agent_id="cursor")
    second = await writer._collect_existing_tags(store, user_id="u1", agent_id="cursor")

    assert first == second == ["python", "work"]
    assert len(store.calls) == 1


@pytest.mark.asyncio
async def test_existing_tags_cache_is_incrementally_updated():
    store = FakeVectorStore([_node_with_tags("work")])
    writer = MemoryWriter.__new__(MemoryWriter)

    assert await writer._collect_existing_tags(
        store, user_id="u1", agent_id="cursor",
    ) == ["work"]
    writer._remember_existing_tags("u1", "cursor", {"python", "memory"})

    assert await writer._collect_existing_tags(
        store, user_id="u1", agent_id="cursor",
    ) == ["memory", "python", "work"]
    assert len(store.calls) == 1
