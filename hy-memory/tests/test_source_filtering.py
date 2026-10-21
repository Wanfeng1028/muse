import uuid
import subprocess
import sys
import textwrap

import pytest

from hy_memory.config import MemoryConfig, VectorStoreConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode
from hy_memory.utils.source_filter import (
    normalize_source,
    normalize_source_filters,
    source_allowed,
)


def _config(provider: str, path, *, dims: int = 4) -> MemoryConfig:
    config = MemoryConfig()
    config.vector_store = VectorStoreConfig(
        provider=provider,
        persist_directory=str(path),
        collection_name=f"source_filter_{uuid.uuid4().hex[:8]}",
        embedding_dims=dims,
    )
    return config


def _node(node_id: str, source: str, embedding) -> MemoryNode:
    return MemoryNode(
        node_id=node_id,
        user_id="u1",
        agent_id="a1",
        session_id="s1",
        source=source,
        layer=MemoryLayer.L2_FACT,
        content=f"memory from {source}",
        embedding=list(embedding),
    )


def test_source_normalization_and_exclude_precedence():
    assert normalize_source("  CoDeX ") == "codex"
    assert normalize_source_filters(
        [" Codex ", "codex", "OpenClaw"], [" CURSOR "]
    ) == (["codex", "openclaw"], ["cursor", "mixed"])
    assert source_allowed("codex", ["codex", "cursor"], ["codex"]) is False
    assert source_allowed("cursor", ["codex"], []) is False
    assert source_allowed("mixed", [], ["cursor"]) is False
    assert source_allowed("mixed", ["mixed"], []) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["chroma", "qdrant", "faiss"])
async def test_vector_source_filter_is_applied_before_limit(provider, tmp_path, monkeypatch):
    """The globally best disallowed hit must not consume the only result slot."""
    from hy_memory.data.vector_store import create_vector_store

    if provider == "qdrant":
        from hy_memory.pipelines._retrieval import bm25_fastembed

        monkeypatch.setattr(bm25_fastembed, "is_available", lambda: False)
    store = create_vector_store(_config(provider, tmp_path / provider))
    await store.initialize()
    try:
        await store.upsert(_node("cursor-best", "cursor", [1.0, 0.0, 0.0, 0.0]))
        await store.upsert(_node("codex-second", "codex", [0.9, 0.1, 0.0, 0.0]))
        await store.upsert(_node("openclaw-third", "openclaw", [0.8, 0.2, 0.0, 0.0]))
        for node_id in ("cursor-best", "codex-second", "openclaw-third"):
            await store.update_payload(node_id, {"episode_id": "episode-1"})

        included = await store.search(
            query_embedding=[1.0, 0.0, 0.0, 0.0],
            user_id="u1",
            include_sources=["codex"],
            limit=1,
            score_threshold=0.0,
        )
        assert [hit["node_id"] for hit in included] == ["codex-second"]
        assert included[0]["node"].source == "codex"

        excluded = await store.search(
            query_embedding=[1.0, 0.0, 0.0, 0.0],
            user_id="u1",
            exclude_sources=["cursor"],
            limit=1,
            score_threshold=0.0,
        )
        assert [hit["node_id"] for hit in excluded] == ["codex-second"]

        both = await store.search(
            query_embedding=[1.0, 0.0, 0.0, 0.0],
            user_id="u1",
            include_sources=["cursor", "codex"],
            exclude_sources=["cursor"],
            limit=1,
            score_threshold=0.0,
        )
        assert [hit["node_id"] for hit in both] == ["codex-second"]

        episode_nodes = await store.list_by_episode(
            ["episode-1"], user_id="u1", include_sources=["codex"], limit=1,
        )
        assert [node.node_id for node in episode_nodes] == ["codex-second"]
    finally:
        await store.close()


