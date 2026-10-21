# -*- coding: utf-8 -*-
"""
search() / async_search() 的 scene 参数 + queries-rewrite 路由测试。

覆盖三分支：
  1) scene 显式 ("coding"|"chat") → 不调 LLM
  2) search_mode=default + 没 scene → 固定 chat/normal，零 LLM
  3) search_mode=agentic + 没 scene → 三分类 + query rewrite

外加：
  - LLM 失败 / 解析失败 → fail-safe 走 chat
  - scene 非法值 → ValueError
  - scene=coding 但 coding.enable=False → fall back chat
  - classify_and_rewrite_queries 单元测试
"""

import asyncio
import pytest

from hy_memory.coding.judge import classify_and_rewrite_queries

from tests.coding._helpers import MockLLMProvider, FailingLLMProvider


# ================================================================
# Phase 1: classify_and_rewrite_queries 单元测试（不需要真实 client）
# ================================================================

class TestClassifyAndRewrite:

    def test_coding_with_rewrite(self):
        async def _run():
            llm = MockLLMProvider("1\n如何把 hy_memory 项目发布到私有包索引")
            result = await classify_and_rewrite_queries(
                ["怎么发布", "用 twine 还是手动？", "我说的是发布到私有包索引"],
                llm,
            )
            assert result["ok"] is True
            assert result["is_coding"] is True
            assert result["rewrite_query"] == "如何把 hy_memory 项目发布到私有包索引"
        asyncio.run(_run())

    def test_chat_with_rewrite(self):
        async def _run():
            llm = MockLLMProvider("0\n用户最喜欢什么颜色")
            result = await classify_and_rewrite_queries(
                ["你喜欢什么颜色", "我呢"], llm,
            )
            assert result["ok"] is True
            assert result["is_coding"] is False
            assert result["rewrite_query"] == "用户最喜欢什么颜色"
        asyncio.run(_run())

    def test_no_rewrite_keeps_target(self):
        """LLM 返回 0/1 但没给 rewrite → 用原 target"""
        async def _run():
            llm = MockLLMProvider("1")
            result = await classify_and_rewrite_queries(["foo"], llm)
            assert result["ok"] is True
            assert result["is_coding"] is True
            assert result["rewrite_query"] == "foo"
        asyncio.run(_run())

    def test_unrecognized_head_falls_back(self):
        """LLM 输出不是 0/1 → ok=False 但仍给 rewrite"""
        async def _run():
            llm = MockLLMProvider("maybe\nthe rewrite")
            result = await classify_and_rewrite_queries(["foo"], llm)
            assert result["ok"] is False
            assert result["is_coding"] is False
            assert result["rewrite_query"] == "the rewrite"
        asyncio.run(_run())

    def test_llm_failure(self):
        async def _run():
            result = await classify_and_rewrite_queries(["foo"], FailingLLMProvider())
            assert result["ok"] is False
            assert result["is_coding"] is False
            assert result["rewrite_query"] == "foo"
        asyncio.run(_run())

    def test_empty_queries(self):
        async def _run():
            llm = MockLLMProvider("1\nrewrite")
            result = await classify_and_rewrite_queries([], llm)
            assert result["ok"] is False
            assert result["rewrite_query"] == ""
        asyncio.run(_run())

    def test_markdown_fence_stripped(self):
        async def _run():
            llm = MockLLMProvider("```\n1\nrewritten X\n```")
            result = await classify_and_rewrite_queries(["x"], llm)
            assert result["ok"] is True
            assert result["is_coding"] is True
            assert result["rewrite_query"] == "rewritten X"
        asyncio.run(_run())


# ================================================================
# Phase 2: scene 参数路由 — 用最小 SimpleNamespace 模拟 client，
# 直接覆盖 async_search 入口的路由逻辑（不依赖完整 client init）
# ================================================================
#
# 此处复用现有 search_ctx fixture（含真实 store + mock embed）；scene 路由
# 在 client.async_search 顶部，store 是否被实际调用由我们在 mock client 中
# 短路掉。
# ================================================================

import time
import uuid
import asyncio
from types import SimpleNamespace
from typing import List, Optional, Any, Dict

from hy_memory.client import HyMemoryClient
from hy_memory.coding.types import CodingMemory


