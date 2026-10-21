import asyncio
from unittest.mock import AsyncMock

from hy_memory.client import HyMemoryClient
from hy_memory.models.memory import MemoryLayer, MemoryNode


def test_concurrent_clone_fanout_reads_source_once():
    class Store:
        def __init__(self):
            self.source_reads = 0
            self.writes = []

        async def list_by_user(self, user_id, **kwargs):
            if user_id != "src":
                return []
            self.source_reads += 1
            await asyncio.sleep(0.02)
            node = MemoryNode(
                node_id="source-node",
                user_id="src",
                agent_id="a",
                session_id="s",
                content="fact",
                layer=MemoryLayer.L2_FACT,
            )
            node.embedding = [0.1, 0.2]
            return [node]

        async def upsert_batch(self, nodes):
            self.writes.append(list(nodes))
            return [node.node_id for node in nodes]

        async def delete_by_metadata(self, **kwargs):
            return 0

    async def run():
        store = Store()
        client = HyMemoryClient.__new__(HyMemoryClient)
        client._vector_store = store
        client._graph_store = None
        client._cache = None
        client._purge_graph_data = AsyncMock()
        results = await asyncio.gather(*[
            HyMemoryClient.async_clone_user.__wrapped__(
                client, "src", f"dst-{index}", agent_id=None,
            )
            for index in range(8)
        ])
        return store, results

    store, results = asyncio.run(run())
    assert store.source_reads == 1
    assert len(store.writes) == 8
    assert all(result["success"] for result in results)
