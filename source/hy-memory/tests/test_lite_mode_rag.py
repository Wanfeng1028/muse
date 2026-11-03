"""Lite mode must provide a complete embedding-only write/search loop."""

import types
import uuid

from hy_memory import HyMemoryClient, MemoryConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode


def _config(tmp_path, *, coding_enabled=False):
    suffix = uuid.uuid4().hex[:8]
    return MemoryConfig.from_dict({
        "vector_store": {
            "provider": "chroma",
            "collection_name": f"test_lite_rag_{suffix}",
            "persist_directory": str(tmp_path / "chroma"),
            "embedding_dims": 8,
        },
        "embedder": {
            "embedding_dims": 8,
        },
        "cache": {
            "backend": "sqlite",
            "sqlite_path": str(tmp_path / "cache.db"),
        },
        "history": {"enable": False},
        "coding": {"enable": coding_enabled},
    })


def _install_fixed_embed(client):
    """Replace network embedding calls on the already shared service object."""
    vector = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    async def embed(_self, _text, use_cache=True):
        return list(vector)

    async def embed_with_meta(_self, _text, use_cache=True):
        return list(vector), {"cache_hit": False, "provider": "test"}

    async def embed_batch(_self, texts, use_cache=True):
        return [list(vector) for _ in texts]

    async def embed_queued(_self, _text, use_cache=True):
        return list(vector)

    async def embed_queued_with_meta(_self, _text, use_cache=True):
        return list(vector), {"cache_hit": False, "provider": "test"}

    service = client._embed_service
    service.embed = types.MethodType(embed, service)
    service.embed_with_meta = types.MethodType(embed_with_meta, service)
    service.embed_batch = types.MethodType(embed_batch, service)
    service.embed_queued = types.MethodType(embed_queued, service)
    service.embed_queued_with_meta = types.MethodType(
        embed_queued_with_meta, service,
    )


def test_lite_add_then_search_returns_raw_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEMORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MEMORY_SEARCH_DEDUP_ENABLED", "false")
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
    client = HyMemoryClient(_config(tmp_path), mode="lite")
    try:
        _install_fixed_embed(client)

        cursor = client.add(
            "Cursor recorded the deployment checklist.",
            user_id="u1",
            source="cursor",
        )
        codex = client.add(
            "Codex recorded the release procedure.",
            user_id="u1",
            source="codex",
        )

        assert cursor["success"] is True
        assert codex["success"] is True

        result = client.search(
            "release procedure",
            user_ids=["u1"],
            include_sources=["codex"],
            limit=1,
            min_score=0.0,
        )
        normal = result["memories"]["normal"]
        assert len(normal) == 1
        assert normal[0]["memory_id"] == codex["memory_id"]
        assert "Codex recorded the release procedure." in normal[0]["content"]
        assert normal[0]["layer"] == "l1_raw"
        assert normal[0]["source"] == "codex"
    finally:
        client.close()


def test_lite_ignores_layers_and_scene_and_returns_only_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEMORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MEMORY_SEARCH_DEDUP_ENABLED", "false")
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
    client = HyMemoryClient(_config(tmp_path), mode="lite")
    try:
        _install_fixed_embed(client)
        raw_result = client.add(
            "Lite raw memory must be the only visible result.",
            user_id="u1",
            source="codex",
        )
        higher = MemoryNode(
            user_id="u1",
            agent_id="default_agent",
            session_id="default_session",
            source="codex",
            layer=MemoryLayer.L2_FACT,
            content="A seeded L2 fact must never escape from lite mode.",
            embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        client._loop_thread.run(client._vector_store.upsert(higher))

        forced_coding = client.search(
            "memory",
            user_ids=["u1"],
            scene="coding",
            layers=[MemoryLayer.L2_FACT],
            limit=10,
            min_score=0.0,
        )
        normal = forced_coding["memories"]["normal"]
        assert [item["memory_id"] for item in normal] == [raw_result["memory_id"]]
        assert {item["layer"] for item in normal} == {"l1_raw"}

        agentic = client.search(
            "memory",
            user_ids=["u1"],
            search_mode="agentic",
            layers=[MemoryLayer.L1_RAW, MemoryLayer.L2_FACT],
            limit=10,
            min_score=0.0,
        )
        normal = agentic["memories"]["normal"]
        assert [item["memory_id"] for item in normal] == [raw_result["memory_id"]]
        assert {item["layer"] for item in normal} == {"l1_raw"}
        assert agentic["memories"]["schema"] == []
        assert agentic["memories"]["proactive"] == []

        invalid_layers = client.search(
            "memory",
            user_ids=["u1"],
            layers=["not-a-real-layer"],
            limit=10,
            min_score=0.0,
        )
        assert [
            item["memory_id"] for item in invalid_layers["memories"]["normal"]
        ] == [raw_result["memory_id"]]
    finally:
        client.close()


def test_lite_add_with_tools_still_writes_only_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEMORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MEMORY_SEARCH_DEDUP_ENABLED", "false")
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
    client = HyMemoryClient(
        _config(tmp_path, coding_enabled=True),
        mode="lite",
    )
    try:
        _install_fixed_embed(client)
        written = client.add(
            [
                {"role": "user", "content": "Please inspect the repository."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "exec_command",
                            "arguments": '{"cmd":"git status"}',
                        },
                    }],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "content": "clean",
                },
            ],
            user_id="u1",
            scene="coding",
            source="codex",
        )
        assert written["success"] is True
        assert written["scene"] == "chat"

        result = client.search(
            "repository",
            user_ids=["u1"],
            scene="coding",
            layers=[MemoryLayer.L2_FACT],
            min_score=0.0,
        )
        normal = result["memories"]["normal"]
        assert [item["memory_id"] for item in normal] == [written["memory_id"]]
        assert {item["layer"] for item in normal} == {"l1_raw"}
    finally:
        client.close()


def test_pro_default_search_still_hides_raw(tmp_path, monkeypatch):
    """The lite exception must not widen raw visibility in pro/ultra modes."""
    monkeypatch.setenv("MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MEMORY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MEMORY_PIPELINE_TRACE_ENABLED", "false")
    client = HyMemoryClient(_config(tmp_path), mode="pro")
    try:
        _install_fixed_embed(client)
        raw = MemoryNode(
            user_id="u1",
            agent_id="default_agent",
            session_id="default_session",
            layer=MemoryLayer.L1_RAW,
            content="This raw record must stay hidden in pro mode.",
            embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        client._loop_thread.run(client._vector_store.upsert(raw))

        result = client.search(
            "raw record",
            user_ids=["u1"],
            limit=10,
            min_score=0.0,
        )
        assert result["memories"]["normal"] == []
    finally:
        client.close()
