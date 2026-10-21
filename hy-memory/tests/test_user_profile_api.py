"""Public get_user_profile API regressions."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from hy_memory.client import HyMemoryClient
from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode, MemoryStatus


class _VectorStore:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    async def list_by_user(self, **kwargs):
        assert kwargs["layers"] == [MemoryLayer.L0_BASIC_INFO]
        assert kwargs["with_vectors"] is False
        return list(self.nodes)


class _GraphStore:
    def __init__(self, nodes):
        self.nodes = list(nodes)

    async def get_all_nodes(self, **kwargs):
        return list(self.nodes)


def _l0(node_id, *, status, is_latest, when, kv):
    return MemoryNode(
        node_id=node_id,
        user_id="u1",
        agent_id="",
        layer=MemoryLayer.L0_BASIC_INFO,
        status=status,
        is_latest=is_latest,
        content="partial profile",
        gmt_created=when,
        custom={"basic_info_kv": dict(kv)},
        tags=["basic_info"],
    )


def _internal_node(node_id, schema_kind, content):
    version_key = (
        "balanced_catalog_version"
        if schema_kind == "balanced_persona_catalog"
        else "specific_supplement_version"
    )
    return MemoryNode(
        node_id=node_id,
        user_id="u1",
        agent_id="",
        layer=MemoryLayer.L6_SCHEMA,
        status=MemoryStatus.ACTIVE,
        is_latest=True,
        content=content,
        confidence=1.0,
        custom={
            "schema_kind": schema_kind,
            version_key: 4 if schema_kind == "balanced_persona_catalog" else 1,
            "selected_count": 1,
        },
    )


def _client(vector_nodes, graph_nodes):
    config = MemoryConfig.from_dict({
        "basic_profile": {
            "fields": {
                "name": "Name",
                "occupation": "Occupation",
            },
        },
    })

    async def _store_log(**kwargs):
        return None

    return SimpleNamespace(
        _vector_store=_VectorStore(vector_nodes),
        _graph_store=_GraphStore(graph_nodes),
        _config=config,
        _backend_identity=lambda: {"vector_store": "fake"},
        _maybe_store_op_log=_store_log,
    )


@pytest.mark.asyncio
async def test_get_user_profile_merges_l0_history_and_ultra_artifacts(monkeypatch):
    now = datetime.now()
    old = _l0(
        "l0-old",
        status=MemoryStatus.SUPERSEDED,
        is_latest=False,
        when=now - timedelta(days=1),
        kv={"name": "Alice"},
    )
    head = _l0(
        "l0-head",
        status=MemoryStatus.ACTIVE,
        is_latest=True,
        when=now,
        kv={"occupation": "Engineer"},
    )
    catalog = _internal_node(
        "catalog-1",
        "balanced_persona_catalog",
        "System2 verified persona catalog:\n"
        "- [habits_items] The user carries a steel bottle every day.",
    )
    supplement = _internal_node(
        "supplement-1",
        "specific_persona_supplement",
        "System2 specific supplement (exact stored evidence):\n"
        "- [health_accessibility] The user has mild myopia.",
    )
    monkeypatch.setenv("MEMORY_USER_PROFILE_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.setenv("MEMORY_USER_PROFILE_SPECIFIC_SUPPLEMENT_ENABLED", "true")

    raw = HyMemoryClient.async_get_user_profile.__wrapped__
    result = await raw(
        _client([head, old], [catalog, supplement]),
        user_id="u1",
    )

    profile = result["profile"]
    assert profile["memory_id"] == "l0-head"
    assert profile["layer"] == MemoryLayer.L0_BASIC_INFO.value
    assert profile["basic_info"] == {
        "name": "Alice",
        "occupation": "Engineer",
    }
    assert "name is Alice" in profile["content"]
    assert "occupation is Engineer" in profile["content"]
    catalog_pos = profile["content"].index("System2 verified persona catalog")
    supplement_pos = profile["content"].index("System2 specific supplement")
    assert catalog_pos < supplement_pos
    assert profile["catalog"]["attached"] is True
    assert profile["supplement"]["attached"] is True


@pytest.mark.asyncio
async def test_get_user_profile_can_be_synthetic_from_ultra_catalog(monkeypatch):
    catalog = _internal_node(
        "catalog-only",
        "balanced_persona_catalog",
        "System2 verified persona catalog:\n"
        "- [preferences_collections] The user enjoys jazz.",
    )
    monkeypatch.setenv("MEMORY_USER_PROFILE_BALANCED_CATALOG_ENABLED", "true")
    monkeypatch.delenv(
        "MEMORY_USER_PROFILE_SPECIFIC_SUPPLEMENT_ENABLED", raising=False,
    )

    raw = HyMemoryClient.async_get_user_profile.__wrapped__
    result = await raw(
        _client([], [catalog]),
        user_id="u1",
    )

    profile = result["profile"]
    assert profile["memory_id"] == "catalog-only"
    assert profile["basic_info"] == {}
    assert "The user enjoys jazz." in profile["content"]
    assert profile["catalog"]["synthetic_l0"] is True


@pytest.mark.asyncio
async def test_get_user_profile_returns_none_without_l0_or_ultra(monkeypatch):
    monkeypatch.delenv(
        "MEMORY_USER_PROFILE_BALANCED_CATALOG_ENABLED", raising=False,
    )
    monkeypatch.delenv(
        "MEMORY_USER_PROFILE_SPECIFIC_SUPPLEMENT_ENABLED", raising=False,
    )
    raw = HyMemoryClient.async_get_user_profile.__wrapped__
    result = await raw(
        _client([], []),
        user_id="u1",
    )
    assert result["profile"] is None
