# -*- coding: utf-8 -*-
"""
Intention (L7) 召回 + 惰性过期转换 端到端测试（chroma 后端）。

覆盖：
- 未过期 L7 意图被 recall_intentions 召回，layer 标记 l7_intention；
- 已过期 L7 意图不被召回，且其存储 layer 被持久化改写为 l2_fact（再查确认）；
- valid_until=None 的意图永不过期，始终召回；
- intention_limit=0 时 reader 不返回意图（gate）；
- extractor 新 schema：facts/intentions 解析；writer 不再产 L4_IDENTITY。
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.intention import recall_intentions


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _emb(dims: int = 32):
    vec = [random.gauss(0, 1) for _ in range(dims)]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _make_intention(content, *, user_id="u1", valid_until=None, dims=32):
    node = MemoryNode(
        node_id=str(uuid.uuid4()),
        user_id=user_id,
        agent_id="a1",
        session_id="s1",
        content=content,
        layer=MemoryLayer.L7_INTENTION,
        status=MemoryStatus.ACTIVE,
        is_latest=True,
        valid_until=valid_until,
    )
    node.embedding = _emb(dims)
    return node


@pytest.fixture
def store(tmp_path):
    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_intent_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma_data"),
            "embedding_dims": 32,
        },
    })
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestRecallIntentions:

    def test_unexpired_recalled(self, store):
        future = datetime.now() + timedelta(days=7)
        n = _make_intention("用户下周二要面试字节", valid_until=future)
        run(store.upsert(n))
        q = list(n.embedding)  # 同向量保证 cosine=1 命中
        hits = run(recall_intentions(store, q, user_ids=["u1"], limit=5))
        ids = {h["node_id"] for h in hits}
        assert n.node_id in ids
        hit = next(h for h in hits if h["node_id"] == n.node_id)
        assert hit["layer"] == "l7_intention"
        assert hit["retrieval_source"] == "vdb_intention"

    def test_no_expiry_always_recalled(self, store):
        n = _make_intention("用户打算学习吉他", valid_until=None)
        run(store.upsert(n))
        q = list(n.embedding)
        hits = run(recall_intentions(store, q, user_ids=["u1"], limit=5))
        assert n.node_id in {h["node_id"] for h in hits}

    def test_expired_excluded_and_converted_to_fact(self, store):
        past = datetime.now() - timedelta(days=3)
        n = _make_intention("用户上周要交报告", valid_until=past)
        run(store.upsert(n))
        q = list(n.embedding)
        # 过期 → 不在意图结果里
        hits = run(recall_intentions(store, q, user_ids=["u1"], limit=5))
        assert n.node_id not in {h["node_id"] for h in hits}
        # 且存储 layer 被持久化改写为 l2_fact
        reloaded = run(store.get_by_id(n.node_id))
        assert reloaded is not None
        assert reloaded.layer == MemoryLayer.L2_FACT

    def test_limit_zero_returns_empty(self, store):
        n = _make_intention("用户计划去旅行", valid_until=None)
        run(store.upsert(n))
        q = _emb()
        assert run(recall_intentions(store, q, user_ids=["u1"], limit=0)) == []


class TestExtractorSchema:
    """新 schema：memory→L2_FACT、intentions 单独解析；不再产 L4_IDENTITY。"""

    def test_collect_new_memories_memory_bucket_to_l2(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {
            "memory": [{"content": "用户喜欢篮球", "tags": ["sport"]}],
            "intentions": [{"content": "用户下周面试", "valid_until": "2099-01-01"}],
        }
        texts, meta = MemoryWriter._collect_new_memories(info)
        assert "用户喜欢篮球" in texts
        assert all(m["layer"] == "L2_FACT" for m in meta)
        # intentions 不进 normal memories
        assert "用户下周面试" not in texts

    def test_collect_new_memories_legacy_facts_to_l2(self):
        """向后兼容：旧 extractor 的 facts 字段仍可解析。"""
        from hy_memory.pipelines.writer import MemoryWriter
        info = {"facts": [{"content": "用户喜欢篮球", "tags": ["sport"]}]}
        texts, meta = MemoryWriter._collect_new_memories(info)
        assert "用户喜欢篮球" in texts
        assert all(m["layer"] == "L2_FACT" for m in meta)

    def test_collect_new_memories_legacy_identity_to_l2(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {"identity": [{"content": "用户性格内向", "tags": []}]}
        texts, meta = MemoryWriter._collect_new_memories(info)
        assert "用户性格内向" in texts
        assert all(m["layer"] == "L2_FACT" for m in meta)

    def test_collect_intentions_parses_valid_until(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {
            "intentions": [
                {"content": "用户下周面试", "valid_until": "2099-01-01"},
                {"content": "用户想学吉他", "valid_until": None},
                {"content": "坏日期", "valid_until": "not-a-date"},
            ]
        }
        out = MemoryWriter._collect_intentions(info)
        assert len(out) == 3
        assert out[0]["valid_until"] is not None
        assert out[0]["valid_until"].year == 2099
        assert out[1]["valid_until"] is None
        assert out[2]["valid_until"] is None  # 坏日期降级 None


class TestOwner:
    """owner 字段：extractor→meta、intention、归一化、持久化 round-trip。"""

    def test_collect_new_memories_owner(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {"memory": [
            {"content": "用户喜欢篮球", "owner": "user"},
            {"content": "助手推荐了川菜馆", "owner": "agent"},
            {"content": "无 owner", "tags": []},
            {"content": "脏 owner", "owner": "robot"},
        ]}
        _, meta = MemoryWriter._collect_new_memories(info)
        owners = {m["content"]: m["owner"] for m in meta}
        assert owners["用户喜欢篮球"] == "user"
        assert owners["助手推荐了川菜馆"] == "agent"
        assert owners["无 owner"] is None       # 缺失 → None
        assert owners["脏 owner"] is None        # 非法 → None

    def test_collect_new_memories_owner_assistant_alias(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {"memory": [{"content": "x", "owner": "assistant"}]}
        _, meta = MemoryWriter._collect_new_memories(info)
        assert meta[0]["owner"] == "agent"   # mem0 风格 assistant → agent

    def test_collect_intentions_owner(self):
        from hy_memory.pipelines.writer import MemoryWriter
        info = {"intentions": [
            {"content": "用户下周面试", "owner": "user"},
            {"content": "8小时后提醒用户", "owner": "agent"},
        ]}
        out = MemoryWriter._collect_intentions(info)
        assert out[0]["owner"] == "user"
        assert out[1]["owner"] == "agent"

    def test_node_owner_roundtrip(self, store):
        n = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="助手推荐了科比纪录片", layer=MemoryLayer.L2_FACT,
            status=MemoryStatus.ACTIVE, owner="agent",
        )
        n.embedding = _emb()
        run(store.upsert(n))
        got = run(store.get_by_id(n.node_id))
        assert got is not None
        assert got.owner == "agent"

    def test_node_owner_empty_roundtrip(self, store):
        n = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="一条 summary", layer=MemoryLayer.L3_SUMMARY,
            status=MemoryStatus.ACTIVE,  # owner 留空
        )
        n.embedding = _emb()
        run(store.upsert(n))
        got = run(store.get_by_id(n.node_id))
        assert got is not None
        assert got.owner is None
