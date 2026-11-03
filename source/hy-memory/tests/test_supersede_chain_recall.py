# -*- coding: utf-8 -*-
"""
SUPERSEDE 演化链召回（chroma 后端）。

回归保护两个核心行为：
- 旧节点 status=SUPERSEDED 也能进召回池（不是只召回链头 ACTIVE 节点）；
- 命中链上任意节点 → expand_evolution_chains 从命中点双向展开整链，
  以链头（is_latest=True）为代表返回；
- 同一条链多个节点同时命中 → 去重为一条（不重复输出）。

另保护：reconcile 候选搜索仍只搜 ACTIVE（不把 SUPERSEDED 拉进来当候选去
二次取代）。
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines.reader_hybrid import HybridReadPipeline
from hy_memory.pipelines.base import ReadRequest


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
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_chain_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma_data"),
            "embedding_dims": 32,
        },
    })


@pytest.fixture
def store(config):
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


def _node(node_id, content, *, status, is_latest, supersedes=None,
          superseded_by=None, emb=None, days_ago=0):
    n = MemoryNode(
        node_id=node_id, user_id="u1", agent_id="default_agent", session_id="s1",
        content=content, layer=MemoryLayer.L2_FACT, status=status,
        is_latest=is_latest,
        supersedes=supersedes, superseded_by=superseded_by,
    )
    n.memory_at = datetime.now() - timedelta(days=days_ago)
    n.embedding = emb or _emb()
    return n


def _seed_chain(store, shared_emb):
    """种一条 3 节点链：E0 ← E1 ← E2（E2=ACTIVE 链头，E0/E1=SUPERSEDED）。

    三个节点用同一向量，保证查询能同时命中（验证多命中去重）。
    """
    e0 = _node("E0", "用户住在涩谷的公寓", status=MemoryStatus.SUPERSEDED,
               is_latest=False, superseded_by=["E1"], emb=list(shared_emb), days_ago=30)
    e1 = _node("E1", "用户搬到了新宿", status=MemoryStatus.SUPERSEDED,
               is_latest=False, supersedes=["E0"], superseded_by=["E2"],
               emb=list(shared_emb), days_ago=15)
    e2 = _node("E2", "用户现在住横滨", status=MemoryStatus.ACTIVE,
               is_latest=True, supersedes=["E1"], emb=list(shared_emb), days_ago=1)
    for n in (e0, e1, e2):
        run(store.upsert(n))
    return e0, e1, e2


class TestSupersededRecall:
    def test_superseded_node_enters_recall_pool(self, store, config):
        """search 默认只 ACTIVE 会漏掉 SUPERSEDED；hybrid 应纳入 SUPERSEDED。"""
        shared = _emb()
        _seed_chain(store, shared)

        # 直接验证 reader 用的 status_filter：只 ACTIVE 时只能召回 E2
        only_active = run(store.search(
            query_embedding=list(shared), user_id="u1",
            layers=[MemoryLayer.L2_FACT], limit=10,
            status_filter=[MemoryStatus.ACTIVE], only_latest=False,
        ))
        assert {h["node_id"] for h in only_active} == {"E2"}

        # 纳入 SUPERSEDED 后，E0/E1/E2 都能进池
        with_super = run(store.search(
            query_embedding=list(shared), user_id="u1",
            layers=[MemoryLayer.L2_FACT], limit=10,
            status_filter=[MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
            only_latest=False,
        ))
        assert {h["node_id"] for h in with_super} == {"E0", "E1", "E2"}

    def test_reader_recalls_chain_and_dedups(self, store, config):
        """hybrid：多个链节点同时命中 → 展开为一条（链头代表）+ 完整链。"""
        shared = _emb()
        _seed_chain(store, shared)

        reader = HybridReadPipeline(config, vector_store=store)
        run(reader.initialize())
        req = ReadRequest(query="用户住哪", user_id="u1",
                          query_embedding=list(shared), min_score=0.0, limit=10)
        resp = run(reader.read(req))
        assert resp.success

        # 同一条链的 3 个节点命中，去重为 1 条
        l2 = [m for m in resp.memories if m.get("layer") == MemoryLayer.L2_FACT.value]
        assert len(l2) == 1, f"chain should dedup to 1, got {[m['memory_id'] for m in l2]}"
        # 代表节点 = 链头 E2（is_latest）
        assert l2[0]["memory_id"] == "E2"

    def test_hit_old_node_expands_full_chain(self, store, config):
        """命中旧节点（非链头）也能双向展开整链。"""
        from hy_memory.pipelines._retrieval.evolution import expand_evolution_chains

        shared = _emb()
        e0, e1, e2 = _seed_chain(store, shared)

        # 模拟只命中中间旧节点 E1（带 node 对象）
        e1_node = run(store.get_by_id("E1"))
        hits = [{"node_id": "E1", "score": 0.9, "node": e1_node}]
        out = run(expand_evolution_chains(store, hits))

        assert len(out) == 1
        exp = out[0]
        # 双向展开后以链头 E2 为代表
        assert exp["node_id"] == "E2"
        assert exp.get("is_evolved") is True
        chain_ids = {c["node_id"] for c in exp["evolution_chain"]}
        assert chain_ids == {"E0", "E1", "E2"}


class TestReconcileCandidatesUnaffected:
    def test_reconcile_search_still_active_only(self, store, config):
        """reconcile 候选搜索显式 status_filter=[ACTIVE]，不应召回 SUPERSEDED 旧节点。"""
        shared = _emb()
        _seed_chain(store, shared)
        # reconcile 的候选搜索语义：只 ACTIVE + only_latest=False
        hits = run(store.search(
            query_embedding=list(shared), user_id="u1",
            layers=[MemoryLayer.L2_FACT], limit=10,
            status_filter=[MemoryStatus.ACTIVE], only_latest=False,
        ))
        assert {h["node_id"] for h in hits} == {"E2"}
