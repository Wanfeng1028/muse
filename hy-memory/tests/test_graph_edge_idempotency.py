"""图写入的幂等性，以及重建前的清理。

`add_edge` 此前用 `CREATE`，而同一对节点之间会**反复**建同类型边：

- `UPDATE` 是原地更新（`node_id` 不变），一条记忆被合并多次就多次参与投影；
  两条老节点若再次同批出现，`co_occurs` 就重复建。线上实测一条记忆被 UPDATE 了 7 次。
- System 2 的 agent 循环可能对同一对反复调用 `add_edge`。

线上实测（eval 库）：**20.4 万对重复、最严重一对 32 份**，其中 99% 是 System 2 写的
无类型 `related`。重复边不放大打分（`build_adjacency` 折叠成最强的一条），但会吃掉
`get_related_edges` 的 `max_edges` 预算 —— Cypher 的 `LIMIT` 先截断、去重在 Python 侧，
于是重复边挤掉了本该返回的真实边。
"""

import asyncio
import tempfile

import pytest

from hy_memory.config import MemoryConfig
from hy_memory.models.memory import MemoryLayer, MemoryNode


def _cfg(path: str) -> MemoryConfig:
    cfg = MemoryConfig()
    cfg.graph_store.provider = "kuzu"
    cfg.graph_store.db_path = path
    return cfg


async def _store():
    from hy_memory.data.graph_store_kuzu import KuzuGraphStore

    gs = KuzuGraphStore(_cfg(tempfile.mkdtemp() + "/g"))
    await gs.initialize()
    return gs


def _node(content: str, *, session="s1", layer=MemoryLayer.L2_FACT, tags=None):
    return MemoryNode(
        user_id="u", agent_id="a", session_id=session,
        layer=layer, content=content, tags=tags or [],
    )


class TestAddEdgeIdempotent:
    @pytest.mark.asyncio
    async def test_repeated_add_edge_yields_one_edge(self):
        gs = await _store()
        try:
            a, b = _node("m0"), _node("m1")
            await gs.upsert_memory_node(a)
            await gs.upsert_memory_node(b)
            for w in (0.5, 0.9, 0.7):
                await gs.add_edge(
                    a.node_id, b.node_id, "RELATED_TO",
                    {"relation_type": "co_occurs", "weight": w},
                )
            rows = await gs._run(
                "MATCH (x:Memory)-[r:RELATED_TO]->(y:Memory) RETURN count(*);"
            )
            # 双向各一条 = 2；用 CREATE 时会是 6
            assert int(rows[0][0]) == 2
        finally:
            await gs.close()

    @pytest.mark.asyncio
    async def test_on_match_keeps_max_weight(self):
        """ON MATCH 取较大权重 —— 与读侧 build_adjacency"折叠成最强"的语义一致。"""
        gs = await _store()
        try:
            a, b = _node("m0"), _node("m1")
            await gs.upsert_memory_node(a)
            await gs.upsert_memory_node(b)
            for w in (0.5, 0.9, 0.7):
                await gs.add_edge(
                    a.node_id, b.node_id, "RELATED_TO",
                    {"relation_type": "co_occurs", "weight": w},
                )
            edges = await gs.get_related_edges([a.node_id])
            co = [e for e in edges if e["relation_type"] == "co_occurs"]
            assert len(co) == 1
            assert co[0]["weight"] == pytest.approx(0.9)
        finally:
            await gs.close()

    @pytest.mark.asyncio
    async def test_different_relation_types_coexist(self):
        """同一对节点之间**可以**有多种关系 —— 去重不能把它们合并掉。"""
        gs = await _store()
        try:
            a, b = _node("m0"), _node("m1")
            await gs.upsert_memory_node(a)
            await gs.upsert_memory_node(b)
            for rt in ("co_occurs", "causes", "elaborates"):
                await gs.add_edge(
                    a.node_id, b.node_id, "RELATED_TO",
                    {"relation_type": rt, "weight": 0.8},
                )
            edges = await gs.get_related_edges([a.node_id])
            assert {e["relation_type"] for e in edges} == {
                "co_occurs", "causes", "elaborates",
            }
        finally:
            await gs.close()

    @pytest.mark.asyncio
    async def test_reprojecting_same_batch_is_stable(self):
        """回归线上现场：同一批节点被投影两次（UPDATE 让老节点再次入批）。"""
        from hy_memory.pipelines._graph.projector import project_memories_to_graph

        gs = await _store()
        try:
            nodes = [_node(f"m{i}", tags=["health"]) for i in range(3)]
            for _ in range(2):
                await project_memories_to_graph(
                    graph_store=gs, embed_service=None, nodes=nodes,
                )
            rows = await gs._run(
                "MATCH (x:Memory)-[r:RELATED_TO]->(y:Memory) RETURN count(*);"
            )
            # 3 个节点两两相连 = 3 对，双向 = 6 条。投影两次仍应是 6。
            assert int(rows[0][0]) == 6
        finally:
            await gs.close()