def test_kuzu_graph_source_filter_is_applied_before_limit(tmp_path):
    # Kuzu's native extension owns process-global worker state. Isolate the real
    # backend check so pytest's main process does not wait on extension teardown.
    script = textwrap.dedent(f"""
        import asyncio
        import os
        from hy_memory.config import MemoryConfig
        from hy_memory.data.graph_store_kuzu import KuzuGraphStore
        from hy_memory.models.memory import MemoryLayer, MemoryNode

        async def main():
            config = MemoryConfig()
            config.vector_store.embedding_dims = 4
            config.graph_store.provider = "kuzu"
            config.graph_store.db_path = {str(tmp_path / 'graph')!r}
            graph = KuzuGraphStore(config)
            await graph.initialize()
            for node_id, source, embedding in (
                ("cursor-best", "cursor", [1.0, 0.0, 0.0, 0.0]),
                ("codex-second", "codex", [0.9, 0.1, 0.0, 0.0]),
                ("anchor", "codex", [0.0, 1.0, 0.0, 0.0]),
            ):
                node = MemoryNode(
                    node_id=node_id, user_id="u1", agent_id="a1", session_id="s1",
                    source=source, layer=MemoryLayer.L2_FACT,
                    content=node_id, embedding=embedding,
                )
                node._graph_embedding = embedding
                await graph.upsert_memory_node(node)
            hits = await graph.vector_search(
                [1.0, 0.0, 0.0, 0.0], isolation_key="", user_id="u1",
                include_sources=["codex"], limit=1,
            )
            assert [hit["node_id"] for hit in hits] == ["codex-second"]
            assert hits[0]["memory_source"] == "codex"
            await graph.add_edge("anchor", "cursor-best", "RELATED_TO")
            await graph.add_edge("anchor", "codex-second", "RELATED_TO")
            edges = await graph.get_related_edges(
                ["anchor"], include_sources=["codex"], max_edges=10,
            )
            assert sorted(edge["target_id"] for edge in edges) == ["codex-second"]
            await graph.close()
            os._exit(0)

        asyncio.run(main())
    """)
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.asyncio
async def test_evolution_chain_does_not_leak_excluded_source():
    from hy_memory.pipelines._retrieval.evolution import expand_evolution_chains

    old = _node("old", "codex", [1.0, 0.0, 0.0, 0.0])
    new = _node("new", "cursor", [1.0, 0.0, 0.0, 0.0])
    old.is_latest = False
    old.superseded_by = [new.node_id]
    new.supersedes = [old.node_id]

    class Store:
        async def get_by_ids(self, node_ids):
            by_id = {old.node_id: old, new.node_id: new}
            return [by_id[node_id] for node_id in node_ids if node_id in by_id]

    expanded = await expand_evolution_chains(
        Store(),
        [{"node_id": old.node_id, "node": old, "score": 1.0}],
        include_sources=["codex"],
    )
    assert len(expanded) == 1
    assert expanded[0]["node_id"] == "old"
    assert [item["node_id"] for item in expanded[0]["evolution_chain"]] == ["old"]


@pytest.mark.asyncio
async def test_neo4j_graph_source_filter_is_in_database_query():
    from hy_memory.data.graph_store_neo4j import Neo4jGraphStore

    graph = object.__new__(Neo4jGraphStore)
    graph._driver = object()
    captured = {}

    async def _run(query, params=None):
        captured["query"] = query
        captured["params"] = params or {}
        return [{
            "node_id": "codex-node", "content": "x", "layer": "l6_schema",
            "confidence": 1.0, "score": 1.0, "custom_json": "{}",
            "memory_source": "codex",
        }]

    graph._run = _run
    hits = await graph.vector_search(
        [1.0, 0.0], isolation_key="", user_id="u1",
        include_sources=["codex"], exclude_sources=["cursor"], limit=1,
    )
    query = captured["query"]
    assert "m.source IN $include_sources" in query
    assert "NOT m.source IN $exclude_sources" in query
    assert query.index("m.source IN $include_sources") < query.index("ORDER BY score DESC")
    assert captured["params"]["include_sources"] == ["codex"]
    assert captured["params"]["exclude_sources"] == ["cursor"]
    assert hits[0]["memory_source"] == "codex"


@pytest.mark.asyncio
async def test_coding_store_filters_facts_and_experiences_by_source(
    tmp_path,
):
    from hy_memory.coding.store import CodingMemoryStore
    from hy_memory.coding.types import CodingMemory, WorkingFact
    from tests.coding._helpers import MockEmbedService

    config = _config("chroma", tmp_path / "coding-vectors", dims=1536)
    config.history.db_path = str(tmp_path / "history.db")
    config.coding.db_path = str(tmp_path / "coding.db")
    mock_embed = MockEmbedService()
    store = CodingMemoryStore(config, embed_service=mock_embed)
    await store.initialize()
    try:
        await store.insert(CodingMemory(
            experience_id="cursor-exp", user_id="u1", source="cursor",
            task="same task", search_keys=[], solution="cursor solution",
        ))
        await store.insert(CodingMemory(
            experience_id="codex-exp", user_id="u1", source="codex",
            task="same task", search_keys=[], solution="codex solution",
        ))
        query = await mock_embed.embed("same task")
        hits = await store.search_by_query_embedding(
            query, user_id="u1", include_sources=["codex"], top=1,
        )
        assert [hit["experience_id"] for hit in hits] == ["codex-exp"]

        await store.insert_fact(WorkingFact(
            fact_id="cursor-fact", user_id="u1", source="cursor",
            statement="same fact",
        ))
        await store.insert_fact(WorkingFact(
            fact_id="codex-fact", user_id="u1", source="codex",
            statement="same fact",
        ))
        fact_query = await mock_embed.embed("same fact")
        facts = await store.search_facts(
            fact_query, user_id="u1", include_sources=["codex"], top=1,
        )
        assert [fact.fact_id for fact, _score in facts] == ["codex-fact"]
    finally:
        await store.close()
