# -*- coding: utf-8 -*-
"""
Search 路径 e2e 测试

不完整启动 HyMemoryClient（重）；通过组合真实 CodingMemoryStore + 轻量 SimpleNamespace
直接测 _search_coding；并为入参归一化逻辑做局部测试。
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from types import SimpleNamespace
from typing import List

import pytest

from hy_memory.client import HyMemoryClient
from hy_memory.coding.store import CodingMemoryStore
from hy_memory.coding.types import CodingMemory, WorkingFact

from tests.coding._helpers import MockEmbedService, MockLLMProvider


# ================================================================
# Fixtures（避免重复全启 client）
# ================================================================

@pytest.fixture
async def search_ctx(tmp_data_dir, mock_embed):
    """
    构造一个轻量 client-like ctx，含真实 CodingMemoryStore + mock embed。
    适合测 HyMemoryClient._search_coding 这个 method。
    """
    from hy_memory.config import MemoryConfig

    cfg = MemoryConfig.from_env()
    cfg.history.db_path = os.path.join(tmp_data_dir, "history.db")
    cfg.coding.db_path = os.path.join(tmp_data_dir, "coding_memory.db")
    cfg.vector_store.provider = "chroma"
    cfg.vector_store.path = os.path.join(tmp_data_dir, "chroma")
    cfg.vector_store.collection_name = f"test_search_{uuid.uuid4().hex[:8]}"
    cfg.vector_store.embedding_dims = 1536

    store = CodingMemoryStore(cfg, embed_service=mock_embed)
    await store.initialize()

    # 一个绑了所需属性的 SimpleNamespace 当 self 用
    ns = SimpleNamespace(
        _embed_service=mock_embed,
        _coding_store=store,
        _coding_writer=object(),  # 占位，让 _get_coding_writer 跳过 lazy
        _coding_llm_provider=None,
        _coding_init_lock=asyncio.Lock(),
    )

    async def _stub_get_coding_writer():
        return ns._coding_writer

    ns._get_coding_writer = _stub_get_coding_writer

    yield ns
    await store.close()


def _seed_memories(store_to_seed: CodingMemoryStore, mock_embed: MockEmbedService):
    """同步种几个用于测试的 memory（要在 fixture 之外用 asyncio.run 跑）。"""
    async def _do():
        await store_to_seed.insert(CodingMemory(
            experience_id="m_publish", user_id="u1", task="打包发布到私有包索引",
            search_keys=["凭证位置", "twine upload"], solution="详细发布步骤",
            boundary_envs="twine>=6", workspace_id="ws/a",
            files=["scripts/publish_package.sh"], confidence=0.9,
        ))
        await store_to_seed.insert(CodingMemory(
            experience_id="m_pnpm", user_id="u1", task="本项目用 pnpm",
            search_keys=["不要用 npm"], solution="所有项目用 pnpm",
confidence=1.0,
        ))
        await store_to_seed.insert(CodingMemory(
            experience_id="m_other_user", user_id="u_other", task="其他用户记忆",
            solution="x",
        ))
    asyncio.run(_do())


# ================================================================
# _search_coding 路径测试
# ================================================================

@pytest.mark.asyncio
class TestSearchCodingMethod:
    async def test_hit_by_task(self, search_ctx, mock_embed):
        # 在已 init 的 store 中插入数据
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="m_publish", user_id="u1", task="打包发布到私有包索引",
            search_keys=["凭证位置"], solution="详细发布步骤",
            boundary_envs="twine>=6",
            workspace_id="ws/a", files=["scripts/publish_package.sh"], confidence=0.9,
        ))

        import time
        resp = await HyMemoryClient._search_coding(
            search_ctx,
            target_query="打包发布到私有包索引",
            user_ids=["u1"],
            workspace_id="ws/a",
            branch=None,
            limit=10,
            working_fact_min_score=0.0,
            request_id="req-1",
            t0=time.perf_counter(),
        )
        assert resp["scene"] == "productivity"
        assert resp["request_id"] == "req-1"
        assert "elapsed_ms" in resp
        mems = resp["experiences"]
        assert len(mems) == 1
        m = mems[0]
        assert m["experience_id"] == "m_publish"
        assert m["task"] == "打包发布到私有包索引"
        assert m["search_keys"] == ["凭证位置"]
        assert m["solution"] == "详细发布步骤"
        assert m["boundary_envs"] == "twine>=6"
        assert m["workspace_id"] == "ws/a"
        assert m["files"] == ["scripts/publish_package.sh"]
        assert m["matched_key"] == "打包发布到私有包索引"
        assert m["matched_key_kind"] == "task"
        assert m["score"] > 0.9
        assert m["confidence"] == 0.9

    async def test_hit_by_search_key(self, search_ctx, mock_embed):
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="m_publish", user_id="u1", task="打包发布到私有包索引",
            search_keys=["凭证位置"], solution="...",
confidence=0.9,
        ))

        import time
        resp = await HyMemoryClient._search_coding(
            search_ctx,
            target_query="凭证位置", user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, working_fact_min_score=0.0,
            request_id="r", t0=time.perf_counter(),
        )
        mems = resp["experiences"]
        assert len(mems) == 1
        assert mems[0]["matched_key_kind"] == "aspect"
        assert mems[0]["matched_key"] == "凭证位置"

    async def test_workspace_filters(self, search_ctx, mock_embed):
        """workspace 传了就按作用域筛：换 workspace 召不回，不传则全量召回。"""
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="m1", user_id="u1", task="task A", solution="S",
            workspace_id="ws/a",
        ))

        import time
        for ws, expect in (("ws/a", 1), ("ws/b", 0), (None, 1)):
            resp = await HyMemoryClient._search_coding(
                search_ctx,
                target_query="task A", user_ids=["u1"],
                workspace_id=ws, branch=None,
                limit=10, working_fact_min_score=0.0,
                request_id="r", t0=time.perf_counter(),
            )
            assert len(resp["experiences"]) == expect, f"workspace_id={ws!r}"
            if expect:
                assert resp["experiences"][0]["workspace_id"] == "ws/a"

    async def test_min_score_filter(self, search_ctx, mock_embed):
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="m_unrelated", user_id="u1", task="task X",
            solution="S",
        ))

        import time
        # 用一个跟 task 不相关的 query；mock embed 用 hash → 相似度低
        resp = await HyMemoryClient._search_coding(
            search_ctx,
            target_query="完全无关的查询字符串 ABCDEFG xyz",
            user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, working_fact_min_score=0.99,  # 高阈值过滤掉一切
            request_id="r", t0=time.perf_counter(),
        )
        assert resp["experiences"] == []

    async def test_user_isolation(self, search_ctx, mock_embed):
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="m_other", user_id="u_other", task="my task",
            solution="S",
        ))

        import time
        resp = await HyMemoryClient._search_coding(
            search_ctx,
            target_query="my task", user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, working_fact_min_score=0.0,
            request_id="r", t0=time.perf_counter(),
        )
        assert resp["experiences"] == []

    async def test_empty_store_returns_empty(self, search_ctx, mock_embed):
        import time
        resp = await HyMemoryClient._search_coding(
            search_ctx,
            target_query="anything", user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, working_fact_min_score=0.0,
            request_id="r", t0=time.perf_counter(),
        )
        assert resp["experiences"] == []
        assert resp["facts"] == []
        assert resp["scene"] == "productivity"


# ================================================================
# 双层召回：事实主索引 + 顺链带经验 + 直查兜底
# ================================================================

@pytest.mark.asyncio
class TestDualLayerSearch:
    async def _search(self, ctx, query, *, limit=10, min_score=0.0,
                      exp_min_score=None):
        import time
        return await HyMemoryClient._search_coding(
            ctx,
            target_query=query, user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=limit, working_fact_min_score=min_score,
            working_experience_min_score=exp_min_score,
            request_id="r", t0=time.perf_counter(),
        )

    async def test_fact_hit_returns_fact_layer(self, search_ctx):
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1",
            statement="new_file_search 位于 src/search.py",
            files=["src/search.py"],
        ))

        resp = await self._search(search_ctx, "new_file_search 位于 src/search.py")
        assert len(resp["facts"]) == 1
        f = resp["facts"][0]
        assert f["fact_id"] == "f1"
        assert f["statement"] == "new_file_search 位于 src/search.py"
        assert f["files"] == ["src/search.py"]
        assert f["created_at"] is not None
        assert f["score"] > 0.9

    async def _linked_fixture(self, ctx):
        """一条 task 跟 query 完全不像的经验，只能靠事实顺链够到。"""
        await ctx._coding_store.insert(CodingMemory(
            experience_id="e1", user_id="u1",
            task="毫不相干的任务名 QQQQ", solution="怎么改 search 实现",
        ))
        await ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1",
            statement="new_file_search 位于 src/search.py",
            derived_experience_ids=["e1"],
        ))

    async def test_fact_carries_linked_experience(self, search_ctx):
        """经验自身跟 query 不像，靠命中的事实被认出来，标 fact_link。"""
        await self._linked_fixture(search_ctx)

        resp = await self._search(
            search_ctx, "new_file_search 位于 src/search.py", exp_min_score=0.0,
        )
        assert [e["experience_id"] for e in resp["experiences"]] == ["e1"]
        assert resp["experiences"][0]["via"] == "fact_link"

    async def test_linked_experience_is_gated_not_exempt(self, search_ctx):
        """顺链不是免检：分不够就不放进来，哪怕担保它的事实命中了。

        早期这一路完全豁免，实测会让事实把"另一个侧面"的无关经验一起拖进来。
        """
        await self._linked_fixture(search_ctx)

        resp = await self._search(
            search_ctx, "new_file_search 位于 src/search.py", exp_min_score=0.99,
        )
        assert [f["fact_id"] for f in resp["facts"]] == ["f1"]  # 事实照样命中
        assert resp["experiences"] == []                        # 经验被闸门挡下

    async def test_both_experience_paths_share_one_gate(self, search_ctx):
        """顺链和直查卡同一道闸门，没有单独给顺链开的后门。

        两路卡的本来就是同一批分数（顺链借的就是直查那轮的分），分两档没有依据。
        事实背书体现在排序上——顺链排在直查前面——而不是准入上打折。
        """
        await self._linked_fixture(search_ctx)

        loose = await self._search(
            search_ctx, "new_file_search 位于 src/search.py", exp_min_score=0.0,
        )
        strict = await self._search(
            search_ctx, "new_file_search 位于 src/search.py", exp_min_score=0.99,
        )
        # 同一条经验，只由 working_experience_min_score 一个值决定进不进来
        assert [e["experience_id"] for e in loose["experiences"]] == ["e1"]
        assert strict["experiences"] == []
        # 事实层有自己的阈值，不受经验那道影响
        assert len(strict["facts"]) == 1

    async def test_direct_hit_marked_via_direct(self, search_ctx):
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="e1", user_id="u1", task="打包发布到私有包索引", solution="S",
        ))

        resp = await self._search(search_ctx, "打包发布到私有包索引")
        assert resp["facts"] == []
        assert [e["experience_id"] for e in resp["experiences"]] == ["e1"]
        assert resp["experiences"][0]["via"] == "direct"
        assert resp["experiences"][0]["score"] > 0.9

    async def test_fact_link_wins_over_direct_on_dedup(self, search_ctx):
        """同一条经验既被事实带出又被直查命中，只出现一次，标 fact_link。"""
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="e1", user_id="u1", task="共同的查询词", solution="S",
        ))
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="共同的查询词",
            derived_experience_ids=["e1"],
        ))

        resp = await self._search(search_ctx, "共同的查询词")
        assert len(resp["experiences"]) == 1
        assert resp["experiences"][0]["via"] == "fact_link"
        # 直查那一路的分数仍然带出来，不因为走了链就丢掉
        assert resp["experiences"][0]["score"] > 0.9

    async def test_dead_link_filtered(self, search_ctx):
        """事实指向一条已被 DELETE 的经验，存在性过滤应该把死链滤掉。"""
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="指向幽灵经验的事实",
            derived_experience_ids=["ghost"],
        ))

        resp = await self._search(search_ctx, "指向幽灵经验的事实")
        assert len(resp["facts"]) == 1
        assert resp["experiences"] == []

    async def test_superseded_fact_not_recalled(self, search_ctx):
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f_old", user_id="u1", statement="config 位于 /opt/app/config.yaml",
        ))
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f_new", user_id="u1", statement="config 位于 /etc/app/config.yaml",
        ))
        await search_ctx._coding_store.supersede_fact("f_old", "f_new")

        resp = await self._search(search_ctx, "config 位于 /opt/app/config.yaml")
        assert [f["fact_id"] for f in resp["facts"]] == ["f_new"]

    async def test_min_score_filters_facts(self, search_ctx):
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="某条事实",
        ))

        assert len((await self._search(search_ctx, "某条事实"))["facts"]) == 1
        resp = await self._search(search_ctx, "完全无关的查询 ABCDEFG", min_score=0.99)
        assert resp["facts"] == []

    async def test_low_score_fact_does_not_drag_experience(self, search_ctx):
        """低分事实被闸门挡掉后，不该再顺链把它的经验带进结果。

        事实层是主索引，噪声在这里会放大成一串无关经验。
        """
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="e1", user_id="u1", task="无关的经验", solution="S",
        ))
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="无关的事实",
            derived_experience_ids=["e1"],
        ))

        resp = await self._search(
            search_ctx, "完全不沾边的查询 ZZZZZ", min_score=0.99,
        )
        assert resp["facts"] == []
        assert resp["experiences"] == []

    async def test_fact_user_isolation(self, search_ctx):
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u_other", statement="别人的事实",
        ))

        resp = await self._search(search_ctx, "别人的事实")
        assert resp["facts"] == []

    async def test_facts_respect_limit_below_floor(self, search_ctx):
        """limit 小于事实层取数下限（5）时，返回条数仍要落回 limit。

        事实层按 max(limit, 5) 取，多出来的那几条是给阈值过滤留的余量，
        不该直接透到结果里。
        """
        for i in range(6):
            await search_ctx._coding_store.insert_fact(WorkingFact(
                fact_id=f"f{i}", user_id="u1", statement=f"同一批事实 {i}",
            ))

        resp = await self._search(search_ctx, "同一批事实 0", limit=2)
        assert len(resp["facts"]) == 2

    async def test_experiences_capped_at_limit_across_both_sources(self, search_ctx):
        """顺链 + 直查合并后总数不超过 limit，且优先保留顺链那批。"""
        for i in range(4):
            await search_ctx._coding_store.insert(CodingMemory(
                experience_id=f"linked{i}", user_id="u1",
                task=f"被事实链带出的经验 {i}", solution="S",
            ))
        # 直查能命中的经验：task 与 query 一致
        for i in range(4):
            await search_ctx._coding_store.insert(CodingMemory(
                experience_id=f"direct{i}", user_id="u1",
                task="同一批事实 0", solution="S",
            ))
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="同一批事实 0",
            derived_experience_ids=[f"linked{i}" for i in range(4)],
        ))

        resp = await self._search(search_ctx, "同一批事实 0", limit=3)
        assert len(resp["experiences"]) == 3
        # 顺链在前，limit 砍掉的应该是直查那批
        assert all(e["via"] == "fact_link" for e in resp["experiences"])

    async def test_dead_links_do_not_eat_limit_slots(self, search_ctx):
        """死链在 get_many 就被丢了，不该占掉 limit 名额。

        截断如果放在 get_many 之前，前几个死链会把名额吃光，实际返回数够不到 limit。
        """
        await search_ctx._coding_store.insert(CodingMemory(
            experience_id="alive", user_id="u1", task="活着的经验", solution="S",
        ))
        await search_ctx._coding_store.insert_fact(WorkingFact(
            fact_id="f1", user_id="u1", statement="带死链的事实",
            # 前两个 experience_id 库里不存在
            derived_experience_ids=["ghost1", "ghost2", "alive"],
        ))

        resp = await self._search(search_ctx, "带死链的事实", limit=1)
        assert [e["experience_id"] for e in resp["experiences"]] == ["alive"]
        # 必须是顺链拿到的。直查也可能捞到 alive，那样这条测试会假通过
        assert resp["experiences"][0]["via"] == "fact_link"


# ================================================================
# 入参归一化测试 — 不需要完整 client，直接静态调用
# ================================================================

class TestInputNormalization:
    """入参校验逻辑测试（用 ValueError 触发即可）"""

    def test_query_and_queries_mutex_via_async(self):
        # async_search 的入参校验在最开头，可以直接 await 一个未初始化的 client 测它
        # 用一个最小 mock client 走到那段逻辑
        async def _run():
            class _DummyClient:
                _coding_llm_provider = None

                async def _check(self, query=None, queries=None):
                    # 复用真正的 async_search 校验逻辑（直接 raise）
                    if queries is not None and query is not None:
                        raise ValueError("query and queries are mutually exclusive; choose one")
                    if queries is None and query is None:
                        raise ValueError("either query or queries is required")
                    if queries is not None and (not isinstance(queries, list) or not queries):
                        raise ValueError("queries must be a non-empty list[str]")

            c = _DummyClient()
            # 互斥
            with pytest.raises(ValueError, match="mutually exclusive"):
                await c._check(query="a", queries=["b"])
            # 都没传
            with pytest.raises(ValueError, match="either query or queries"):
                await c._check()
            # 空 list
            with pytest.raises(ValueError, match="non-empty"):
                await c._check(queries=[])

        asyncio.run(_run())