class TestClearProjection:
    @pytest.mark.asyncio
    async def test_clears_l2_and_orphan_topics(self):
        gs = await _store()
        try:
            for i in range(3):
                n = _node(f"m{i}", session=f"s{i}", tags=["health"])
                await gs.upsert_memory_node(n)
                # 故意用旧的（带 session 的）键建 Topic，模拟碎片化历史数据
                await gs.add_topic_tag(n.node_id, "health", n.get_isolation_key())
            res = await gs.clear_projection("u", "a", layer="l2_fact")
            assert res["memories"] == 3
            assert res["topics"] == 3
            rows = await gs._run("MATCH (t:Topic) RETURN count(*);")
            assert int(rows[0][0]) == 0
        finally:
            await gs.close()

    @pytest.mark.asyncio
    async def test_does_not_touch_l6_schema(self):
        """关键护栏：一个用户的 Memory 里还有 System 2 写的 l6_schema，
        无条件删会毁掉 ultra 的数据。"""
        gs = await _store()
        try:
            await gs.upsert_memory_node(_node("fact"))
            await gs.upsert_memory_node(_node("schema", layer=MemoryLayer.L6_SCHEMA))
            await gs.clear_projection("u", "a", layer="l2_fact")
            rows = await gs._run(
                "MATCH (m:Memory {layer:'l6_schema'}) RETURN count(*);"
            )
            assert int(rows[0][0]) == 1
            rows = await gs._run("MATCH (m:Memory) RETURN count(*);")
            assert int(rows[0][0]) == 1, "只该剩 l6_schema 那一个"
        finally:
            await gs.close()

    @pytest.mark.asyncio
    async def test_other_users_untouched(self):
        gs = await _store()
        try:
            await gs.upsert_memory_node(_node("mine"))
            other = MemoryNode(
                user_id="u2", agent_id="a", session_id="s1",
                layer=MemoryLayer.L2_FACT, content="theirs",
            )
            await gs.upsert_memory_node(other)
            await gs.clear_projection("u", "a", layer="l2_fact")
            rows = await gs._run(
                "MATCH (m:Memory {user_id:'u2'}) RETURN count(*);"
            )
            assert int(rows[0][0]) == 1
        finally:
            await gs.close()

    def test_base_default_is_noop(self):
        """未实现该能力的后端不做任何事，不能抛。"""
        import inspect

        from hy_memory.data.graph_store_base import GraphStoreBase

        src = inspect.getsource(GraphStoreBase.clear_projection)
        assert "l2_fact" in src and "l6_schema" in src

    def test_all_backends_implement_it(self):
        from hy_memory.data.graph_store_base import GraphStoreBase
        from hy_memory.data.graph_store_kuzu import KuzuGraphStore
        from hy_memory.data.graph_store_neo4j import Neo4jGraphStore

        for cls in (KuzuGraphStore, Neo4jGraphStore):
            assert cls.clear_projection is not GraphStoreBase.clear_projection, (
                f"{cls.__name__} 未自己实现 clear_projection，会静默不清理"
            )


class TestNoCreateLeftInAddEdge:
    """静态守卫：退回 CREATE 就会重新引入重复边。"""

    @pytest.mark.parametrize("module_path", [
        "hy_memory.data.graph_store_kuzu",
        "hy_memory.data.graph_store_neo4j",
    ])
    def test_add_edge_uses_merge(self, module_path):
        import importlib
        import inspect

        mod = importlib.import_module(module_path)
        cls = next(
            v for k, v in vars(mod).items()
            if isinstance(v, type) and hasattr(v, "add_edge")
            and v.__module__ == module_path
        )
        src = inspect.getsource(cls.add_edge)
        assert "MERGE" in src, f"{module_path}.add_edge 没用 MERGE"
        assert "CREATE (a)-[:RELATED_TO" not in src, (
            f"{module_path}.add_edge 仍在用 CREATE 建边"
        )
        assert "ON MATCH" in src, "缺 ON MATCH，重复调用不会更新权重"


class TestBuildMemoryGraphClearFirst:
    def test_client_exposes_clear_first(self):
        import inspect

        from hy_memory.client import HyMemoryClient

        for fn in ("build_memory_graph", "async_build_memory_graph"):
            params = inspect.signature(getattr(HyMemoryClient, fn)).parameters
            assert "clear_first" in params, f"{fn} 缺 clear_first"
            assert params["clear_first"].default is False, "默认必须为 False"

    def test_clear_scoped_to_l2_fact(self):
        import inspect

        from hy_memory.client import HyMemoryClient

        src = inspect.getsource(HyMemoryClient.async_build_memory_graph)
        assert "clear_projection(" in src
        assert "L2_FACT" in src, "清理必须按 layer 收窄，否则会删掉 l6_schema"
