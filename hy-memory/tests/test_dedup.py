# -*- coding: utf-8 -*-
"""
记忆去重机制测试。

覆盖：
- dedup helper 纯函数：4 条删除规则 / 确定性保留 / 阈值边界 / 不重复不删；
- execute_dedup 编排：删库 + DEDUP log（含 extractor 的 delete_from_store=False）；
- 后端 get_embeddings：chroma 取向量非空；
- reconcile 候选去重端到端（chroma + fake LLM）：重复链头被删库 + 移出候选。
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.dedup import (
    DedupItem, plan_dedup, execute_dedup, get_dedup_threshold,
    group_items_by_owner,
)


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


_SAME = [1.0, 0.0, 0.0, 0.0]
_SAME2 = [0.999, 0.0010, 0.0, 0.0]
_DIFF = [0.0, 1.0, 0.0, 0.0]


class TestPlanDedupRules:
    def test_all_non_chain_keep_earliest(self):
        # 规则2：全非链，两条几乎相同 → 留 gmt 最早，删另一条；无关项不动
        r = plan_dedup([
            DedupItem("a", _SAME, content="打篮球", gmt_created=100),
            DedupItem("b", _SAME2, content="打篮球", gmt_created=200),
            DedupItem("c", _DIFF, content="喝茶", gmt_created=50),
        ])
        assert r["delete_ids"] == ["b"]
        assert r["kept_ids"] == ["a"]

    def test_one_head_keeps_head(self):
        # 规则3：1 链头 + 1 非链重复 → 留链头，删非链（即使链头 gmt 更晚）
        r = plan_dedup([
            DedupItem("h", _SAME, content="住横滨", is_chain_head=True,
                      gmt_created=300, chain_node_ids=["h", "old1"]),
            DedupItem("p", _SAME2, content="住横滨", gmt_created=100),
        ])
        assert r["delete_ids"] == ["p"]
        assert r["kept_ids"] == ["h"]

    def test_two_heads_cascade_delete_chain(self):
        # 规则4：2 链头重复 → 留 gmt 最早链头，删另一链头 + 连带其历史链
        r = plan_dedup([
            DedupItem("h1", _SAME, content="住横滨", is_chain_head=True,
                      gmt_created=100, chain_node_ids=["h1", "b1"]),
            DedupItem("h2", _SAME2, content="住横滨", is_chain_head=True,
                      gmt_created=200, chain_node_ids=["h2", "b2", "b3"]),
        ])
        assert r["kept_ids"] == ["h1"]
        assert sorted(r["delete_ids"]) == ["b2", "b3", "h2"]
        g = r["groups"][0]
        assert g["kept"]["reason"] == "earliest_chain_head"
        d = [x for x in g["deleted"] if x["node_id"] == "h2"][0]
        assert sorted(d["also_deleted_chain"]) == ["b2", "b3"]

    def test_no_duplicate_no_delete(self):
        r = plan_dedup([
            DedupItem("x", _SAME, gmt_created=1),
            DedupItem("y", _DIFF, gmt_created=2),
        ])
        assert r["delete_ids"] == []
        assert r["groups"] == []

    def test_chain_body_ignored(self):
        # is_latest=False（链身）不参与判重
        r = plan_dedup([
            DedupItem("a", _SAME, is_latest=True, gmt_created=1),
            DedupItem("body", _SAME, is_latest=False, gmt_created=2),
        ])
        assert r["delete_ids"] == []  # 只剩 1 个 is_latest，无重复

    def test_threshold_env(self, monkeypatch):
        monkeypatch.setenv("MEMORY_DEDUP_THRESHOLD", "0.5")
        assert abs(get_dedup_threshold() - 0.5) < 1e-9
        monkeypatch.delenv("MEMORY_DEDUP_THRESHOLD", raising=False)
        assert abs(get_dedup_threshold() - 0.95) < 1e-9


class _CaptureCache:
    def __init__(self):
        self.logs = []

    async def store_pipeline_log(self, **kw):
        self.logs.append(kw)


class _FakeStore:
    """记录 dedup 对存储的写操作。

    dedup 改为逻辑删除后走 update_payload 置 SHADOW，不再调 delete。保留
    delete() 方法用于断言"绝不硬删"。
    """

    def __init__(self):
        self.deleted = []
        self.payload_updates = []  # [(node_id, updates_dict), ...]

    async def delete(self, nid):
        self.deleted.append(nid)
        return True

    async def update_payload(self, node_id, updates):
        self.payload_updates.append((node_id, dict(updates)))
        return True

    @property
    def shadowed_ids(self):
        return [
            nid for nid, up in self.payload_updates
            if up.get("status") == "shadow"
        ]


class TestExecuteDedup:
    def test_shadows_and_logs(self):
        cache = _CaptureCache()
        store = _FakeStore()
        items = [
            DedupItem("a", _SAME, content="x", gmt_created=1),
            DedupItem("b", _SAME2, content="x", gmt_created=2),
        ]
        plan = run(execute_dedup(
            items, vector_store=store, cache=cache, trigger="reconcile",
            request_id="rq", user_id="u1", agent_id="a1", delete_from_store=True,
        ))
        assert plan["delete_ids"] == ["b"]
        # 逻辑删除：置 SHADOW，绝不硬删
        assert store.deleted == [], "dedup 不应硬删（不可恢复）"
        assert store.shadowed_ids == ["b"]
        _nid, _up = store.payload_updates[0]
        assert _up["status"] == "shadow"
        assert _up["is_latest"] is False
        # 审计字段：为什么不见了 + 被哪条取代
        assert _up["shadow_reason"] == "dedup:reconcile"
        assert _up["dedup_kept_id"] == "a"

        dedup_logs = [l for l in cache.logs if l["step"] == "DEDUP"]
        assert len(dedup_logs) == 1
        import json
        parsed = json.loads(dedup_logs[0]["parsed"])
        assert parsed["trigger"] == "reconcile"
        assert parsed["deleted_count"] == 1

    def test_extractor_no_store_delete(self):
        # extractor 阶段 delete_from_store=False：不删库，但仍记 log
        cache = _CaptureCache()
        store = _FakeStore()
        items = [
            DedupItem("0", _SAME, content="x", gmt_created=0),
            DedupItem("1", _SAME2, content="x", gmt_created=1),
        ]
        plan = run(execute_dedup(
            items, vector_store=store, cache=cache, trigger="extractor",
            request_id="rq", user_id="u1", agent_id="a1", delete_from_store=False,
        ))
        assert plan["delete_ids"] == ["1"]
        assert store.deleted == []  # 没删库
        assert store.payload_updates == []  # 也没置 SHADOW
        assert any(l["step"] == "DEDUP" for l in cache.logs)


class TestGroupItemsByOwner:
    """去重的隔离维度由 owner 决定，而不是无差别按 agent_id 切分。

    owner='user'（含空值）：记忆属于用户这一侧。同一用户在 agent_a / agent_b 下
      说的同一件事是同一条事实，必须同批判重，否则每个 agent 各存一份且永远
      无法合并（此前 reconcile 候选检索写死 agent_ids=[agent_id]，这两条根本
      不会出现在同一批里）。
    owner='agent'：不同 assistant 说过的话是独立记忆，即使语义相近也不应互删。
    """

    def _item(self, nid, *, owner=None, uid="u1", aid="a1", source="default"):
        return DedupItem(
            nid, _SAME, content="x", owner=owner, user_id=uid,
            agent_id=aid, source=source,
        )

    def test_owner_user_merges_across_agents(self):
        items = [
            self._item("n1", owner="user", aid="agent_a"),
            self._item("n2", owner="user", aid="agent_b"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="agent_b")
        assert len(batches) == 1, "owner=user 应跨 agent 合并成一批"
        assert batches[0]["owner"] == "user"
        assert sorted(i.node_id for i in batches[0]["items"]) == ["n1", "n2"]
        assert batches[0]["user_id"] == "u1"

    def test_owner_agent_isolated_per_agent(self):
        items = [
            self._item("n3", owner="agent", aid="agent_a"),
            self._item("n4", owner="agent", aid="agent_b"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="agent_b")
        # 各自单条 → 都不足 2 条，无从判重
        assert batches == [], "owner=agent 不同 agent 不应放进同一批"

    def test_owner_agent_same_agent_batched(self):
        items = [
            self._item("n5", owner="agent", aid="agent_a"),
            self._item("n6", owner="agent", aid="agent_a"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="agent_a")
        assert len(batches) == 1
        assert batches[0]["owner"] == "agent"
        assert batches[0]["agent_id"] == "agent_a"

    @pytest.mark.parametrize("owner", [None, "", "USER", "unknown-value"])
    def test_missing_or_unknown_owner_falls_back_to_user(self, owner):
        """owner 2026-06-16 才引入，老节点为空；LLM 也可能漏填/填错。

        全链路约定是 `owner or "user"`（extractor prompt / reconciler
        existing_mem_list 都如此），这里必须一致，否则历史数据会被划进
        agent 桶而丢失跨 agent 去重能力。
        """
        items = [
            self._item("n7", owner=owner, aid="agent_a"),
            self._item("n8", owner=owner, aid="agent_b"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="agent_b")
        assert len(batches) == 1
        assert batches[0]["owner"] == "user"

    def test_mixed_owners_split_into_separate_batches(self):
        items = [
            self._item("u_a", owner="user", aid="agent_a"),
            self._item("u_b", owner="user", aid="agent_b"),
            self._item("g_a1", owner="agent", aid="agent_a"),
            self._item("g_a2", owner="agent", aid="agent_a"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="agent_a")
        assert len(batches) == 2
        by_owner = {b["owner"]: b for b in batches}
        assert sorted(i.node_id for i in by_owner["user"]["items"]) == ["u_a", "u_b"]
        assert sorted(i.node_id for i in by_owner["agent"]["items"]) == ["g_a1", "g_a2"]

    def test_different_users_never_mixed(self):
        """多 user 检索（user_ids=[u1,u2]）时绝不能跨 user 判重。"""
        items = [
            self._item("x1", owner="user", uid="u1"),
            self._item("x2", owner="user", uid="u2"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="a1")
        assert batches == []

    def test_different_sources_never_mixed(self):
        items = [
            self._item("cursor", owner="user", source="cursor"),
            self._item("codex", owner="user", source="codex"),
        ]
        batches = group_items_by_owner(
            items, default_user_id="u1", default_agent_id="a1",
        )
        assert batches == []

    def test_same_source_still_batches(self):
        items = [
            self._item("codex-1", owner="user", source="Codex"),
            self._item("codex-2", owner="user", source=" codex "),
        ]
        batches = group_items_by_owner(
            items, default_user_id="u1", default_agent_id="a1",
        )
        assert len(batches) == 1
        assert batches[0]["source"] == "codex"

    def test_batch_carries_accurate_attribution(self):
        """DEDUP log 归属：此前调用方固定传 effective_*_ids[0]，跨 user 时记错。"""
        items = [
            self._item("y1", owner="user", uid="u2"),
            self._item("y2", owner="user", uid="u2"),
        ]
        batches = group_items_by_owner(items, default_user_id="u1", default_agent_id="a1")
        assert len(batches) == 1
        assert batches[0]["user_id"] == "u2", "应记实际归属的 user，而非调用方的第一个"

    def test_single_item_batch_dropped(self):
        items = [self._item("z1", owner="user")]
        assert group_items_by_owner(items, default_user_id="u1", default_agent_id="a1") == []


@pytest.fixture
def config(tmp_path):
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_dedup_{uuid.uuid4().hex[:8]}",
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


class TestBackendGetEmbeddings:
    def test_chroma_get_embeddings(self, store):
        e1, e2 = _emb(), _emb()
        for nid, e in [("a", e1), ("b", e2)]:
            n = MemoryNode(node_id=nid, user_id="u1", agent_id="a1", session_id="s1",
                           content="x", layer=MemoryLayer.L2_FACT,
                           status=MemoryStatus.ACTIVE, is_latest=True)
            n.embedding = e
            run(store.upsert(n))
        embs = run(store.get_embeddings(["a", "b", "missing"]))
        assert set(embs.keys()) == {"a", "b"}
        assert len(embs["a"]) == 32


class _CaptureLLM:
    def __init__(self):
        self.last_prompt = ""

    async def complete(self, prompt, **kw):
        self.last_prompt = prompt
        class R:
            content = "[]"
            prompt_tokens = 1
            completion_tokens = 1
            tokens_used = 2
        return R()


class _Embed:
    def __init__(self, vec):
        self._vec = vec

    async def embed(self, t):
        return list(self._vec)

    async def embed_batch(self, ts):
        return [list(self._vec) for _ in ts]

    async def embed_queued(self, t, use_cache=True):
        return list(self._vec)


class TestReconcileDedupE2E:
    def test_duplicate_candidates_shadowed(self, store, config):
        from hy_memory.agent.reconciler import MemoryReconciler
        shared = _emb()
        # 两条几乎相同的 ACTIVE L2 (非链)，都会被召回为候选
        for nid, days in [("m1", 30), ("m2", 5)]:
            n = MemoryNode(node_id=nid, user_id="u1", agent_id="default_agent",
                           session_id="s1", content="用户喜欢打篮球",
                           layer=MemoryLayer.L2_FACT, status=MemoryStatus.ACTIVE,
                           is_latest=True)
            n.memory_at = datetime.now() - timedelta(days=days)
            n.gmt_created = datetime.now() - timedelta(days=days)
            n.embedding = list(shared)
            run(store.upsert(n))

        recon = MemoryReconciler(config)
        recon._get_llm = lambda: _CaptureLLM()
        recon._enable_search_query = False
        run(recon.reconcile(
            new_memories=["用户爱打篮球"],
            user_id="u1", agent_id="default_agent",
            vector_store=store, embed_service=_Embed(shared),
            request_id="rq1",
        ))
        # 去重是逻辑删除：两个节点都还在库里，但只有 gmt 最早的 m1 仍 ACTIVE
        m1 = run(store.get_by_id("m1"))
        m2 = run(store.get_by_id("m2"))
        assert m1 is not None and m2 is not None, "dedup 不应硬删节点"
        assert m1.status == MemoryStatus.ACTIVE
        assert m1.is_latest is True
        assert m2.status == MemoryStatus.SHADOW, f"m2 应被逻辑删除，实际 {m2.status}"
        assert m2.is_latest is False

    def test_non_l2_l4_candidates_not_deduped(self, store, config):
        # L3_SUMMARY 重复候选不在去重范围（仅 L2+L4），不应被删
        from hy_memory.agent.reconciler import MemoryReconciler
        shared = _emb()
        for nid, days in [("s1n", 30), ("s2n", 5)]:
            n = MemoryNode(node_id=nid, user_id="u1", agent_id="default_agent",
                           session_id="s1", content="会话摘要内容",
                           layer=MemoryLayer.L3_SUMMARY, status=MemoryStatus.ACTIVE,
                           is_latest=True)
            n.memory_at = datetime.now() - timedelta(days=days)
            n.gmt_created = datetime.now() - timedelta(days=days)
            n.embedding = list(shared)
            run(store.upsert(n))

        recon = MemoryReconciler(config)
        recon._get_llm = lambda: _CaptureLLM()
        recon._enable_search_query = False
        run(recon.reconcile(
            new_memories=["新摘要"],
            user_id="u1", agent_id="default_agent",
            vector_store=store, embed_service=_Embed(shared),
            layers=[MemoryLayer.L3_SUMMARY],
            request_id="rq2",
        ))
        # L3 不参与去重 → 两条都还在，且都仍 ACTIVE。
        # 必须断言 status：dedup 改为逻辑删除后，节点被去重也依然 get_by_id 得到，
        # 只断言 "is not None" 已不足以证明"没被去重"。
        remain = [run(store.get_by_id("s1n")), run(store.get_by_id("s2n"))]
        assert all(n is not None for n in remain)
        assert all(n.status == MemoryStatus.ACTIVE for n in remain), (
            "L3_SUMMARY 不在去重范围，不应被置 SHADOW"
        )
