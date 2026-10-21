"""created_after 按**事件时间**过滤的回归测试。

修复的 bug：过滤字段原为 `gmt_created`（落库时间），批量灌入场景下所有记忆的
gmt_created 几乎同一时刻，导致时间过滤完全失效。改为按 `memory_at`（事件时间），
`memory_at` 为空才回退 `gmt_created`。

覆盖：
- payload 级 helper（Chroma / FAISS post-filter 用）
- hit 级 helper（reader 末端兜底用）
- 关键场景：批量灌入（gmt_created 全部=今天，memory_at 跨年）
"""

from datetime import datetime, timedelta

import pytest

from hy_memory.data.vector_store_base import (
    node_effective_time,
    passes_created_after,
)
from hy_memory.pipelines._retrieval.temporal import (
    filter_hits_by_created_after,
    hit_effective_ts,
)
from hy_memory.models.memory import MemoryNode, MemoryLayer


NOW = datetime(2026, 9, 12, 12, 0, 0)
LAST_YEAR = datetime(2025, 3, 1, 12, 0, 0)
CUTOFF = datetime(2026, 1, 1, 0, 0, 0).timestamp()


# ================================================================
# payload 级（Chroma / FAISS）
# ================================================================

class TestNodeEffectiveTime:
    def test_prefers_memory_at(self):
        payload = {"memory_at": 100.0, "gmt_created": 999.0}
        assert node_effective_time(payload) == 100.0

    def test_falls_back_to_gmt_created_when_none(self):
        assert node_effective_time({"memory_at": None, "gmt_created": 999.0}) == 999.0

    def test_falls_back_when_empty_string(self):
        # Chroma 不支持 None，_payload_to_chroma_metadata 把空值写成 ""
        assert node_effective_time({"memory_at": "", "gmt_created": 999.0}) == 999.0

    def test_none_when_both_missing(self):
        assert node_effective_time({}) is None
        assert node_effective_time({"memory_at": "", "gmt_created": ""}) is None

    def test_ignores_unparseable(self):
        assert node_effective_time({"memory_at": "not-a-number", "gmt_created": 7.0}) == 7.0


class TestPassesCreatedAfter:
    def test_no_filter_passes_everything(self):
        assert passes_created_after({"memory_at": 1.0}, None) is True
        assert passes_created_after({"memory_at": 1.0}, 0) is True

    def test_filters_on_event_time(self):
        old = {"memory_at": LAST_YEAR.timestamp(), "gmt_created": NOW.timestamp()}
        new = {"memory_at": NOW.timestamp(), "gmt_created": NOW.timestamp()}
        assert passes_created_after(old, CUTOFF) is False
        assert passes_created_after(new, CUTOFF) is True

    def test_bulk_ingest_scenario(self):
        """核心回归：批量灌入时 gmt_created 全部=今天，只有 memory_at 能区分。"""
        ingested_now = NOW.timestamp()
        payloads = [
            {"memory_at": (LAST_YEAR + timedelta(days=d)).timestamp(),
             "gmt_created": ingested_now}
            for d in range(0, 600, 60)
        ]
        kept = [p for p in payloads if passes_created_after(p, CUTOFF)]
        # 按 gmt_created 过滤会全部通过（旧 bug）；按 memory_at 只留 cutoff 之后的
        assert 0 < len(kept) < len(payloads)
        assert all(p["memory_at"] >= CUTOFF for p in kept)

    def test_missing_time_is_kept(self):
        """两个时间字段都取不到时保留 —— 不因缺字段静默丢数据。"""
        assert passes_created_after({}, CUTOFF) is True

    def test_null_memory_at_uses_gmt_created(self):
        """L0_BASIC_INFO 这类旁路写入历史数据 memory_at 为空，行为与改动前一致。"""
        old_l0 = {"memory_at": None, "gmt_created": LAST_YEAR.timestamp()}
        new_l0 = {"memory_at": None, "gmt_created": NOW.timestamp()}
        assert passes_created_after(old_l0, CUTOFF) is False
        assert passes_created_after(new_l0, CUTOFF) is True


# ================================================================
# hit 级（reader 末端兜底）
# ================================================================

def _hit(memory_at=None, gmt_created=None, node=True, score=0.9):
    if not node:
        return {"node": None, "score": score,
                "memory_at": memory_at, "gmt_created": gmt_created}
    return {
        "node": MemoryNode(
            node_id="n1", content="c", layer=MemoryLayer.L2_FACT,
            memory_at=memory_at, gmt_created=gmt_created,
        ),
        "score": score,
    }


