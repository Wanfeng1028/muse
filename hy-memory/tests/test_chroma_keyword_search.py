# -*- coding: utf-8 -*-
"""
Chroma keyword_search 端到端测试。

注意：本地嵌入式 Chroma（PersistentClient）不支持原生 BM25/FTS 检索 ——
新的 collection.search() Search 表达式引擎只在 Chroma Server / Cloud（Rust
分布式后端）实现，本地调用会抛 NotImplementedError("Search is not implemented
for Local Chroma")。旧的 $contains 子串匹配命中只能给 binary 1.0 分，被 reader
端 normalize_bm25 sigmoid 压成 ~0.039 后对融合几乎无贡献还稀释强语义结果，
因此 keyword_search 在 chroma 后端故意 return []（诚实退化为纯向量召回）。

→ 这些断言"有命中"的用例对本地 chroma 不成立，整体 skip。真关键词检索请用
  支持 sparse/BM25 的后端（qdrant）。chromadb>=1.5.9 已具备 server
  模式的 BM25 能力，将来上 chroma server 时可重新启用。
"""

import asyncio
import random
import uuid
from typing import List

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus

pytestmark = pytest.mark.skip(
    reason="本地 Chroma 不支持原生 BM25/FTS（Search 引擎仅 server/cloud 实现），"
           "keyword_search 故意 return []。真关键词检索走 qdrant 后端。"
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_node(
    *,
    content: str,
    user_id: str = "u1",
    agent_id: str = "a1",
    session_id: str = "s1",
    layer: MemoryLayer = MemoryLayer.L2_FACT,
    status: MemoryStatus = MemoryStatus.ACTIVE,
    is_latest: bool = True,
    dims: int = 32,
) -> MemoryNode:
    node = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
        content=content,
        layer=layer,
        status=status,
        is_latest=is_latest,
    )
    vec = [random.gauss(0, 1) for _ in range(dims)]
    norm = sum(v * v for v in vec) ** 0.5
    node.embedding = [v / norm for v in vec]
    return node


@pytest.fixture
def store(tmp_path):
    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_kw_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma_data"),
            "embedding_dims": 32,
        },
    })
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestChromaKeywordSearchChinese:

    def test_chinese_query_hits_chinese_content(self, store):
        nodes = [
            _make_node(content="用户倾向于接受务实的解决方案，主动寻找更新", user_id="u1"),
            _make_node(content="今天天气不错，公园里很多人散步", user_id="u1"),
            _make_node(content="用户喜欢吃辣，川菜火锅都行", user_id="u1"),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="用户倾向接受务实", user_id="u1", top_k=5))
        ids = {h["node_id"] for h in hits}
        # 命中第 1 条（含"用户/倾向/接受/务实"），可能也命中第 3 条（含"用户"）
        assert nodes[0].node_id in ids
        # 第 2 条不应命中（没"用户/倾向/接受/务实"任一）
        assert nodes[1].node_id not in ids

    def test_chinese_no_overlap_returns_empty(self, store):
        nodes = [
            _make_node(content="今天天气不错，公园里很多人", user_id="u1"),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="完全无关的另一个查询", user_id="u1", top_k=5))
        assert hits == []

    def test_score_is_binary_one(self, store):
        """跟 Qdrant 行为对齐：所有命中 score=1.0"""
        nodes = [_make_node(content="用户倾向接受务实", user_id="u1")]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="用户", user_id="u1", top_k=5))
        assert len(hits) == 1
        assert hits[0]["score"] == 1.0


class TestChromaKeywordSearchEnglish:

    def test_english_query_hits(self, store):
        nodes = [
            _make_node(content="How to deploy to production with twine upload", user_id="u1"),
            _make_node(content="User likes coffee in the morning", user_id="u1"),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="deploy production", user_id="u1", top_k=5))
        ids = {h["node_id"] for h in hits}
        assert nodes[0].node_id in ids
        assert nodes[1].node_id not in ids


class TestChromaKeywordSearchFilters:

    def test_user_id_filter(self, store):
        nodes = [
            _make_node(content="用户倾向接受务实", user_id="u1"),
            _make_node(content="用户倾向接受务实", user_id="u2"),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="用户倾向", user_id="u1", top_k=10))
        ids = {h["node_id"] for h in hits}
        assert nodes[0].node_id in ids
        assert nodes[1].node_id not in ids

    def test_agent_id_filter(self, store):
        nodes = [
            _make_node(content="用户倾向接受务实", user_id="u1", agent_id="a1"),
            _make_node(content="用户倾向接受务实", user_id="u1", agent_id="a2"),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(
            query="用户倾向", user_id="u1", agent_ids=["a1"], top_k=10,
        ))
        ids = {h["node_id"] for h in hits}
        assert nodes[0].node_id in ids
        assert nodes[1].node_id not in ids

    def test_layer_filter(self, store):
        nodes = [
            _make_node(content="用户倾向接受务实", user_id="u1", layer=MemoryLayer.L2_FACT),
            _make_node(content="用户倾向接受务实", user_id="u1", layer=MemoryLayer.L4_IDENTITY),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(
            query="用户倾向", user_id="u1", layers=[MemoryLayer.L4_IDENTITY], top_k=10,
        ))
        ids = {h["node_id"] for h in hits}
        assert nodes[1].node_id in ids
        assert nodes[0].node_id not in ids

    def test_status_filter_excludes_non_active(self, store):
        nodes = [
            _make_node(content="用户倾向接受务实", user_id="u1", status=MemoryStatus.ACTIVE),
            _make_node(content="用户倾向接受务实", user_id="u1", status=MemoryStatus.SUPERSEDED),
        ]
        run(store.upsert_batch(nodes))

        # 默认只搜 active
        hits = run(store.keyword_search(query="用户倾向", user_id="u1", top_k=10))
        ids = {h["node_id"] for h in hits}
        assert nodes[0].node_id in ids
        assert nodes[1].node_id not in ids

    def test_only_latest(self, store):
        nodes = [
            _make_node(content="用户倾向接受务实", user_id="u1", is_latest=True),
            _make_node(content="用户倾向接受务实", user_id="u1", is_latest=False),
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(
            query="用户倾向", user_id="u1", only_latest=True, top_k=10,
        ))
        ids = {h["node_id"] for h in hits}
        assert nodes[0].node_id in ids
        assert nodes[1].node_id not in ids


class TestChromaKeywordSearchEdgeCases:

    def test_empty_query_returns_empty(self, store):
        hits = run(store.keyword_search(query="", user_id="u1"))
        assert hits == []

    def test_whitespace_only_query_returns_empty(self, store):
        hits = run(store.keyword_search(query="   ", user_id="u1"))
        assert hits == []

    def test_top_k_caps_results(self, store):
        nodes = [
            _make_node(content=f"用户倾向 候选 {i}", user_id="u1") for i in range(5)
        ]
        run(store.upsert_batch(nodes))

        hits = run(store.keyword_search(query="用户倾向", user_id="u1", top_k=3))
        assert len(hits) <= 3
