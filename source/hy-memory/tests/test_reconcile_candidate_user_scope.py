# -*- coding: utf-8 -*-
"""reconcile 候选检索是 user 维度，不按 agent 收窄。

背景：候选检索此前写死 `agent_ids=[agent_id]`，而 writer 传下来的 agent_id
永不为空（`request.agent_id or "default_agent"`）。于是 reconcile 只能看到本
agent 的历史 —— 后果不只是去重失效，而是整个 reconcile 失效：

  用户在 agent_a 说"我是素食主义者" → 之后在 agent_b 说"我现在吃鱼了"
  → agent_b 这次搜不到 agent_a 那条 → LLM 拿不到候选 → 判 ADD 而非 SUPERSEDE
  → 库里两条矛盾的 user 记忆同时 ACTIVE

owner 和 agent_id 是两个正交维度：owner='user' 的记忆照样被打上写入时的
agent_id，所以"按 agent 隔离"对用户侧事实是多余且有害的。

向后兼容不靠"保持按 agent 过滤"，而是靠演化链的双向追溯：跨 agent SUPERSEDE
后新节点挂在 agent_b 名下，但 agent_a 的用户搜索仍能命中留在 agent_a 的旧节点
（status=SUPERSEDED 也在召回范围），再由 _trace_full_chain 沿 superseded_by
找到 agent_b 的链头并返回整链 —— 见 test_cross_agent_chain_still_recallable。
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus


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
            "collection_name": f"test_xagent_{uuid.uuid4().hex[:8]}",
            "persist_directory": str(tmp_path / "chroma"),
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


class _CaptureLLM:
    """捕获 reconcile prompt，用于断言候选是否进了 prompt。"""

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
        self._v = vec

    async def embed_batch(self, texts):
        return [list(self._v) for _ in texts]

    async def embed_queued(self, text, use_cache=True):
        return list(self._v)


def _l2(store, *, content, agent_id, owner="user", days=10, emb=None,
        status=MemoryStatus.ACTIVE, is_latest=True, supersedes=None):
    n = MemoryNode(
        user_id="u1", agent_id=agent_id, session_id="s1",
        layer=MemoryLayer.L2_FACT, content=content, owner=owner,
        status=status, is_latest=is_latest, supersedes=supersedes,
    )
    n.memory_at = datetime.now() - timedelta(days=days)
    n.gmt_created = datetime.now() - timedelta(days=days)
    n.embedding = emb or _emb()
    return run(store.upsert(n))


def _reconcile(config, store, *, agent_id, new_memories, emb):
    from hy_memory.agent.reconciler import MemoryReconciler
    recon = MemoryReconciler(config)
    llm = _CaptureLLM()
    recon._get_llm = lambda: llm
    recon._enable_search_query = False
    run(recon.reconcile(
        new_memories=new_memories,
        user_id="u1", agent_id=agent_id,
        vector_store=store, embed_service=_Embed(emb),
        request_id="rq",
    ))
    return llm


class TestCandidateScopeIsUser:
    def test_other_agent_user_memory_enters_candidates(self, config, store):
        """agent_a 写的 owner=user 记忆，必须出现在 agent_b 的 reconcile 候选里。"""
        shared = _emb()
        _l2(store, content="用户是素食主义者", agent_id="agent_a", emb=shared)

        llm = _reconcile(
            config, store, agent_id="agent_b",
            new_memories=["用户现在开始吃鱼了"], emb=shared,
        )
        assert "素食主义者" in llm.last_prompt, (
            "跨 agent 的 owner=user 候选未进 prompt —— reconcile 仍被 agent 隔离"
        )

    def test_other_agent_agent_owned_memory_also_recalled(self, config, store):
        """owner=agent 的跨 agent 记忆也会进候选（不在候选侧过滤）。

        跨 owner 的约束由 RECONCILE_PROMPT 的
        "NEVER merge or supersede across different owners" 保证；
        去重侧则由 group_items_by_owner 按 agent 隔离。
        候选侧不做 owner 过滤 —— 这是明确的设计选择，锁在这里防止被"顺手优化"掉。
        """
        shared = _emb()
        _l2(store, content="助手为用户推荐了京都的一家旅馆",
            agent_id="agent_a", owner="agent", emb=shared)

        llm = _reconcile(
            config, store, agent_id="agent_b",
            new_memories=["助手为用户推荐了大阪的一家旅馆"], emb=shared,
        )
        assert "京都" in llm.last_prompt

    def test_other_user_memory_never_enters_candidates(self, config, store):
        """放宽的是 agent 维度，user 隔离必须仍然严格。"""
        shared = _emb()
        n = MemoryNode(
            user_id="u_other", agent_id="agent_a", session_id="s1",
            layer=MemoryLayer.L2_FACT, content="另一个用户的秘密",
            owner="user", status=MemoryStatus.ACTIVE, is_latest=True,
        )
        n.memory_at = datetime.now()
        n.gmt_created = datetime.now()
        n.embedding = list(shared)
        run(store.upsert(n))

        llm = _reconcile(
            config, store, agent_id="agent_b",
            new_memories=["用户喜欢打篮球"], emb=shared,
        )
        assert "另一个用户的秘密" not in llm.last_prompt, "绝不能跨 user 召回候选"

    def test_same_agent_candidate_still_works(self, config, store):
        """本 agent 的候选照常召回（防止放宽后误伤原有路径）。"""
        shared = _emb()
        _l2(store, content="用户喜欢打篮球", agent_id="agent_b", emb=shared)

        llm = _reconcile(
            config, store, agent_id="agent_b",
            new_memories=["用户爱打篮球"], emb=shared,
        )
        assert "打篮球" in llm.last_prompt


class TestBackwardCompatibility:
    def test_cross_agent_chain_still_recallable(self, store):
        """跨 agent SUPERSEDE 后，按 agent_a 搜索仍能拿到演化后的最新值。

        这是"新节点 agent_id 记当前 agent"这个决定的兼容性依据：
          - VDB filter 按 agent_a 只捞到留在 agent_a 的旧节点（SUPERSEDED）
          - _trace_full_chain 沿 superseded_by 双向追溯到 agent_b 的链头
          - 返回链头为代表 + 完整 evolution_chain
        """
        from hy_memory.pipelines._retrieval.evolution import expand_evolution_chains

        shared = _emb()
        old_id = _l2(store, content="用户是素食主义者", agent_id="agent_a",
                     emb=shared, days=30,
                     status=MemoryStatus.SUPERSEDED, is_latest=False)
        new_id = _l2(store, content="用户现在吃鱼", agent_id="agent_b",
                     emb=shared, days=1, supersedes=[old_id])
        run(store.update_payload(old_id, {"superseded_by": [new_id]}))

        # 按 agent_a 搜索（业务显式传 agent_ids=['agent_a']）
        hits = run(store.search(
            query_embedding=shared, user_id="u1", agent_ids=["agent_a"],
            layers=[MemoryLayer.L2_FACT], limit=10, score_threshold=0.0,
            status_filter=[MemoryStatus.ACTIVE, MemoryStatus.SUPERSEDED],
            only_latest=False,
        ))
        assert [h["node"].node_id for h in hits] == [old_id], \
            "agent_a 的 filter 只应命中 agent_a 的节点"

        expanded = run(expand_evolution_chains(
            store, [h for h in hits if h.get("node")]
        ))
        assert len(expanded) == 1
        rep = expanded[0]["node"]
        # 代表节点是 agent_b 的链头 —— 拿到的是演化后的正确值
        assert rep.node_id == new_id
        assert rep.agent_id == "agent_b"
        assert rep.content == "用户现在吃鱼"
        # 整条链都返回，历史可见
        contents = [c["content"] for c in expanded[0]["evolution_chain"]]
        assert contents == ["用户现在吃鱼", "用户是素食主义者"]
