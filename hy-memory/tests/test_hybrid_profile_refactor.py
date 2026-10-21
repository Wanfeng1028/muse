# -*- coding: utf-8 -*-
"""Hybrid schema-channel integration tests (Chroma + fake graph store).

Search returns normal memories plus L6 schema. L0 user profile content is
retrieved separately through ``get_user_profile()`` and must not appear here.
"""

import asyncio
import random
import uuid

import pytest
import json

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus
from hy_memory.pipelines.base import ReadRequest


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
    return MemoryConfig.from_dict({"vector_store": {
        "provider": "chroma",
        "collection_name": f"t_hv2_{uuid.uuid4().hex[:8]}",
        "persist_directory": str(tmp_path / "chroma"),
        "embedding_dims": 32,
    }})


@pytest.fixture
def store(config):
    from hy_memory.data.vector_store_chroma import ChromaVectorStore
    vs = ChromaVectorStore(config)
    run(vs.initialize())
    yield vs
    run(vs.close())


def _mk(node_id, content, layer, vec, uid="u1", aid="a1"):
    n = MemoryNode(
        node_id=node_id, user_id=uid, agent_id=aid, session_id="s1",
        content=content, layer=layer, status=MemoryStatus.ACTIVE, is_latest=True,
    )
    n.embedding = vec
    return n


class _FakeGraph:
    """最小 graph_store：正路 vector_search 返回预设 L6；反路 find_referencing_memories
    按 vdb_node_id → 支撑的 L6 映射返回边。"""
    def __init__(
        self, l6_forward, support_map, evidence_counts=None,
        catalog_node=None, internal_nodes=None,
    ):
        # l6_forward: [{node_id, content, score}]，正路命中
        self._fwd = l6_forward
        # support_map: {vdb_node_id: [l6_node_id, ...]} 反查
        self._support = support_map
        self._ev = evidence_counts or {}
        self._catalog_node = catalog_node
        self._internal_nodes = list(internal_nodes or [])
        if catalog_node is not None and catalog_node not in self._internal_nodes:
            self._internal_nodes.append(catalog_node)
        self.vector_search_calls = 0
        self.reverse_calls = 0

    async def vector_search(
        self, query_embedding, isolation_key="", layers=None,
        limit=10, score_threshold=0.0, user_id="",
        include_sources=None, exclude_sources=None,
    ):
        self.vector_search_calls += 1
        out = []
        for r in self._fwd:
            if r["score"] >= score_threshold:
                out.append({
                    "node_id": r["node_id"], "content": r["content"],
                    "layer": "l6_schema", "confidence": r["score"],
                    "score": r["score"], "custom_json": "{}",
                    "source": "graph_vector_search",
                })
        return out[:limit]

    async def get_evidence_vdbrefs(self, memory_node_id):
        return [{"node_id": f"e{i}", "layer": "l2_fact"}
                for i in range(self._ev.get(memory_node_id, 0))]

    async def find_referencing_memories(
        self, vdb_node_ids, limit=50,
        include_sources=None, exclude_sources=None,
    ):
        self.reverse_calls += 1
        rows = []
        for vid in vdb_node_ids:
            for l6 in self._support.get(vid, []):
                rows.append({
                    "node_id": l6, "content": f"schema-{l6}", "layer": "l6_schema",
                    "confidence": 0.8, "evidence_vdb_id": vid, "source": "reverse_evidence",
                })
        return rows[:limit]

    async def get_all_nodes(self, isolation_key, layer=None, status=None, limit=100):
        return self._internal_nodes[:limit]


def _seed_and_reader(store, config, graph_store):
    from hy_memory.pipelines.reader_hybrid import HybridReadPipeline

    qvec = _emb()
    # L0 basic_info（profile 置顶候选），与 query 较相近
    l0vec = [0.9 * a for a in qvec]
    n0 = l0vec[0]  # not normalized but fine for chroma cosine ordering
    run(store.upsert(_mk("L0", "用户叫张三", MemoryLayer.L0_BASIC_INFO, _norm(l0vec))))
    # 两条 L2 fact（normal），其中 F1 与 query 相近会被命中
    run(store.upsert(_mk("F1", "用户喜欢爬山", MemoryLayer.L2_FACT, _norm([0.8*a for a in qvec]))))
    run(store.upsert(_mk("F2", "用户养了猫", MemoryLayer.L2_FACT, _emb())))

    reader = HybridReadPipeline(config, vector_store=store, graph_store=graph_store)
    run(reader.initialize())

    class _FakeEmbed:
        async def embed(self, text, use_cache=True):
            return list(qvec)
        async def embed_with_meta(self, text, use_cache=True):
            return list(qvec), {"cache_hit": False, "model": "fake"}
        async def embed_batch(self, texts):
            return [list(qvec) for _ in texts]
        async def embed_queued(self, text, use_cache=True):
            return list(qvec)
    reader._embed_service = _FakeEmbed()
    return reader, qvec


