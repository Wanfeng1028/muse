"""delete/get/list 操作的 pipeline trace（DELETE/GET/LIST step）落库验证。

不构造完整 VDB/client，直接驱动 HyMemoryClient._maybe_store_op_log + _backend_identity
两个 helper（绑定一个真实 SqliteCache），验证：
  - trace 开启时落 pipeline_logs_v2，step / parsed / memory_ids 正确
  - trace 关闭时（MEMORY_PIPELINE_TRACE_ENABLED=false）不落库
"""

import asyncio
import json
import types

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.data.cache_sqlite import SqliteCache
from hy_memory.client import HyMemoryClient


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fake_client(cache, provider="qdrant", db_name="", coll="agent_memories_1024"):
    """造一个最小壳：只挂 _cache / _config / _vector_store，够两个 helper 用。"""
    c = HyMemoryClient.__new__(HyMemoryClient)
    c._cache = cache
    c._config = MemoryConfig.from_dict({"vector_store": {"provider": provider}})
    c._vector_store = types.SimpleNamespace(_db_name=db_name, _collection_name=coll)
    return c


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_CACHE_DB_PATH", str(tmp_path / "cache.db"))
    cfg = MemoryConfig.from_dict({"cache": {"backend": "sqlite"}})
    ca = SqliteCache(cfg)
    run(ca.initialize())
    return ca


class TestBackendIdentity:
    def test_chroma_no_db_name(self, cache):
        c = _fake_client(cache, provider="chroma", db_name="", coll="agent_memories_1024")
        ident = c._backend_identity()
        assert ident["provider"] == "chroma"
        assert ident["db_name"] == ""
        assert ident["collection_name"] == "agent_memories_1024"


class TestOpLogWrites:
    def test_delete_log(self, cache, monkeypatch):
        monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "true")
        c = _fake_client(cache)

        async def _go():
            await c._maybe_store_op_log(
                step="DELETE",
                request_id="rq-del",
                user_id="u1",
                agent_id="a1",
                parsed={**c._backend_identity(), "memory_id": "m1", "vdb_deleted": True,
                        "deleted_count": 1, "found": True},
                memory_ids=["m1"],
                elapsed_ms=12.3,
            )
            return await cache.get_pipeline_logs(request_id="rq-del")

        logs = run(_go())
        assert len(logs) == 1
        row = logs[0]
        assert row["step"] == "DELETE"
        assert row["user_id"] == "u1"
        parsed = json.loads(row["parsed"])
        assert parsed["memory_id"] == "m1"
        assert parsed["vdb_deleted"] is True
        assert parsed["collection_name"] == "agent_memories_1024"
        assert parsed["provider"] == "qdrant"
        assert json.loads(row["memory_ids"]) == ["m1"]

    def test_get_log(self, cache, monkeypatch):
        monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "true")
        c = _fake_client(cache)

        async def _go():
            await c._maybe_store_op_log(
                step="GET",
                request_id="rq-get",
                user_id="u1",
                parsed={**c._backend_identity(), "memory_id": "m9", "hit": False, "source": ""},
                memory_ids=["m9"],
                elapsed_ms=3.0,
            )
            return await cache.get_pipeline_logs(request_id="rq-get")

        logs = run(_go())
        assert len(logs) == 1
        assert logs[0]["step"] == "GET"
        parsed = json.loads(logs[0]["parsed"])
        assert parsed["hit"] is False
        assert parsed["memory_id"] == "m9"

    def test_list_log(self, cache, monkeypatch):
        monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "true")
        c = _fake_client(cache)

        async def _go():
            await c._maybe_store_op_log(
                step="LIST",
                request_id="rq-list",
                user_id="u1",
                agent_id="a1",
                parsed={**c._backend_identity(), "user_id": "u1", "vdb_total": 42,
                        "returned_count": 2, "limit": 100, "offset": 0, "order": "desc"},
                memory_ids=["m1", "m2"],
                elapsed_ms=8.0,
            )
            return await cache.get_pipeline_logs(request_id="rq-list")

        logs = run(_go())
        assert len(logs) == 1
        assert logs[0]["step"] == "LIST"
        parsed = json.loads(logs[0]["parsed"])
        assert parsed["vdb_total"] == 42
        assert parsed["returned_count"] == 2
        assert json.loads(logs[0]["memory_ids"]) == ["m1", "m2"]

    def test_trace_disabled_no_write(self, cache, monkeypatch):
        monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
        c = _fake_client(cache)

        async def _go():
            await c._maybe_store_op_log(
                step="DELETE",
                request_id="rq-off",
                user_id="u1",
                parsed={"memory_id": "m1"},
                memory_ids=["m1"],
            )
            return await cache.get_pipeline_logs(request_id="rq-off")

        logs = run(_go())
        assert logs == []
