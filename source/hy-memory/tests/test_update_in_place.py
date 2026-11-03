# -*- coding: utf-8 -*-
"""
UPDATE 原地更新旧节点（chroma 后端，驱动 writer._reconcile_and_store）。

UPDATE 语义 = 合并精炼同一主题，本质同一条记忆延续。改为原地更新后：
- node_id 不变（不再删旧建新）；
- content + embedding 被替换；
- access_count / last_accessed_at 保留（不打回冷启动）；
- 不产生 SHADOW 垃圾节点。
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.agent.reconciler import ReconcileResult, ReconcileOp


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _emb(dims=32):
    v = [random.gauss(0, 1) for _ in range(dims)]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture
def config(tmp_path):
    return MemoryConfig.from_dict({"vector_store": {
        "provider": "chroma",
        "collection_name": f"test_upd_{uuid.uuid4().hex[:8]}",
        "persist_directory": str(tmp_path / "chroma"),
        "embedding_dims": 32,
    }})


@pytest.fixture
def store(config):
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestUpdateInPlace:
    def test_update_keeps_node_id_and_access_count(self, store, config):
        from hy_memory.pipelines.writer import MemoryWriter
        from hy_memory.pipelines.base import WriteRequest

        shared = _emb()
        new_vec = _emb()
        # 旧节点：已积累 access_count=7
        old = MemoryNode(node_id="m1", user_id="u1", agent_id="default_agent",
                         session_id="s1", content="用户在学吉他",
                         layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
                         is_latest=True)
        old.embedding = list(shared)
        old.access_count = 7
        old.last_accessed_at = datetime.now() - timedelta(days=2)
        old.gmt_created = datetime.now() - timedelta(days=30)
        run(store.upsert(old))

        writer = MemoryWriter(config, vector_store=store)
        run(writer.initialize())

        class _FakeEmbed:
            async def embed_batch(self, texts):
                return [list(new_vec) for _ in texts]
            async def embed_queued(self, text, use_cache=True):
                return list(new_vec)
        writer._embed_service = _FakeEmbed()

        new_content = "用户会弹吉他并在开放麦表演"
        async def _fake_reconcile(*args, **kwargs):
            return ReconcileResult(ops=[
                ReconcileOp(op="UPDATE", memory_id="m1", content=new_content,
                            layer="L2_FACT", owner="user", tags=["music"])
            ], success=True)
        writer._reconciler.reconcile = _fake_reconcile

        req = WriteRequest(content="x", user_id="u1", agent_id="default_agent", session_id="s1")
        stored_ids, err, ops, tok = run(writer._reconcile_and_store(
            new_memory_texts=[new_content],
            new_memories_meta=[{"content": new_content, "layer": "L2_FACT", "owner": "user", "tags": ["music"]}],
            request=req, vector_store=store, req_id="rq1",
        ))
        assert err is None
        assert stored_ids == ["m1"], "原地更新应复用 m1，不产生新 node_id"
        assert ops["update"] == 1
        assert ops["total"] == ops["add"] + ops["supersede"] + ops["update"]
        assert set(tok) == {"prompt", "completion", "total"}

        # m1 仍在，content/embedding 已换，access_count 保留，仍 ACTIVE+is_latest
        node = run(store.get_by_id("m1"))
        assert node is not None
        assert node.content == new_content
        assert node.status == MemoryStatus.ACTIVE
        assert node.is_latest is True
        assert node.access_count == 7, "access_count 必须保留（不打回冷启动）"
        # embedding 已换成 new_vec（与 new_vec 点积≈1）
        embs = run(store.get_embeddings(["m1"]))
        dot = sum(a * b for a, b in zip(embs["m1"], new_vec))
        assert dot > 0.99, f"embedding 应已更新为 new_vec, dot={dot}"

        # 不产生 SHADOW 垃圾：ACTIVE 仍只有 m1
        active = run(store.search(query_embedding=list(new_vec), user_id="u1",
                                  layers=[MemoryLayer.L2_FACT], limit=10,
                                  status_filter=[MemoryStatus.ACTIVE]))
        assert {h["node_id"] for h in active} == {"m1"}