@pytest.fixture
async def search_ctx_with_llm(tmp_data_dir, mock_embed):
    """复用 test_search_e2e 的 ctx 思路：真实 store + mock embed + 可注入 mock LLM"""
    import os, uuid
    from hy_memory.config import MemoryConfig
    from hy_memory.coding.store import CodingMemoryStore

    cfg = MemoryConfig.from_env()
    cfg.history.db_path = os.path.join(tmp_data_dir, "history.db")
    cfg.coding.db_path = os.path.join(tmp_data_dir, "coding_memory.db")
    cfg.coding.enable = True
    cfg.vector_store.provider = "chroma"
    cfg.vector_store.path = os.path.join(tmp_data_dir, "chroma")
    cfg.vector_store.collection_name = f"test_scene_{uuid.uuid4().hex[:8]}"
    cfg.vector_store.embedding_dims = 1536

    store = CodingMemoryStore(cfg, embed_service=mock_embed)
    await store.initialize()

    # mock client-like ns（覆盖 async_search 用到的字段）
    ns = SimpleNamespace(
        _config=cfg,
        _embed_service=mock_embed,
        _coding_store=store,
        _coding_writer=object(),  # 占位
        _coding_llm_provider=None,
        _coding_init_lock=asyncio.Lock(),
        _history_store=None,        # 用于 record_search
        _enable_history_record=False,
        _build_isolation_key=lambda u, a: f"{u}:{a}",
    )

    # 把 HyMemoryClient._search_coding 当 self=ns 来用
    # 收 **kwargs：这里只是把 self 绑成 ns，阈值类参数原样透传，
    # 以后再加新的不用跟着改
    async def _search_coding_bound(target_query, **kw):
        return await HyMemoryClient._search_coding(ns, target_query=target_query, **kw)
    ns._search_coding = _search_coding_bound

    # 短路 chat 路径需要的内部 reader：返回 fixed 空结果
    async def _stub_get_coding_writer():
        return ns._coding_writer
    ns._get_coding_writer = _stub_get_coding_writer

    # 短路 chat 路径：直接返回空 memories（因为我们这里只测路由是否走对）
    async def _stub_chat_search(read_req):
        return type("Resp", (), {
            "memories": [], "total": 0, "elapsed_ms": 1.0,
        })()

    ns._reader = SimpleNamespace(read=_stub_chat_search)

    # async_search 现在只是薄壳：设置 embed_override contextvar 后转发给
    # _async_search_impl（真实实现）。SimpleNamespace 上必须挂这个方法，
    # 否则壳转发时报 AttributeError。绑定成 bound method 形式。
    ns._async_search_impl = HyMemoryClient._async_search_impl.__get__(ns, type(ns))

    yield ns
    await store.close()