def _norm(v):
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def _buckets(resp):
    """把 reader 输出按 layer 分桶（模拟 client 分桶）。"""
    schema, normal = [], []
    for m in resp.memories:
        if m["layer"] == "l6_schema":
            schema.append(m)
        else:
            normal.append(m)
    return schema, normal


class TestHybridProfileRefactor:
    def test_pro_no_graph_search_excludes_l0(self, store, config):
        reader, _ = _seed_and_reader(store, config, graph_store=None)
        req = ReadRequest(query="爱好", user_ids=["u1"], agent_ids=["a1"],
                          limit=10, min_score=0.0, schema_min_score=0.2)
        resp = run(reader.read(req))
        schema, normal = _buckets(resp)
        assert schema == []
        assert all(m["layer"] != "l0_basic_info" for m in resp.memories)
        assert any(m["layer"] == "l2_fact" for m in normal)

    def test_ultra_search_returns_fused_l6_without_l0(self, store, config):
        # 正路命中 S_fwd（高分）；反路：F1 支撑 S_rev（反查），S_rev 不在正路
        graph = _FakeGraph(
            l6_forward=[{"node_id": "S_fwd", "content": "schema-forward", "score": 0.7}],
            support_map={"F1": ["S_rev"]},   # F1 被 normal 命中后反查出 S_rev
            evidence_counts={"S_fwd": 3},
        )
        reader, _ = _seed_and_reader(store, config, graph_store=graph)
        req = ReadRequest(query="爱好", user_ids=["u1"], agent_ids=["a1"],
                          limit=10, min_score=0.0, schema_min_score=0.2)
        resp = run(reader.read(req))
        schema, _ = _buckets(resp)
        schema_ids = [m["memory_id"] for m in schema]
        assert "L0" not in {m["memory_id"] for m in resp.memories}
        assert "S_fwd" in schema_ids
        assert "S_rev" in schema_ids

    def test_schema_limit_counts_only_l6(self, store, config):
        graph = _FakeGraph(
            l6_forward=[
                {"node_id": "S1", "content": "schema-one", "score": 0.9},
                {"node_id": "S2", "content": "schema-two", "score": 0.8},
            ],
            support_map={},
        )
        reader, _ = _seed_and_reader(store, config, graph_store=graph)
        req = ReadRequest(
            query="爱好", user_ids=["u1"], agent_ids=["a1"],
            limit=10, min_score=0.0, schema_min_score=0.2, schema_limit=1,
        )
        resp = run(reader.read(req))
        schema, normal = _buckets(resp)
        assert len(schema) == 1
        assert any(row["layer"] == "l2_fact" for row in normal)
        assert all(row["layer"] != "l0_basic_info" for row in resp.memories)

    def test_hidden_l0_context_is_not_gated_by_schema_min_score(
        self, store, config,
    ):
        reader, _ = _seed_and_reader(
            store, config, graph_store=_FakeGraph([], {}),
        )
        req = ReadRequest(
            query="爱好", user_ids=["u1"], agent_ids=["a1"],
            limit=10, min_score=0.0, schema_min_score=1.1,
        )
        resp = run(reader.read(req))
        assert resp.extra["channels"]["hidden_l0_context"] == 1
        assert all(row["layer"] != "l0_basic_info" for row in resp.memories)

    def test_schema_limit_zero_skips_l6_graph_recall(self, store, config):
        graph = _FakeGraph(
            [{"node_id": "S1", "content": "schema-one", "score": 0.9}],
            {"F1": ["S_rev"]},
        )
        reader, _ = _seed_and_reader(store, config, graph_store=graph)
        req = ReadRequest(
            query="爱好", user_ids=["u1"], agent_ids=["a1"],
            limit=10, min_score=0.0, schema_limit=0,
        )
        resp = run(reader.read(req))
        schema, normal = _buckets(resp)
        assert schema == []
        assert any(row["layer"] == "l2_fact" for row in normal)
        assert graph.vector_search_calls == 0
        assert graph.reverse_calls == 0

    def test_ultra_catalog_is_internal_to_search_without_consuming_schema_slot(
        self, store, config, monkeypatch,
    ):
        catalog_node = MemoryNode(
            node_id="CAT", user_id="u1", agent_id="a1",
            layer=MemoryLayer.L6_SCHEMA, status=MemoryStatus.ACTIVE,
            content=(
                "System2 verified persona catalog:\n"
                "- [habits_items] The user carries a steel bottle every day."
            ),
            custom={
                "schema_kind": "balanced_persona_catalog",
                "balanced_catalog_version": 1,
                "selected_count": 1,
            },
        )
        graph = _FakeGraph(
            l6_forward=[
                {"node_id": "CAT", "content": catalog_node.content, "score": 0.99,
                 "custom_json": json.dumps(catalog_node.custom)},
                {"node_id": "S_fwd", "content": "schema-forward", "score": 0.7},
            ],
            support_map={"F1": ["CAT", "S_rev"]},
            catalog_node=catalog_node,
        )
        # Preserve per-hit custom JSON from this test's forward fixtures.
        original_vector_search = graph.vector_search
        async def vector_search(*args, **kwargs):
            rows = await original_vector_search(*args, **kwargs)
            for fixture, row in zip(graph._fwd, rows):
                row["custom_json"] = fixture.get("custom_json", "{}")
            return rows
        graph.vector_search = vector_search
        original_reverse = graph.find_referencing_memories
        async def reverse(*args, **kwargs):
            rows = await original_reverse(*args, **kwargs)
            for row in rows:
                row["custom_json"] = json.dumps(
                    catalog_node.custom if row["node_id"] == "CAT" else {}
                )
            return rows
        graph.find_referencing_memories = reverse

        monkeypatch.setenv(
            "MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true"
        )
        reader, _ = _seed_and_reader(store, config, graph_store=graph)
        req = ReadRequest(
            query="爱好", user_ids=["u1"], agent_ids=["a1"],
            limit=10, min_score=0.0, schema_min_score=0.2, schema_limit=6,
        )
        resp = run(reader.read(req))
        schema, _ = _buckets(resp)
        ids = [row["memory_id"] for row in schema]
        assert "CAT" not in ids
        assert "S_fwd" in ids and "S_rev" in ids
        assert "L0" not in {row["memory_id"] for row in resp.memories}
        assert all("steel bottle" not in row["content"] for row in resp.memories)

    def test_ultra_catalog_and_supplement_are_internal_to_search(
        self, store, config, monkeypatch,
    ):
        catalog_node = MemoryNode(
            node_id="CAT", user_id="u1", agent_id="a1",
            layer=MemoryLayer.L6_SCHEMA, status=MemoryStatus.ACTIVE,
            content=(
                "System2 verified persona catalog:\n"
                "- [habits_items] The user carries a steel bottle every day."
            ),
            custom={
                "schema_kind": "balanced_persona_catalog",
                "balanced_catalog_version": 4,
                "selected_count": 1,
            },
        )
        supplement_node = MemoryNode(
            node_id="catalog_supplement_X", user_id="u1", agent_id="a1",
            layer=MemoryLayer.L6_SCHEMA, status=MemoryStatus.ACTIVE,
            content=(
                "System2 specific supplement (exact stored evidence):\n"
                "- [health_accessibility] The user has mild myopia."
            ),
            custom={
                "schema_kind": "specific_persona_supplement",
                "specific_supplement_version": 1,
                "selected_count": 1,
            },
        )
        graph = _FakeGraph(
            l6_forward=[
                {"node_id": "CAT", "content": catalog_node.content, "score": 0.99,
                 "custom_json": json.dumps(catalog_node.custom)},
                {"node_id": "catalog_supplement_X", "content": supplement_node.content,
                 "score": 0.98, "custom_json": json.dumps(supplement_node.custom)},
                {"node_id": "S_fwd", "content": "schema-forward", "score": 0.7},
            ],
            support_map={"F1": ["CAT", "catalog_supplement_X", "S_rev"]},
            internal_nodes=[catalog_node, supplement_node],
        )
        original_vector_search = graph.vector_search

        async def vector_search(*args, **kwargs):
            rows = await original_vector_search(*args, **kwargs)
            for fixture, row in zip(graph._fwd, rows):
                row["custom_json"] = fixture.get("custom_json", "{}")
            return rows

        graph.vector_search = vector_search
        original_reverse = graph.find_referencing_memories

        async def reverse(*args, **kwargs):
            rows = await original_reverse(*args, **kwargs)
            custom_by_id = {
                "CAT": catalog_node.custom,
                "catalog_supplement_X": supplement_node.custom,
            }
            for row in rows:
                row["custom_json"] = json.dumps(custom_by_id.get(row["node_id"], {}))
            return rows

        graph.find_referencing_memories = reverse
        monkeypatch.setenv(
            "MEMORY_HYBRID_V2_BALANCED_CATALOG_L0_ENABLED", "true"
        )
        monkeypatch.setenv(
            "MEMORY_HYBRID_V2_SPECIFIC_SUPPLEMENT_L0_ENABLED", "true"
        )
        reader, _ = _seed_and_reader(store, config, graph_store=graph)
        req = ReadRequest(
            query="爱好", user_ids=["u1"], agent_ids=["a1"],
            limit=10, min_score=0.0, schema_min_score=0.2, schema_limit=6,
        )
        resp = run(reader.read(req))
        schema, _ = _buckets(resp)
        ids = [row["memory_id"] for row in schema]
        assert "CAT" not in ids
        assert "catalog_supplement_X" not in ids
        assert "S_fwd" in ids and "S_rev" in ids
        assert "L0" not in {row["memory_id"] for row in resp.memories}
        assert all("mild myopia" not in row["content"] for row in resp.memories)
