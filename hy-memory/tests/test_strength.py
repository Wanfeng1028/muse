# -*- coding: utf-8 -*-
"""
Memory Strength（基于 idle 的时间衰减排序）单元 + 集成测试。

覆盖：
- compute_strength 公式：新建满强度、冷启动退回 gmt_created、idle 衰减、access_count
  log 频次加权、access_count=0 不崩（log 守卫）。
- apply_strength_to_normal：profile / intention 层透传不衰减，normal 层乘进 strength。
- bump_access：access_count+1 / last_accessed_at 回写（chroma 端到端）。
- 持久化 round-trip：last_accessed_at upsert → get_by_id 保留。
- reader 集成：近期命中的 fact 在 strength 后排到陈旧 fact 前面（chroma）。
"""

import asyncio
import math
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.strength import (
    compute_strength,
    apply_strength_to_normal,
    bump_access,
    DEFAULT_TAU,
)


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


class _FakeNode:
    def __init__(self, *, access_count=0, last_accessed_at=None, gmt_created=None, layer=None):
        self.access_count = access_count
        self.last_accessed_at = last_accessed_at
        self.gmt_created = gmt_created
        self.layer = layer


class TestComputeStrength:
    def test_new_never_accessed_full_strength(self):
        now = datetime.now()
        n = _FakeNode(access_count=0, last_accessed_at=None, gmt_created=now)
        assert abs(compute_strength(n, now=now) - 1.0) < 1e-6

    def test_access_count_zero_no_crash(self):
        now = datetime.now()
        n = _FakeNode(access_count=0, last_accessed_at=now, gmt_created=now)
        # freq=1.0, idle=0 → strength=1.0
        assert abs(compute_strength(n, now=now) - 1.0) < 1e-6

    def test_idle_decay(self):
        now = datetime.now()
        n = _FakeNode(access_count=1, last_accessed_at=now - timedelta(days=365), gmt_created=now)
        expected = (1 + math.log(1)) * math.exp(-365 / DEFAULT_TAU)
        assert abs(compute_strength(n, now=now) - expected) < 1e-6

    def test_frequency_boost(self):
        now = datetime.now()
        n = _FakeNode(access_count=5, last_accessed_at=now - timedelta(days=1), gmt_created=now)
        expected = (1 + math.log(5)) * math.exp(-1 / DEFAULT_TAU)
        assert abs(compute_strength(n, now=now) - expected) < 1e-6
        assert compute_strength(n, now=now) > 1.0  # 高频近期 → strength > 1

    def test_cold_start_falls_back_to_created(self):
        now = datetime.now()
        # 从未访问，但 300 天前创建 → idle 用 gmt_created
        n = _FakeNode(access_count=0, last_accessed_at=None, gmt_created=now - timedelta(days=300))
        expected = 1.0 * math.exp(-300 / DEFAULT_TAU)
        assert abs(compute_strength(n, now=now) - expected) < 1e-6

    def test_recent_old_memory_beats_idle_old(self):
        """2023 创建但昨天命中，应强于创建近但久未命中的。"""
        now = datetime.now()
        kobe = _FakeNode(access_count=3, last_accessed_at=now - timedelta(days=1),
                         gmt_created=now - timedelta(days=1000))
        stale = _FakeNode(access_count=1, last_accessed_at=now - timedelta(days=300),
                          gmt_created=now - timedelta(days=10))
        assert compute_strength(kobe, now=now) > compute_strength(stale, now=now)


class TestApplyStrengthToNormal:
    def test_profile_and_intention_passthrough(self):
        now = datetime.now()
        old = now - timedelta(days=400)
        def mk(layer):
            return {"node": _FakeNode(access_count=1, last_accessed_at=old, gmt_created=old,
                                      layer=MemoryLayer.from_string(layer)),
                    "score": 1.0, "layer": layer}
        hits = [mk("l2_fact"), mk("l4_identity"), mk("l7_intention")]
        apply_strength_to_normal(
            hits,
            profile_layers={"l0_basic_info", "l4_identity"},
            intention_layers={"l7_intention"},
        )
        by_layer = {h["layer"]: h["score"] for h in hits}
        assert by_layer["l4_identity"] == 1.0   # profile 透传
        assert by_layer["l7_intention"] == 1.0   # intention 透传
        assert by_layer["l2_fact"] < 1.0         # normal 被衰减


@pytest.fixture
def store(tmp_path):
    config = MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_strength_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma_data"),
            "embedding_dims": 32,
        },
    })
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


class TestPersistenceAndBump:
    def test_last_accessed_at_roundtrip(self, store):
        laat = datetime.now() - timedelta(days=2)
        n = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="用户喜欢科比", layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
            last_accessed_at=laat, access_count=3,
        )
        n.embedding = _emb()
        run(store.upsert(n))
        got = run(store.get_by_id(n.node_id))
        assert got is not None
        assert got.access_count == 3
        assert got.last_accessed_at is not None
        # 精度到秒
        assert abs((got.last_accessed_at - laat).total_seconds()) < 2

    def test_bump_access_increments(self, store):
        n = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="用户在学吉他", layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
            access_count=2,
        )
        n.embedding = _emb()
        run(store.upsert(n))
        ok = run(bump_access(store, [(n.node_id, 2)]))
        assert ok == 1
        got = run(store.get_by_id(n.node_id))
        assert got.access_count == 3
        assert got.last_accessed_at is not None


class TestReaderStrengthRanking:
    """近期高频命中的 fact 经 strength 后排到陈旧 fact 之前。

    直接验证「真实 VDB 召回 + apply_strength_to_normal」这一 reader 核心步骤：
    两条同向量（语义分相等）的 L2 fact，strength 成为唯一区分。
    """

    def test_recent_fact_outranks_stale(self, store):
        now = datetime.now()
        shared_emb = _emb()
        recent = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="用户最近在追一部剧", layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
            access_count=10, last_accessed_at=now - timedelta(days=1),
        )
        stale = MemoryNode(
            node_id=str(uuid.uuid4()), user_id="u1", agent_id="a1", session_id="s1",
            content="用户以前看过一部剧", layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
            access_count=1, last_accessed_at=now - timedelta(days=400),
        )
        recent.embedding = list(shared_emb)
        stale.embedding = list(shared_emb)
        run(store.upsert(recent))
        run(store.upsert(stale))

        hits = run(store.search(
            query_embedding=list(shared_emb), user_ids=["u1"],
            layers=[MemoryLayer.L2_FACT], limit=10,
            status_filter=[MemoryStatus.ACTIVE], only_latest=True,
        ))
        assert {recent.node_id, stale.node_id} <= {h["node_id"] for h in hits}
        # 召回时语义分相等 → strength 前两者并列；strength 后 recent 必须更高
        apply_strength_to_normal(hits, score_key="score")
        hits.sort(key=lambda x: x["score"], reverse=True)
        ids = [h["node_id"] for h in hits]
        assert ids.index(recent.node_id) < ids.index(stale.node_id)