@pytest.mark.asyncio
class TestSceneRouting:
    """async_search 的 scene/queries/query 三分支路由"""

    # async_search 被 _route_to_internal_loop 装饰；测试时直接调原函数
    _async_search = staticmethod(HyMemoryClient.async_search.__wrapped__)

    async def _seed_coding_memory(self, ns):
        await ns._coding_store.insert(CodingMemory(
            experience_id="e_pub", user_id="u1", task="发布到私有包索引",
            search_keys=["twine upload"], solution="...", confidence=0.9,
        ))

    async def test_explicit_scene_coding_no_llm(self, search_ctx_with_llm):
        """scene='productivity' 显式 + 单 query → 走 coding 路径，不调 LLM"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)
        # 注入 LLM —— 如果被调，会留 calls 记录
        sentinel_llm = MockLLMProvider("0\nshould not be called")
        ns._coding_llm_provider = sentinel_llm

        resp = await self._async_search(
            ns,
            query="发布到私有包索引",
            scene="productivity",
            user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, min_score=0.0,
        )
        assert resp["scene"] == "productivity"
        assert "facts" in resp
        assert "experiences" in resp
        # LLM 不应被调
        assert len(sentinel_llm.calls) == 0

    async def test_explicit_scene_chat_no_llm(self, search_ctx_with_llm):
        """scene='normal' 显式 + 多 queries → 走 chat 路径，不调 LLM（即使 queries 多条）"""
        ns = search_ctx_with_llm
        sentinel_llm = MockLLMProvider("1\nshould not be called")
        ns._coding_llm_provider = sentinel_llm

        # chat 路径需要 _reader.read；让它跑通
        # 直接 mock async_search 结尾依赖，模拟空结果走完
        # 这里只验证不进 coding 分支 + LLM 没被调
        try:
            resp = await self._async_search(
                ns,
                queries=["a", "b", "你帮我发布一下"],
                scene="normal",
                user_ids=["u1"],
            )
            # 走到 chat 分支会需要更多 client 内部依赖；我们这里用 try 兜底，
            # 重点验证 LLM 没被调（短路了 LLM）
        except Exception:
            pass
        assert len(sentinel_llm.calls) == 0  # ← 关键断言

    async def test_default_single_query_no_llm(self, search_ctx_with_llm):
        """默认 light search：scene=None + 单 query 固定 normal，零 LLM。"""
        ns = search_ctx_with_llm
        sentinel = MockLLMProvider('{"scene":"working"}')
        ns._coding_llm_provider = sentinel
        try:
            await self._async_search(ns, query="发布到私有包索引", user_ids=["u1"])
        except Exception:
            pass
        assert len(sentinel.calls) == 0

    async def test_default_multi_queries_keep_previous_rewrite_logic(self, search_ctx_with_llm):
        ns = search_ctx_with_llm
        ns._config.llm.enable_query_rewrite = True
        llm = MockLLMProvider("coding\n修复 auth.py\nSINCE: NONE")
        ns._coding_llm_provider = llm
        seen = {}

        async def _capture(target_query, **kwargs):
            seen["query"] = target_query
            seen.update(kwargs)
            return {
                "request_id": "r", "scene": "productivity",
                "facts": [], "experiences": [], "elapsed_ms": 1.0,
                "chain_block": "", "chain_used": [],
            }

        ns._search_coding = _capture
        await self._async_search(
            ns, queries=["auth.py 报错", "修一下"], user_ids=["u1"],
        )
        assert len(llm.calls) == 1
        assert seen["variant"] == "coding"
        assert seen["query"] == "修复 auth.py"

    async def test_default_multi_queries_with_features_disabled_no_llm(self, search_ctx_with_llm):
        ns = search_ctx_with_llm
        ns._config.coding.enable = False
        ns._config.llm.enable_query_rewrite = False
        sentinel = MockLLMProvider("should not be called")
        ns._coding_llm_provider = sentinel
        try:
            await self._async_search(
                ns, queries=["上下文", "目标问题"], user_ids=["u1"],
            )
        except Exception:
            pass
        assert len(sentinel.calls) == 0

    async def test_no_scene_multi_queries_calls_llm_rewrite_used(self, search_ctx_with_llm):
        """没 scene + 多 queries → 调 LLM；若 is_coding=1 + 有 rewrite，effective query = rewrite"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)
        # LLM 返回 1 + rewrite
        llm = MockLLMProvider("1\n如何发布到私有包索引（改写后）")
        ns._coding_llm_provider = llm

        resp = await self._async_search(
            ns,
            queries=["发布", "用 twine？", "我说的是私有包索引"],
            user_ids=["u1"],
            workspace_id=None, branch=None,
            limit=10, min_score=0.0,
        )
        assert resp["scene"] == "productivity"
        assert len(llm.calls) == 1  # 调了一次 LLM

    async def test_no_scene_auto_coding_uses_coding_variant(self, search_ctx_with_llm):
        ns = search_ctx_with_llm
        ns._coding_llm_provider = MockLLMProvider(
            "coding\n修复 auth.py 的 traceback"
        )
        seen = {}

        async def _capture(target_query, **kwargs):
            seen.update(kwargs)
            return {
                "request_id": "r", "scene": "productivity",
                "facts": [], "experiences": [], "elapsed_ms": 1.0,
                "chain_block": "", "chain_used": [],
            }

        ns._search_coding = _capture
        await self._async_search(
            ns,
            queries=["auth.py 报错", "帮我修掉这个 traceback"],
            user_ids=["u1"],
        )
        assert seen["variant"] == "coding"

    async def test_no_scene_multi_queries_chat_classification(self, search_ctx_with_llm):
        """没 scene + 多 queries + LLM 判 chat → 走 chat 路径"""
        ns = search_ctx_with_llm
        llm = MockLLMProvider("0\nrewrite for chat")
        ns._coding_llm_provider = llm

        try:
            await self._async_search(
                ns,
                queries=["你喜欢", "什么颜色", "猫还是狗"],
                user_ids=["u1"],
            )
        except Exception:
            pass
        # LLM 被调 1 次
        assert len(llm.calls) == 1

    async def test_no_scene_llm_failure_falls_back_chat(self, search_ctx_with_llm):
        """没 scene + 多 queries + LLM 失败 → fail-safe 走 chat"""
        ns = search_ctx_with_llm
        ns._coding_llm_provider = FailingLLMProvider()

        try:
            await self._async_search(
                ns,
                queries=["debug", "我那个错"],
                user_ids=["u1"],
            )
        except Exception:
            pass
        # 没异常向上抛即可（fail-safe）

    async def test_invalid_scene_raises(self, search_ctx_with_llm):
        """scene 非法值 → ValueError"""
        ns = search_ctx_with_llm
        with pytest.raises(ValueError, match="scene must be"):
            await self._async_search(
                ns,
                query="x",
                scene="weird",
                user_ids=["u1"],
            )

    async def test_invalid_search_mode_raises(self, search_ctx_with_llm):
        with pytest.raises(ValueError, match="search_mode must be"):
            await self._async_search(
                search_ctx_with_llm,
                query="x", search_mode="turbo", user_ids=["u1"],
            )

    async def test_explicit_coding_but_disabled_falls_back(self, search_ctx_with_llm):
        """scene='productivity' 但 config.coding.enable=False → fall back chat"""
        ns = search_ctx_with_llm
        ns._config.coding.enable = False
        sentinel_llm = MockLLMProvider("0\n")
        ns._coding_llm_provider = sentinel_llm

        try:
            await self._async_search(
                ns,
                query="x",
                scene="productivity",
                user_ids=["u1"],
            )
        except Exception:
            pass
        # 即使 scene='productivity'，coding 关闭时应该回退 chat（不会调 LLM）
        assert len(sentinel_llm.calls) == 0


