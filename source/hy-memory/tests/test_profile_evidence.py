# -*- coding: utf-8 -*-
"""
reverse_lookup_l6 单元测试（纯逻辑，mock graph_store）。

反路：从一批 VDB node_id 反查支撑它们的 L6 schema，按支撑度（distinct
evidence_vdb_id 数）降序。验证：聚合支撑度、过滤非 l6 层、排序、空/异常兜底。
"""

import asyncio

import pytest

from hy_memory.data.graph_store_kuzu import KuzuGraphStore
from hy_memory.data.graph_store_neo4j import Neo4jGraphStore
from hy_memory.models.memory import MemoryLayer, MemoryStatus
from hy_memory.pipelines._retrieval.profile_evidence import reverse_lookup_l6


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeGraph:
    """find_referencing_memories 返回预设的 (Memory, VdbRef) 边列表。"""
    def __init__(self, rows, raise_exc=False):
        self._rows = rows
        self._raise = raise_exc
        self.called_with = None

    async def find_referencing_memories(self, vdb_node_ids, limit=50):
        self.called_with = (list(vdb_node_ids), limit)
        if self._raise:
            raise RuntimeError("graph down")
        return list(self._rows)


def _edge(node_id, ev_id, layer="l6_schema", content="schema-content"):
    return {
        "node_id": node_id, "content": content, "layer": layer,
        "confidence": 0.9, "evidence_vdb_id": ev_id, "source": "reverse_evidence",
    }


class TestReverseLookupL6:
    def test_support_degree_aggregation_and_order(self):
        # s1 被 v1/v2/v3 支撑（3），s2 被 v1（1）。s1 应排前。
        rows = [
            _edge("s1", "v1"), _edge("s1", "v2"), _edge("s1", "v3"),
            _edge("s2", "v1"),
        ]
        g = _FakeGraph(rows)
        out = run(reverse_lookup_l6(g, ["v1", "v2", "v3"], limit=50))
        assert [h["node_id"] for h in out] == ["s1", "s2"]
        assert out[0]["_support_count"] == 3
        assert out[1]["_support_count"] == 1
        # score 归一化：最高支撑度 = 1.0
        assert out[0]["score"] == 1.0
        assert abs(out[1]["score"] - 1 / 3) < 1e-6
        # 输出层兼容字段
        assert out[0]["layer"] == "l6_schema"
        assert out[0]["retrieval_source"] == "schema_reverse"
        assert out[0]["node"] is None
        assert out[0]["content"] == "schema-content"
        # 透传 vdb_node_ids
        assert g.called_with == (["v1", "v2", "v3"], 50)

    def test_distinct_evidence_not_double_counted(self):
        # 同一 (s1, v1) 边重复出现 → 支撑度仍按 distinct evidence 算 = 1
        rows = [_edge("s1", "v1"), _edge("s1", "v1")]
        out = run(reverse_lookup_l6(_FakeGraph(rows), ["v1"]))
        assert len(out) == 1
        assert out[0]["_support_count"] == 1

    def test_non_l6_layers_filtered(self):
        rows = [_edge("s1", "v1"), _edge("m1", "v1", layer="l2_fact")]
        out = run(reverse_lookup_l6(_FakeGraph(rows), ["v1"]))
        assert [h["node_id"] for h in out] == ["s1"]

    def test_empty_inputs(self):
        assert run(reverse_lookup_l6(_FakeGraph([]), [])) == []
        assert run(reverse_lookup_l6(None, ["v1"])) == []
        assert run(reverse_lookup_l6(_FakeGraph([]), ["v1"])) == []

    def test_no_method_returns_empty(self):
        class _Bare:
            pass
        assert run(reverse_lookup_l6(_Bare(), ["v1"])) == []

    def test_exception_swallowed(self):
        out = run(reverse_lookup_l6(_FakeGraph([], raise_exc=True), ["v1"]))
        assert out == []


@pytest.mark.parametrize(
    ("store_class", "catalog_filter"),
    [
        (Neo4jGraphStore, "NOT m.node_id STARTS WITH 'catalog_'"),
        (KuzuGraphStore, "NOT starts_with(m.node_id, 'catalog_')"),
    ],
)
def test_store_filters_catalog_before_reverse_recall_limit(
    store_class, catalog_filter,
):
    """Catalog audit edges must not consume the bounded reverse row budget."""
    store = store_class.__new__(store_class)
    if store_class is KuzuGraphStore:
        store._available = True
    queries = []

    async def capture(query, params=None):
        queries.append((query, params))
        return []

    store._run = capture
    assert run(store.find_referencing_memories(["f1"], limit=7)) == []
    assert len(queries) == 1
    query = queries[0][0]
    assert catalog_filter in query
    assert query.index(catalog_filter) < query.index("LIMIT")


@pytest.mark.parametrize("store_class", [Neo4jGraphStore, KuzuGraphStore])
def test_graph_store_get_nodes_by_user_filters_user_layer_and_status(store_class):
    store = store_class.__new__(store_class)
    if store_class is KuzuGraphStore:
        store._available = True
    queries = []

    async def capture(query, params=None):
        queries.append((query, params or {}))
        return []

    store._run = capture
    assert run(store.get_nodes_by_user(
        "u1", layer=MemoryLayer.L6_SCHEMA,
        status=MemoryStatus.ACTIVE, limit=17,
    )) == []
    query, params = queries[-1]
    assert "m.user_id" in query
    assert "m.layer" in query
    assert "m.status" in query
    assert params["uid"] == "u1"
    assert params["layer"] == MemoryLayer.L6_SCHEMA.value
    assert params["status"] == MemoryStatus.ACTIVE.value