class TestHitEffectiveTs:
    def test_prefers_node_memory_at(self):
        h = _hit(memory_at=LAST_YEAR, gmt_created=NOW)
        assert hit_effective_ts(h) == LAST_YEAR.timestamp()

    def test_falls_back_to_node_gmt_created(self):
        h = _hit(memory_at=None, gmt_created=NOW)
        assert hit_effective_ts(h) == NOW.timestamp()

    def test_graph_hit_without_node(self):
        # graph 通道结果 node=None，字段挂在 hit dict 上（可能是 unix 秒）
        h = _hit(memory_at=LAST_YEAR.timestamp(), node=False)
        assert hit_effective_ts(h) == LAST_YEAR.timestamp()

    def test_none_when_nothing_available(self):
        assert hit_effective_ts({"node": None, "score": 0.5}) is None


class TestFilterHitsByCreatedAfter:
    def test_no_filter_returns_input(self):
        hits = [_hit(memory_at=LAST_YEAR)]
        assert filter_hits_by_created_after(hits, None) is hits

    def test_empty_input(self):
        assert filter_hits_by_created_after([], CUTOFF) == []

    def test_filters_by_event_time_not_write_time(self):
        hits = [
            _hit(memory_at=LAST_YEAR, gmt_created=NOW),  # 事件旧、写入新 → 应被过滤
            _hit(memory_at=NOW, gmt_created=NOW),
        ]
        out = filter_hits_by_created_after(hits, CUTOFF)
        assert len(out) == 1
        assert out[0]["node"].memory_at == NOW

    def test_keeps_hits_without_any_time(self):
        hits = [{"node": None, "score": 0.5}]
        assert filter_hits_by_created_after(hits, CUTOFF) == hits

    def test_boundary_is_inclusive(self):
        boundary = datetime.fromtimestamp(CUTOFF)
        out = filter_hits_by_created_after([_hit(memory_at=boundary)], CUTOFF)
        assert len(out) == 1


# ================================================================
# Qdrant 端到端：嵌套 should + IsNull 过滤器
# ================================================================

@pytest.mark.asyncio
async def test_qdrant_filters_on_event_time_end_to_end(tmp_path):
    """Qdrant 侧下推过滤的真实行为（嵌套 should + IsNullCondition）。

    过滤器写错会让主后端所有带 created_after 的查询直接崩，所以必须端到端验证。
    """
    from hy_memory.config import MemoryConfig, VectorStoreConfig
    from hy_memory.data.vector_store_qdrant import QdrantVectorStore

    cfg = MemoryConfig()
    cfg.vector_store = VectorStoreConfig(
        provider="qdrant",
        persist_directory=str(tmp_path),
        collection_name="test_created_after",
        embedding_dims=4,
    )
    vs = QdrantVectorStore(cfg)
    await vs.initialize()

    def _node(nid, memory_at, gmt_created):
        return MemoryNode(
            node_id=nid, user_id="u1", agent_id="a1", session_id="s1",
            layer=MemoryLayer.L2_FACT, content=f"fact {nid}",
            memory_at=memory_at, gmt_created=gmt_created,
            embedding=[1.0, 0.0, 0.0, 0.0],
        )

    try:
        # 批量灌入场景：gmt_created 全是"今天"，只有 memory_at 能区分事件时间
        await vs.upsert(_node("old_event", LAST_YEAR, NOW))
        await vs.upsert(_node("new_event", NOW, NOW))
        # memory_at 为空的旁路节点 → 回退 gmt_created
        await vs.upsert(_node("nullma_old", None, LAST_YEAR))
        await vs.upsert(_node("nullma_new", None, NOW))

        async def _ids(created_after):
            res = await vs.search(
                query_embedding=[1.0, 0.0, 0.0, 0.0], user_id="u1",
                limit=10, score_threshold=0.0, created_after=created_after,
            )
            return sorted(r["node_id"] for r in res)

        assert await _ids(None) == [
            "new_event", "nullma_new", "nullma_old", "old_event",
        ]
        # old_event 的 gmt_created 是"今天" —— 旧实现按 gmt_created 过滤会漏放它
        assert await _ids(CUTOFF) == ["new_event", "nullma_new"]
    finally:
        await vs.close()


# ================================================================
# L0 旁路写入现在会带上 memory_at
# ================================================================

@pytest.mark.asyncio
async def test_basic_profile_node_carries_memory_at(monkeypatch):
    """upsert_basic_profile 建的 L0 节点必须带 memory_at（消除 null 源）。"""
    from hy_memory.agent.tools import basic_profile as bp

    captured = {}

    class _FakeVS:
        async def list_by_user(self, **kw):
            return []
        async def get_by_ids(self, ids):
            return []
        async def upsert(self, node):
            captured["node"] = node
            return node.node_id
        async def update_payload(self, nid, updates):
            return True

    class _FakeEmbed:
        async def embed_queued(self, text):
            return [0.1, 0.2, 0.3]

    res = await bp.upsert_basic_profile(
        user_id="u1",
        kv={"name": "Tim"},
        vector_store=_FakeVS(),
        embed_service=_FakeEmbed(),
        allowed_fields=["name"],
    )

    assert res.success, res.error
    node = captured.get("node")
    assert node is not None, "upsert 未被调用"
    assert node.layer == MemoryLayer.L0_BASIC_INFO
    assert node.memory_at is not None