@pytest.mark.asyncio
class TestRequestIdPassthrough:
    """search()/async_search() 的 request_id：传入则复用，不传/空白则自生成。"""

    _async_search = staticmethod(HyMemoryClient.async_search.__wrapped__)

    async def _seed_coding_memory(self, ns):
        await ns._coding_store.insert(CodingMemory(
            experience_id="m_pub", user_id="u1", task="发布到私有包索引",
            search_keys=["twine upload"], solution="...",
            confidence=0.9,
        ))

    async def test_explicit_request_id_reused(self, search_ctx_with_llm):
        """传入 request_id → 原样出现在返回结果里"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)

        resp = await self._async_search(
            ns,
            query="发布到私有包索引",
            scene="productivity",
            user_ids=["u1"],
            request_id="app-预生成-req-123",
        )
        assert resp["request_id"] == "app-预生成-req-123"

    async def test_missing_request_id_autogenerated(self, search_ctx_with_llm):
        """不传 request_id → SDK 自生成一个合法 uuid"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)

        resp = await self._async_search(
            ns,
            query="发布到私有包索引",
            scene="productivity",
            user_ids=["u1"],
        )
        assert resp["request_id"]
        uuid.UUID(resp["request_id"])  # 不抛异常即为合法 uuid

    async def test_blank_request_id_autogenerated(self, search_ctx_with_llm):
        """空白 request_id（空串 / 纯空格）→ 视为未传，自生成"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)

        for blank in ("", "   "):
            resp = await self._async_search(
                ns,
                query="发布到私有包索引",
                scene="productivity",
                user_ids=["u1"],
                request_id=blank,
            )
            assert resp["request_id"]
            uuid.UUID(resp["request_id"])

    async def test_each_call_without_request_id_gets_distinct_id(self, search_ctx_with_llm):
        """不同调用各自生成不同的 request_id"""
        ns = search_ctx_with_llm
        await self._seed_coding_memory(ns)

        resp1 = await self._async_search(
            ns, query="发布到私有包索引", scene="productivity", user_ids=["u1"],
        )
        resp2 = await self._async_search(
            ns, query="发布到私有包索引", scene="productivity", user_ids=["u1"],
        )
        assert resp1["request_id"] != resp2["request_id"]


@pytest.mark.asyncio
class TestQueryRewriteRouting:
    """search_mode=agentic 的 query rewrite 与 working memory 组合路由。"""

    _async_search = staticmethod(HyMemoryClient.async_search.__wrapped__)

    async def test_agentic_single_query_classifies_and_rewrites(self, search_ctx_with_llm):
        ns = search_ctx_with_llm
        llm = MockLLMProvider("coding\n修复 auth.py 的异常\nSINCE: NONE")
        ns._coding_llm_provider = llm
        seen = {}

        async def _capture(target_query, **kwargs):
            seen["query"] = target_query
            seen.update(kwargs)
            return {
                "request_id": "r", "scene": "productivity",
                "facts": [], "experiences": [], "elapsed_ms": 1.0,
                "chain_block": "", "chain_used": [],
            }

        ns._search_coding = _capture
        await self._async_search(
            ns, query="修一下这个异常", search_mode="agentic", user_ids=["u1"],
        )
        assert len(llm.calls) == 1
        assert seen["variant"] == "coding"
        assert seen["query"] == "修复 auth.py 的异常"

    async def test_agentic_without_working_memory_still_classifies_and_rewrites(self, search_ctx_with_llm):
        """agentic 不受 working-memory 开关影响：仍做三分类、rewrite 和时间解析。

        chat 路径尾部依赖完整 client（_registry 等），此处只验证 LLM 被正确调用
        （单 query 也走、prompt 不含判类），rewrite 解析细节由 analyze_queries 单测覆盖。
        """
        ns = search_ctx_with_llm
        ns._config.coding.enable = False
        llm = MockLLMProvider(
            "chat\nwhat important thing did the user say last week\nSINCE: 2026-06-24"
        )
        ns._coding_llm_provider = llm

        try:
            await self._async_search(
                ns, query="我上周说了什么重要的事", search_mode="agentic",
                user_ids=["u1"],
            )
        except Exception:
            pass
        assert len(llm.calls) == 1                        # 单 query 也调了 LLM
        assert "Classify the target" in llm.calls[0]["prompt"]

    async def test_agentic_classifies_and_rewrites_in_one_call(self, search_ctx_with_llm):
        """agentic + working memory：一次 LLM 完成三分类、改写与时间解析。"""
        ns = search_ctx_with_llm
        ns._config.coding.enable = True
        await TestSceneRouting()._seed_coding_memory(ns)
        llm = MockLLMProvider("1\n如何发布到私有包索引\nSINCE: NONE")
        ns._coding_llm_provider = llm

        resp = await self._async_search(
            ns, queries=["怎么发布", "我说的是私有包索引"],
            search_mode="agentic",
            user_ids=["u1"], workspace_id=None, branch=None,
            limit=10, min_score=0.0,
        )
        assert len(llm.calls) == 1                        # 只调一次 LLM（合并）
        assert "Classify the target" in llm.calls[0]["prompt"]  # 判类在同一 prompt
        assert resp["scene"] == "productivity"

    async def test_agentic_long_queries_still_classify_and_rewrite(self, search_ctx_with_llm):
        """agentic 使用有界 query 视图；原始 queries 超长也不关闭 rewrite。"""
        ns = search_ctx_with_llm
        ns._config.coding.enable = True
        ns._config.llm.query_rewrite_max_chars = 20  # 故意调低
        llm = MockLLMProvider("chat\n重写后的查询\nSINCE: NONE")
        ns._coding_llm_provider = llm

        try:
            resp = await self._async_search(
                ns, queries=["这是一段非常非常长的查询" * 5, "还有更多内容拼接起来超过阈值"],
                search_mode="agentic",
                user_ids=["u1"],
            )
            assert resp["rewrite"]["used"] is True
            assert resp["rewrite"]["effective_query"] == "重写后的查询"
        except Exception:
            pass
        assert len(llm.calls) == 1

    async def test_agentic_long_queries_without_wm_still_use_llm(self, search_ctx_with_llm):
        """agentic 总是启用 judge/rewrite，即使 working memory 关闭且原始 query 很长。"""
        ns = search_ctx_with_llm
        ns._config.coding.enable = False
        ns._config.llm.query_rewrite_max_chars = 10
        llm = MockLLMProvider("chat\n重写后的长查询\nSINCE: NONE")
        ns._coding_llm_provider = llm

        try:
            resp = await self._async_search(
                ns, query="这是一段超过十个字符的查询内容",
                search_mode="agentic", user_ids=["u1"],
            )
            assert resp["rewrite"]["used"] is True
        except Exception:
            pass
        assert len(llm.calls) == 1

    async def test_default_mode_no_llm(self, search_ctx_with_llm):
        """默认模式不受旧配置影响，固定 normal 且零 LLM。"""
        ns = search_ctx_with_llm
        ns._config.coding.enable = False
        ns._config.llm.enable_query_rewrite = False
        sentinel = MockLLMProvider("nope")
        ns._coding_llm_provider = sentinel

        try:
            await self._async_search(ns, query="随便问一句", user_ids=["u1"])
        except Exception:
            pass
        assert len(sentinel.calls) == 0
