# -*- coding: utf-8 -*-
"""
intention (L7) 写入可观测测试。

意图由 System 1 直接 upsert 到 VDB（不走 reconcile），此前既不进 pipeline_logs
也不进 memory_operations。本测试验证 writer._store_intentions 现在会：
  - 落 INTENTION_UPSERT pipeline log（含 memory_id + 回读校验 verified）
  - 落 memory_operations（op=INTENTION_UPSERT，含 memory_id），供线上按
    request_id / memory_id 追查。

注意：cache 安装 observability 时会捕获 owner_loop；跨 loop 派发会落空。因此
本测试把「建 cache/writer + 跑 _store_intentions + 读回」全放进同一个 event loop。
"""

import asyncio
import json
import os
import shutil
import tempfile
import uuid

from hy_memory.pipelines.base import WriteRequest
from hy_memory.models.memory import MemoryNode


class _FakeEmbed:
    """给不同 text 返回**明显不同**的向量（每条自己一维是 1.0，其余 0）。
    这样任意两条 cosine=0，绝不会撞上 0.95 dedup 阈值。
    """

    def __init__(self):
        self._indices = {}

    def _vec_for(self, text: str):
        # 32 维稀疏 one-hot：按首次出现顺序分配，避免 hash 随机化或碰撞。
        vec = [0.0] * 32
        idx = self._indices.setdefault(text, len(self._indices)) % 32
        vec[idx] = 1.0
        return vec

    async def embed_batch(self, texts):
        return [self._vec_for(t) for t in texts]

    async def embed_queued(self, text):
        return self._vec_for(text)


class _FakeVectorStore:
    """内存 VDB：upsert 存进 dict，get_by_id 回读。"""

    def __init__(self):
        self._store = {}

    async def upsert(self, node: MemoryNode) -> str:
        nid = node.node_id or uuid.uuid4().hex
        node.node_id = nid
        self._store[nid] = node
        return nid

    async def get_by_id(self, node_id):
        return self._store.get(node_id)


def test_intention_upsert_emits_pipeline_log_and_operation(monkeypatch):
    d = tempfile.mkdtemp(prefix="intent_obs_")
    monkeypatch.setenv("MEMORY_DEDUP_THRESHOLD", "0.95")
    os.environ["MEMORY_PIPELINE_TRACE_ENABLED"] = "true"
    os.environ["MEMORY_WRITE_APPLY_VERIFY_ENABLED"] = "true"
    os.environ["MEMORY_MEMORY_OPERATIONS_ENABLED"] = "true"  # 审计表默认关，测试显式开
    os.environ["MEMORY_LOG_DIR"] = os.path.join(d, "logs")

    async def _main():
        from hy_memory.config import MemoryConfig
        from hy_memory.data.cache_sqlite import SqliteCache
        from hy_memory.utils.pipeline_observability import (
            install_pipeline_observability, drain_pipeline_log_tasks,
        )
        from hy_memory.pipelines.writer import MemoryWriter

        cfg = MemoryConfig.from_env()
        cfg.cache.db_path = os.path.join(d, "cache.db")
        cache = SqliteCache(cfg)
        await cache.initialize()
        install_pipeline_observability(cache, log_label="test")
        vs = _FakeVectorStore()
        writer = MemoryWriter(cfg, embed_service=_FakeEmbed(), vector_store=vs, cache=cache)

        rid = uuid.uuid4().hex
        req = WriteRequest(
            content="", messages=[], user_id="u1", agent_id="codebuddy",
            session_id="s1", request_id=rid,
        )
        intentions = [
            {"content": "用户下周二要面试字节", "tags": ["求职"], "valid_until": None},
            {"content": "用户计划学习 Rust", "tags": [], "valid_until": None},
        ]
        ids = await writer._store_intentions(intentions, req, vs, rid)
        await drain_pipeline_log_tasks()

        logs = await cache.get_pipeline_logs(request_id=rid)
        ops_by_id = {nid: await cache.get_memory_operations(memory_id=nid) for nid in ids}
        await cache.close()
        return ids, logs, ops_by_id

    try:
        ids, logs, ops_by_id = asyncio.new_event_loop().run_until_complete(_main())
    finally:
        shutil.rmtree(d, ignore_errors=True)

    assert len(ids) == 2

    # 1. pipeline log: 两条 INTENTION_UPSERT，各带 memory_id + verified=True
    intent_steps = [l for l in logs if l["step"] == "INTENTION_UPSERT"]
    assert len(intent_steps) == 2
    for l in intent_steps:
        assert l.get("memory_ids"), "INTENTION_UPSERT 必须带 memory_id 供追查"
        parsed = json.loads(l["parsed"]) if isinstance(l["parsed"], str) else l["parsed"]
        assert parsed["op"] == "INTENTION_UPSERT"
        assert parsed["memory_id"] in ids
        assert parsed["layer"] == "l7_intention"
        assert parsed["verified"] is True

    # 2. memory_operations: 两条 op=INTENTION_UPSERT，可按 memory_id 反查
    for nid in ids:
        assert any(o["op"] == "INTENTION_UPSERT" for o in ops_by_id[nid]), \
            f"memory_operations 缺 INTENTION_UPSERT for {nid}"
