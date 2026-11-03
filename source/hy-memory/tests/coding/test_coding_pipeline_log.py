# -*- coding: utf-8 -*-
"""
coding 写入链路 pipeline log 打点测试。

验证 judge / extractor / reconciler 分阶段实时落 CODING_JUDGE / CODING_EXTRACT /
CODING_RECONCILE 三个 step（对标 chat 链路），且：
  - prompt / response 完整写入（不截断）
  - crash 不丢：store 入库崩溃时，前面已完成阶段的 log 仍在库

用真实 SqliteCache（含 observability 包装）+ mock LLM/embed，避免外部依赖。

注意：全部资源在单个 test 协程内构建（一个 event loop），避免 pytest-asyncio
auto 模式下 async fixture 与 test 分处不同 loop 导致 owner_loop 跨 loop 派发。
"""

import asyncio
import json
import os
import shutil
import tempfile
import uuid

import pytest

from hy_memory.coding.extractor import CodingMemoryExtractor
from hy_memory.coding.judge import classify_messages_is_coding
from hy_memory.coding.reconciler import CodingMemoryReconciler
from hy_memory.coding.store import CodingMemoryStore
from hy_memory.coding.writer import CodingWriter
from hy_memory.pipelines.base import ChatMessage, ToolCall

from tests.coding._helpers import MockLLMProvider, MockEmbedService


def _classify_resp(is_coding, reason="reason"):
    return json.dumps({"is_coding": is_coding, "reason": reason})


def _extract_resp(memories):
    return json.dumps({"memories": memories})


def _reconcile_resp(ops):
    return json.dumps({"ops": ops})


def _coding_messages():
    return [
        ChatMessage(role="user", content="帮我打包发布到私有包索引"),
        ChatMessage(role="assistant", content="", tool_calls=[
            ToolCall(id="1", name="Read", arguments={"path": "scripts/publish_package.sh"}),
        ]),
        ChatMessage(role="tool", content="200 lines", tool_call_id="1", tool_name="Read"),
        ChatMessage(role="assistant", content="", tool_calls=[
            ToolCall(id="2", name="Bash", arguments={"command": "twine upload"}),
        ]),
        ChatMessage(role="tool", content="OK uploaded", tool_call_id="2", tool_name="Bash"),
    ]


_DRAFT = {
    "task": "打包发布到私有包索引",
    "search_keys": ["twine 上传", "私有索引发布"],
    "solution": "运行 scripts/publish_package.sh，用 twine upload 上传到私有索引",
    "boundary_envs": "twine>=4.0",
    "boundary_scope": "project",
    "confidence": 0.9,
}


async def _make_cache_and_store(d):
    """在当前（test）event loop 上建 cache + store，保证 owner_loop 一致。"""
    os.environ["MEMORY_PIPELINE_TRACE_ENABLED"] = "true"
    os.environ["MEMORY_LOG_LLM_CONTENT"] = "true"
    os.environ["MEMORY_LOG_DIR"] = os.path.join(d, "logs")
    from hy_memory.config import MemoryConfig
    from hy_memory.data.cache_sqlite import SqliteCache
    from hy_memory.utils.pipeline_observability import install_pipeline_observability

    cfg = MemoryConfig.from_env()
    cfg.cache.db_path = os.path.join(d, "cache.db")
    cfg.coding.db_path = os.path.join(d, "coding_memory.db")
    cfg.vector_store.provider = "chroma"
    cfg.vector_store.persist_directory = os.path.join(d, "chroma")
    cfg.vector_store.collection_name = f"t_{uuid.uuid4().hex[:8]}"
    cfg.vector_store.embedding_dims = 1536

    cache = SqliteCache(cfg)
    await cache.initialize()
    install_pipeline_observability(cache, log_label="test")

    store = CodingMemoryStore(
        cfg,
        embed_service=MockEmbedService(),
        db_path=cfg.coding.db_path,
    )
    await store.initialize()
    return cache, store


def _build_writer(cache, store, llm):
    embed = MockEmbedService()
    extractor = CodingMemoryExtractor(llm, cache=cache)
    reconciler = CodingMemoryReconciler(
        store=store, embed_service=embed, llm_provider=llm, cache=cache,
    )
    return CodingWriter(
        store=store, extractor=extractor, reconciler=reconciler,
        llm_provider=llm, embed_service=embed, cache=cache,
    )


@pytest.mark.asyncio
class TestCodingPipelineLog:

    async def test_judge_emits_coding_judge(self):
        d = tempfile.mkdtemp(prefix="coding_plog_")
        try:
            cache, store = await _make_cache_and_store(d)
            from hy_memory.utils.pipeline_observability import drain_pipeline_log_tasks
            rid = uuid.uuid4().hex
            llm = MockLLMProvider(_classify_resp(True, "concrete code task"))
            result = await classify_messages_is_coding(
                _coding_messages(), llm,
                cache=cache, request_id=rid, user_id="u1", agent_id="codebuddy",
            )
            assert result is True
            await drain_pipeline_log_tasks()
            logs = await cache.get_pipeline_logs(request_id=rid)
            judge = next(l for l in logs if l["step"] == "CODING_JUDGE")
            assert "single-label scene classifier" in judge["prompt"]
            assert "is_coding" in judge["response"]
            await cache.close(); await store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    async def test_judge_logs_even_when_chat(self):
        """判为 chat 也留一条 CODING_JUDGE（记录判过、结论 chat）。"""
        d = tempfile.mkdtemp(prefix="coding_plog_")
        try:
            cache, store = await _make_cache_and_store(d)
            from hy_memory.utils.pipeline_observability import drain_pipeline_log_tasks
            rid = uuid.uuid4().hex
            llm = MockLLMProvider(_classify_resp(False, "casual"))
            result = await classify_messages_is_coding(
                _coding_messages(), llm,
                cache=cache, request_id=rid, user_id="u1", agent_id="codebuddy",
            )
            assert result is False
            await drain_pipeline_log_tasks()
            steps = [l["step"] for l in await cache.get_pipeline_logs(request_id=rid)]
            assert "CODING_JUDGE" in steps
            await cache.close(); await store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    async def test_extract_and_reconcile_steps(self):
        """writer 端到端：CODING_EXTRACT + CODING_RECONCILE 落库，prompt/response 完整。"""
        d = tempfile.mkdtemp(prefix="coding_plog_")
        try:
            cache, store = await _make_cache_and_store(d)
            from hy_memory.utils.pipeline_observability import drain_pipeline_log_tasks
            rid = uuid.uuid4().hex
            llm = MockLLMProvider([
                _extract_resp([_DRAFT]),
                _reconcile_resp([{"draft_idx": 0, "action": "ADD"}]),
            ])
            writer = _build_writer(cache, store, llm)
            resp = await writer.write(
                _coding_messages(), user_id="u1", agent_id="codebuddy",
                workspace_id="github.com/example/project", request_id=rid,
            )
            assert resp["success"] is True
            assert resp["experience_ids"]
            await drain_pipeline_log_tasks()
            logs = await cache.get_pipeline_logs(request_id=rid)
            steps = [l["step"] for l in logs]
            assert "CODING_EXTRACT" in steps
            assert "CODING_RECONCILE" in steps
            ext = next(l for l in logs if l["step"] == "CODING_EXTRACT")
            rec = next(l for l in logs if l["step"] == "CODING_RECONCILE")
            assert "可长期保留的 WORKING 记忆" in ext["prompt"]
            # response 是 LLM 原始输出（json.dumps 默认 ensure_ascii → task 以转义形式完整保留）
            assert "task" in ext["response"] and "twine" in ext["response"]
            assert rec["prompt"] and rec["response"]
            await cache.close(); await store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    async def test_reconcile_log_survives_store_crash(self):
        """crash 不丢：store.insert 抛异常时，CODING_EXTRACT + CODING_RECONCILE
        （在 execute 入库之前打点）仍已落库。"""
        d = tempfile.mkdtemp(prefix="coding_plog_")
        try:
            cache, store = await _make_cache_and_store(d)
            from hy_memory.utils.pipeline_observability import drain_pipeline_log_tasks
            rid = uuid.uuid4().hex
            llm = MockLLMProvider([
                _extract_resp([_DRAFT]),
                _reconcile_resp([{"draft_idx": 0, "action": "ADD"}]),
            ])
            async def _boom(*a, **k):
                raise RuntimeError("mock store crash")
            store.insert = _boom
            writer = _build_writer(cache, store, llm)
            # write 不应抛（reconciler execute 内部 try/except 吞掉 ADD 失败）
            await writer.write(
                _coding_messages(), user_id="u1", agent_id="codebuddy",
                workspace_id="github.com/example/project", request_id=rid,
            )
            await drain_pipeline_log_tasks()
            steps = [l["step"] for l in await cache.get_pipeline_logs(request_id=rid)]
            assert "CODING_EXTRACT" in steps
            assert "CODING_RECONCILE" in steps
            await cache.close(); await store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)
