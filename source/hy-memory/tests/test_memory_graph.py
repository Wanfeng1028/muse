"""记忆关系图（pro 模式）测试。

覆盖三层：
1. 读侧数学：用法 A 传播 / 用法 B 阈值松弛 / 用法 C 路径（纯函数，无 I/O）
2. 写侧建边：projector 的四种边来源 + 同步契约
3. Kuzu 端到端：投影 → get_related_edges → Topic 归一化

设计文档：docs/pro_graph_design.md
"""

from typing import Any, Dict

import pytest
from unittest.mock import AsyncMock

from hy_memory.pipelines._graph.rerank import (
    TYPE_PRIOR,
    build_adjacency,
    collect_directed_edges,
    edge_prior,
    find_relation_paths,
    propagate_support,
    relax_admission,
)
from hy_memory.pipelines._graph.rerank import (
    apply_temporal_affinity,
    apply_type_quota,
    edge_group,
    normalize_by_degree,
    reachable_within,
)
from hy_memory.pipelines._graph.topic_summary import (
    SUMMARY_KIND_TOPIC,
    covered_count_of,
    maybe_summarize_topics,
)
from hy_memory.pipelines._graph.projector import (
    LLM_RELATION_TYPES,
    RELATION_CO_OCCURS,
    RELATION_SEMANTIC_NEIGHBOR,
    project_memories_to_graph,
    sync_graph_on_shadow,
    sync_graph_on_supersede,
)
from hy_memory.models.memory import MemoryLayer, MemoryNode, MemoryStatus


def _edge(src, tgt, rtype="causes", weight=1.0, status="active", directed=False):
    return {
        "source_id": src, "target_id": tgt, "relation_type": rtype,
        "weight": weight, "target_status": status, "target_layer": "l2_fact",
        "directed": directed,
    }


# ================================================================
# 邻接表 / 类型先验
# ================================================================

class TestAdjacency:
    def test_edges_are_undirected(self):
        adj = build_adjacency([_edge("a", "b")])
        assert [n for n, _t, _w in adj["a"]] == ["b"]
        assert [n for n, _t, _w in adj["b"]] == ["a"]

    def test_effective_weight_is_weight_times_prior(self):
        adj = build_adjacency([_edge("a", "b", "causes", weight=0.5)])
        _nb, _rt, eff = adj["a"][0]
        assert eff == pytest.approx(0.5 * TYPE_PRIOR["causes"])

    def test_shadow_targets_are_dropped(self):
        """被判重逻辑删除的记忆不能从图里绕回来。"""
        adj = build_adjacency([_edge("a", "b", status="shadow")])
        assert adj == {}

    def test_self_loops_and_incomplete_edges_ignored(self):
        assert build_adjacency([_edge("a", "a")]) == {}
        assert build_adjacency([{"source_id": "a"}]) == {}

    def test_parallel_edges_collapse_to_strongest(self):
        """同一对节点的多种关系折叠成一条，取先验最高的那种。

        度数要数"不同邻居"而不是"平行边数"，否则 hub 降权会被平行边稀释、
        支持度会重复计。
        """
        adj = build_adjacency([
            _edge("a", "b", "semantic_neighbor", weight=1.0),
            _edge("a", "b", "causes", weight=1.0),
        ])
        assert len(adj["a"]) == 1
        nb, rtype, eff = adj["a"][0]
        assert nb == "b" and rtype == "causes"
        assert eff == pytest.approx(TYPE_PRIOR["causes"])

    def test_unknown_relation_gets_default_prior(self):
        assert edge_prior("no_such_relation") == 0.5
        assert edge_prior(None) == 0.5

    def test_semantic_neighbor_prior_is_lowest(self):
        """semantic_neighbor 与向量检索高度冗余，先验必须最低。"""
        assert TYPE_PRIOR["semantic_neighbor"] < TYPE_PRIOR["co_occurs"]
        assert TYPE_PRIOR["co_occurs"] < TYPE_PRIOR["causes"]


# ================================================================
# 用法 A：池内支持度传播
# ================================================================

class TestPropagateSupport:
    def test_linked_pair_both_rise_above_unlinked(self):
        """文档 §3.1 的例子：互相佐证的一对应该浮到无边候选之上。"""
        scores = {"m2": 0.55, "m7": 0.53, "m3": 0.52, "m8": 0.51}
        adj = build_adjacency([_edge("m2", "m3", "causes")])
        out, support = propagate_support(scores, adj, beta=0.15)

        assert out["m2"] > out["m3"] > out["m7"] > out["m8"]
        assert out["m7"] == 0.53 and out["m8"] == 0.51  # 无边支持 → 分数不变
        assert support["m2"] > 0 and support["m7"] == 0

    def test_does_not_introduce_new_candidates(self):
        """A 的核心保证：召回集合不变，recall 恒定。"""
        scores = {"a": 0.6, "b": 0.5}
        adj = build_adjacency([_edge("a", "outside")])
        out, _ = propagate_support(scores, adj, beta=0.15)
        assert set(out) == {"a", "b"}

    def test_only_propagates_within_pool(self):
        """池外的强节点不该给池内节点加分。"""
        adj = build_adjacency([_edge("a", "outside", weight=1.0)])
        out, support = propagate_support({"a": 0.5, "b": 0.4}, adj, beta=0.15)
        assert out["a"] == 0.5
        assert support["a"] == 0.0

    def test_hub_penalty_via_degree_normalization(self):
        """度数归一化：高度数节点单条边的贡献被摊薄（tag hub 问题的解药）。"""
        scores = {"hub": 0.5, "x1": 0.5, "x2": 0.5, "x3": 0.5, "x4": 0.5,
                  "lo": 0.5, "y1": 0.5}
        hub_adj = build_adjacency([
            _edge("hub", f"x{i}", "co_occurs") for i in range(1, 5)
        ])
        lo_adj = build_adjacency([_edge("lo", "y1", "co_occurs")])

        _o1, sup_hub = propagate_support(scores, hub_adj, beta=0.15)
        _o2, sup_lo = propagate_support(scores, lo_adj, beta=0.15)
        # 4 条边 / sqrt(4) = 2× 单边；而不是 4× —— 归一化生效
        assert sup_hub["hub"] == pytest.approx(sup_lo["lo"] * 2.0)

    def test_beta_zero_is_noop(self):
        scores = {"a": 0.6, "b": 0.5}
        adj = build_adjacency([_edge("a", "b")])
        out, _ = propagate_support(scores, adj, beta=0.0)
        assert out == scores

    def test_support_cap_bounds_the_nudge(self):
        scores = {"a": 0.5, "b": 1.0, "c": 1.0, "d": 1.0}
        adj = build_adjacency([
            _edge("a", "b"), _edge("a", "c"), _edge("a", "d"),
        ])
        capped, _ = propagate_support(scores, adj, beta=0.2, support_cap=0.1)
        assert capped["a"] == pytest.approx(0.5 + 0.2 * 0.1)

    def test_empty_inputs(self):
        assert propagate_support({}, {}, beta=0.1) == ({}, {})


# ================================================================
# 用法 B：阈值松弛
# ================================================================

class TestRelaxAdmission:
    def test_hard_gate_admits_near_seed_sim(self):
        """硬闸：sim ≥ seed_sim − δ。seed=0.72 → 门槛 0.52。"""
        adj = build_adjacency([_edge("knee", "running", "causes", weight=1.0)])
        out = relax_admission(
            seed_scores={"knee": 0.72},
            adjacency=adj,
            candidate_sims={"running": 0.55},
            min_score=0.4, gamma=0.3, seed_floor=0.6, seed_sim_delta=0.2,
        )
        assert len(out) == 1
        assert out[0]["node_id"] == "running"
        assert out[0]["threshold"] == pytest.approx(0.52)
        assert out[0]["sim"] == 0.55

    def test_hard_gate_rejects_far_below_seed(self):
        """旧 gamma 路径会捞回 0.35；硬闸 δ=0.2 时相对 seed=0.72 进不来。"""
        adj = build_adjacency([_edge("knee", "running", "causes", weight=1.0)])
        out = relax_admission(
            seed_scores={"knee": 0.72},
            adjacency=adj,
            candidate_sims={"running": 0.35},
            min_score=0.4, gamma=0.3, seed_floor=0.6, seed_sim_delta=0.2,
        )
        assert out == []

    def test_hard_gate_rejects_junk(self):
        adj = build_adjacency([_edge("seed", "junk", "causes", weight=1.0)])
        out = relax_admission(
            seed_scores={"seed": 1.0}, adjacency=adj,
            candidate_sims={"junk": 0.10},
            min_score=0.4, gamma=0.3, seed_floor=0.6, seed_sim_delta=0.2,
        )
        assert out == []

    def test_weak_seed_does_not_expand(self):
        adj = build_adjacency([_edge("weak", "cand", "causes")])
        out = relax_admission(
            seed_scores={"weak": 0.3}, adjacency=adj,
            candidate_sims={"cand": 0.39},
            min_score=0.4, gamma=0.3, seed_floor=0.6, seed_sim_delta=0.2,
        )
        assert out == []

    def test_pool_members_are_not_readmitted(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        out = relax_admission(
            seed_scores={"a": 0.9, "b": 0.5}, adjacency=adj,
            candidate_sims={"b": 0.5}, min_score=0.4, gamma=0.3,
            seed_sim_delta=0.2,
        )
        assert out == []

    def test_gamma_zero_disables_use_b(self):
        adj = build_adjacency([_edge("a", "c", "causes")])
        assert relax_admission(
            seed_scores={"a": 0.9}, adjacency=adj,
            candidate_sims={"c": 0.75}, min_score=0.4, gamma=0.0,
            seed_sim_delta=0.2,
        ) == []

    def test_max_admit_caps_output(self):
        adj = build_adjacency([
            _edge("seed", f"c{i}", "causes") for i in range(10)
        ])
        out = relax_admission(
            seed_scores={"seed": 1.0}, adjacency=adj,
            candidate_sims={f"c{i}": 0.85 for i in range(10)},
            min_score=0.4, gamma=0.3, max_admit=3, seed_sim_delta=0.2,
        )
        assert len(out) == 3

    def test_strongest_supporting_seed_wins(self):
        adj = build_adjacency([
            _edge("s1", "c", "semantic_neighbor", weight=1.0),
            _edge("s2", "c", "causes", weight=1.0),
        ])
        out = relax_admission(
            seed_scores={"s1": 0.9, "s2": 0.9}, adjacency=adj,
            candidate_sims={"c": 0.75}, min_score=0.4, gamma=0.3,
            seed_sim_delta=0.2,
        )
        assert out[0]["relation_type"] == "causes"  # 先验更高

    def test_channel_score_prefers_tag_over_co_occur(self):
        adj = build_adjacency([_edge("s", "c", "co_occurs")])
        out = relax_admission(
            seed_scores={"s": 0.8}, adjacency=adj,
            candidate_sims={"c": 0.65},
            gamma=0.3, seed_floor=0.5, seed_sim_delta=0.2,
            candidate_bm25={"c": 0.0},
            candidate_tag={"c": 1.0},
            candidate_temporal={"c": 1.0},
            channel_weights={
                "sem": 1.0, "bm25": 0.3, "tag": 0.5,
                "temporal": 0.2, "co_occur": 0.15, "struct": 0.25,
            },
        )
        assert len(out) == 1
        # sem*0.65 + tag*0.5*1 + temporal*0.2 + co_occur*0.15*support
        assert out[0]["score"] > out[0]["sim"]
        assert out[0]["tag_overlap"] == 1.0


class TestMergeExpansionsIntoSeeds:
    def test_merges_by_time_with_blank_line(self):
        from datetime import datetime, timezone
        from hy_memory.pipelines._graph.rerank import merge_expansions_into_seeds
        from hy_memory.models.memory import MemoryNode, MemoryLayer

        def _node(nid, text, ts):
            return MemoryNode(
                node_id=nid, user_id="u", agent_id="a",
                layer=MemoryLayer.L2_FACT, content=text,
                memory_at=datetime.fromtimestamp(ts, tz=timezone.utc),
            )

        seed = {
            "node_id": "s1", "score": 0.8,
            "node": _node("s1", "seed later", 200),
        }
        exp = {
            "node_id": "e1", "score": 0.7, "graph_via": "s1",
            "node": _node("e1", "exp earlier", 100),
        }
        out = merge_expansions_into_seeds([seed], [exp])
        assert len(out) == 1
        assert out[0]["content"] == "exp earlier\n\nseed later"
        assert out[0]["graph_merged_ids"] == ["e1"]
        assert out[0]["score"] == 0.8


# ================================================================
# 用法 C：关系路径
# ================================================================

class TestFindRelationPaths:
    def test_one_hop_path_between_two_anchors(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        paths = find_relation_paths(
            hit_scores={"a": 0.8, "b": 0.7}, adjacency=adj, high_floor=0.6,
        )
        assert len(paths) == 1
        assert paths[0]["hops"] == 1
        assert set(paths[0]["nodes"]) == {"a", "b"}

    def test_two_hop_path_carries_low_scoring_middle_node(self):
        """中间节点自己分数很低也要带上 —— 它是路径的一部分。"""
        adj = build_adjacency([
            _edge("ramen", "dana_rec", "elaborates"),
            _edge("dana_rec", "dana_chef", "co_occurs"),
        ])
        paths = find_relation_paths(
            hit_scores={"ramen": 0.85, "dana_chef": 0.65}, adjacency=adj,
            high_floor=0.6,
        )
        assert len(paths) == 1
        assert paths[0]["hops"] == 2
        assert paths[0]["nodes"][1] == "dana_rec"  # 中间节点不在 hit_scores 里

    def test_low_scoring_anchors_are_skipped(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        assert find_relation_paths(
            hit_scores={"a": 0.5, "b": 0.4}, adjacency=adj, high_floor=0.6,
        ) == []

    def test_semantic_neighbor_excluded_by_default(self):
        """两条语义相近的记忆之间连一条路径对答案没有解释价值。"""
        adj = build_adjacency([_edge("a", "b", "semantic_neighbor")])
        assert find_relation_paths(
            hit_scores={"a": 0.8, "b": 0.8}, adjacency=adj,
        ) == []
        assert len(find_relation_paths(
            hit_scores={"a": 0.8, "b": 0.8}, adjacency=adj, typed_only=False,
        )) == 1

    def test_needs_two_anchors(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        assert find_relation_paths(hit_scores={"a": 0.9}, adjacency=adj) == []

    def test_duplicate_paths_deduped(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        paths = find_relation_paths(hit_scores={"a": 0.9, "b": 0.9}, adjacency=adj)
        assert len(paths) == 1

    def test_relations_are_dicts_with_type(self):
        adj = build_adjacency([_edge("a", "b", "causes")])
        paths = find_relation_paths(hit_scores={"a": 0.9, "b": 0.9}, adjacency=adj)
        assert paths[0]["relations"][0]["type"] == "causes"
        assert "direction" not in paths[0]["relations"][0]  # 无向边不标方向

    def test_temporal_direction_is_labelled(self):
        """有向边要标方向，否则"X 之后"和"X 之前"在输出里分不开。"""
        edges = [_edge("early", "late", "temporal_next", directed=True)]
        adj = build_adjacency(edges)
        fwd = collect_directed_edges(edges)

        paths = find_relation_paths(
            hit_scores={"early": 0.9, "late": 0.8}, adjacency=adj, forward_dirs=fwd,
        )
        # 同一 anchor 对去重后只产出一条路径；方向随路径起点而定
        assert len(paths) == 1
        nodes, rel = paths[0]["nodes"], paths[0]["relations"][0]
        assert rel["type"] == "temporal_next"
        expected = "forward" if nodes == ["early", "late"] else "backward"
        assert rel["direction"] == expected


class TestCollectDirectedEdges:
    def test_only_directed_edges_collected(self):
        out = collect_directed_edges([
            _edge("a", "b", "causes", directed=False),
            _edge("x", "y", "temporal_next", directed=True),
        ])
        assert out == {("x", "y")}

    def test_type_prior_ordering(self):
        """先验排序按"能否提供向量检索拿不到的信息"来定。

        `co_occurs` 排在很高位：共同写入是**跨话题联系的主要来源**
        （"去公园/骑车/吃饭"一起写下来，三者向量互不相似但关联真实）。
        它的噪声由写侧的批大小归一化 + 读侧的度数归一化控制，而不是靠压低先验 ——
        压低先验会连带把"一批只有 2 条"这种几乎必然相关的情况也一起贬值。
        """
        p = TYPE_PRIOR
        assert p["causes"] > p["same_series"] > p["contrasts"]
        assert p["contrasts"] == p["temporal_next"] > p["co_occurs"]
        assert p["co_occurs"] > p["semantic_neighbor"]


# ================================================================
# 写侧：projector
# ================================================================

class _FakeGraphStore:
    def __init__(self, topic_memories=None, topics=None):
        self.nodes = []
        self.edges = []
        self.tags = []
        self.updates = {}
        self.temporal = []
        self._topic_memories = topic_memories or {}
        self._topics = topics or []

    async def upsert_memory_node(self, node):
        self.nodes.append(node)
        return node.node_id

    async def add_topic_tag(self, node_id, topic, isolation_key, embed_service=None,
                            similarity_threshold=0.85):
        self.tags.append((node_id, topic, isolation_key, embed_service is not None))
        return f"topic_{topic}"

    async def add_edge(self, src, tgt, edge_type, properties=None):
        self.edges.append((src, tgt, (properties or {}).get("relation_type"),
                           (properties or {}).get("weight")))
        return True

    async def update_node(self, node_id, updates):
        self.updates[node_id] = updates
        return True

    async def add_temporal_edge(self, prev_id, next_id, topic_id=""):
        self.temporal.append((prev_id, next_id, topic_id))
        return True

    async def get_topic_memories(self, topic_id, *, limit=200):
        return self._topic_memories.get(topic_id, [])

    async def get_all_topics(self, isolation_key):
        return self._topics


def _node(nid, content="c", tags=None):
    return MemoryNode(
        node_id=nid, user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L2_FACT, content=content, tags=list(tags or []),
    )


@pytest.mark.asyncio
class TestProjector:
    async def test_native_graph_batches_cover_nodes_entities_and_edges(
        self, monkeypatch,
    ):
        from datetime import datetime
        import hy_memory.pipelines._retrieval.ner as ner

        monkeypatch.setattr(
            ner, "extract_entities",
            lambda _text, for_boost=True: [
                ("Paris", "GPE"), ("Paris", "GPE"), ("OpenAI", "ORG"),
            ],
        )

        class BatchGraph(_FakeGraphStore):
            _supports_batch_memory_nodes = True
            _supports_batch_entity_mentions = True
            _supports_batch_related_edges = True
            _supports_batch_temporal_edges = True

            def __init__(self):
                super().__init__()
                self.memory_batches = []
                self.entity_batches = []
                self.edge_batches = []
                self.temporal_batches = []

            async def upsert_memory_node(self, _node):
                raise AssertionError("per-node path must not be used")

            async def upsert_memory_nodes_batch(self, nodes):
                self.memory_batches.append(list(nodes))
                return [node.node_id for node in nodes]

            async def clear_entity_mentions(self, _node_id):
                raise AssertionError("per-memory entity clear must not be used")

            async def add_entity_mention(self, *_args, **_kwargs):
                raise AssertionError("per-entity path must not be used")

            async def replace_entity_mentions_batch(self, assignments):
                self.entity_batches.append(list(assignments))
                return [
                    (memory_id, f"entity-{name}-{label}")
                    for memory_id, entities, _scope in assignments
                    for name, label in entities
                ]

            async def add_edge(self, *_args, **_kwargs):
                raise AssertionError("per-edge path must not be used")

            async def add_edges_batch(self, edges):
                self.edge_batches.append(list(edges))
                return [True] * len(edges)

            async def add_temporal_edge(self, *_args, **_kwargs):
                raise AssertionError("per-temporal-edge path must not be used")

            async def add_temporal_edges_batch(self, edges):
                self.temporal_batches.append(list(edges))
                return [True] * len(edges)

        n1 = _node("n1", "first", tags=["work"])
        n2 = _node("n2", "second", tags=["work"])
        n1.memory_at = datetime(2026, 1, 1)
        n2.memory_at = datetime(2026, 2, 1)
        gs = BatchGraph()
        stats = await project_memories_to_graph(
            graph_store=gs,
            embed_service=None,
            nodes=[n1, n2],
            neighbors_by_node={"n1": [("old-sem", 0.8)]},
            related_by_node={
                "n2": [{"target_id": "old-cause", "relation_type": "causes"}],
            },
            temporal_spine_bulk=True,
        )

        assert len(gs.memory_batches) == 1
        assert len(gs.entity_batches) == 1
        assert len(gs.edge_batches) == 1
        assert len(gs.edge_batches[0]) == 3
        assert gs.temporal_batches == [[("n1", "n2", "topic_work")]]
        assert stats == {
            "nodes": 2, "tags": 2, "entities": 4,
            "co_occurs": 1, "semantic": 1, "typed": 1, "temporal": 1,
            "errors": 0, "hierarchy_paths": 0, "hierarchy_nodes": 0,
        }

    async def test_batch_failure_falls_back_to_per_item(self):
        class FailingBatchGraph(_FakeGraphStore):
            _supports_batch_memory_nodes = True
            _supports_batch_related_edges = True

            async def upsert_memory_nodes_batch(self, _nodes):
                raise RuntimeError("transient node batch failure")

            async def add_edges_batch(self, _edges):
                raise RuntimeError("transient edge batch failure")

        gs = FailingBatchGraph()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None,
            nodes=[_node("n1"), _node("n2")],
        )

        assert [node.node_id for node in gs.nodes] == ["n1", "n2"]
        assert len(gs.edges) == 1
        assert stats["nodes"] == 2
        assert stats["co_occurs"] == 1
        assert stats["errors"] == 0

    async def test_batch_topic_capability_avoids_per_tag_calls(self):
        class BatchGraph(_FakeGraphStore):
            _supports_batch_topic_tags = True

            def __init__(self):
                super().__init__()
                self.batch_assignments = []

            async def add_topic_tag(self, *args, **kwargs):
                raise AssertionError("per-tag path must not be used")

            async def add_topic_tags_batch(self, assignments, **kwargs):
                self.batch_assignments = list(assignments)
                return [
                    (memory_id, f"topic-{tag}")
                    for memory_id, tag, _scope in assignments
                ]

        gs = BatchGraph()
        node = _node("n1", tags=["work", "travel"])
        stats = await project_memories_to_graph(
            graph_store=gs,
            embed_service=None,
            nodes=[node],
        )

        assert len(gs.batch_assignments) == 2
        assert stats["tags"] == 2

    async def test_projects_nodes_and_tags(self):
        gs = _FakeGraphStore()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=object(),
            nodes=[_node("n1", tags=["work", "health"])],
        )
        assert stats["nodes"] == 1 and stats["tags"] == 2
        # embed_service 必须透传下去，否则 Topic 不做语义归一化
        assert all(has_embed for *_x, has_embed in gs.tags)

    async def test_co_occurs_pairwise_within_batch(self):
        gs = _FakeGraphStore()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None,
            nodes=[_node("n1"), _node("n2"), _node("n3")],
        )
        assert stats["co_occurs"] == 3  # C(3,2)
        assert all(rt == RELATION_CO_OCCURS for _s, _t, rt, _w in gs.edges)

    async def test_co_occurs_skipped_for_oversized_batch(self):
        gs = _FakeGraphStore()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None,
            nodes=[_node(f"n{i}") for i in range(5)],
            co_occurs_max_batch=3,
        )
        assert stats["co_occurs"] == 0

    async def test_semantic_neighbor_respects_threshold(self):
        gs = _FakeGraphStore()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[_node("n1")],
            neighbors_by_node={"n1": [("old1", 0.80), ("old2", 0.40)]},
            edge_min_score=0.55,
        )
        assert stats["semantic"] == 1
        assert ("n1", "old1", RELATION_SEMANTIC_NEIGHBOR, 0.80) in gs.edges

    async def test_typed_relations_whitelisted(self):
        gs = _FakeGraphStore()
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[_node("n1")],
            related_by_node={"n1": [
                {"target_id": "old1", "relation_type": "causes"},
                {"target_id": "old2", "relation_type": "made_up_relation"},
            ]},
        )
        assert stats["typed"] == 1
        assert ("n1", "old1", "causes", 1.0) in gs.edges

    async def test_no_graph_store_is_noop(self):
        stats = await project_memories_to_graph(
            graph_store=None, embed_service=None, nodes=[_node("n1")],
        )
        assert stats["nodes"] == 0

    async def test_sync_contract(self):
        gs = _FakeGraphStore()
        assert await sync_graph_on_supersede(gs, ["old1"]) == 1
        assert gs.updates["old1"]["status"] == "superseded"
        assert await sync_graph_on_shadow(gs, ["dup1"]) == 1
        assert gs.updates["dup1"]["status"] == "shadow"

    async def test_llm_relation_vocabulary_is_small(self):
        """弱模型 + 大本体 = 垃圾；same_event 已按冗余删除。"""
        assert LLM_RELATION_TYPES == (
            "causes", "elaborates", "contrasts", "same_series",
        )

    @staticmethod
    def _spine_setup(member_times):
        """图给同 Topic 成员，VDB 给事件时间 —— 图里没有 memory_at。"""
        from datetime import datetime

        gs = _FakeGraphStore(topic_memories={
            "topic_work": [{"node_id": mid, "content": "c"} for mid in member_times]
        })

        class _VS:
            async def get_by_ids(self, ids):
                out = []
                for mid in ids:
                    if mid not in member_times:
                        continue
                    n = _node(mid)
                    n.memory_at = datetime.fromtimestamp(member_times[mid])
                    out.append(n)
                return out

        return gs, _VS()

    async def test_temporal_spine_picks_nearest_earlier_member(self):
        from datetime import datetime
        target_ts = datetime(2026, 5, 1).timestamp()
        gs, vs = self._spine_setup({
            "too_old": datetime(2020, 1, 1).timestamp(),
            "nearest": datetime(2026, 4, 1).timestamp(),   # 应选它
            "later": datetime(2026, 9, 1).timestamp(),     # 比新节点还晚，不能选
        })
        node = _node("new1", tags=["work"])
        node.memory_at = datetime.fromtimestamp(target_ts)

        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[node],
            vector_store=vs, temporal_spine=True,
        )
        assert stats["temporal"] == 1
        assert gs.temporal == [("nearest", "new1", "topic_work")]

    async def test_temporal_spine_no_earlier_member(self):
        from datetime import datetime
        gs, vs = self._spine_setup({
            "later": datetime(2026, 9, 1).timestamp(),
        })
        node = _node("new1", tags=["work"])
        node.memory_at = datetime(2026, 5, 1)
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[node],
            vector_store=vs, temporal_spine=True,
        )
        assert stats["temporal"] == 0 and gs.temporal == []

    async def test_temporal_spine_off_by_default(self):
        from datetime import datetime
        gs, vs = self._spine_setup({"older": datetime(2020, 1, 1).timestamp()})
        node = _node("new1", tags=["work"])
        node.memory_at = datetime(2026, 5, 1)
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[node], vector_store=vs,
        )
        assert stats["temporal"] == 0 and gs.temporal == []

    async def test_temporal_spine_needs_topic_and_memory_at(self):
        gs, vs = self._spine_setup({"older": 1.0})
        # 无 tag → 无 Topic → 无从串脊
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=[_node("n1")],
            vector_store=vs, temporal_spine=True,
        )
        assert stats["temporal"] == 0

    async def test_bulk_spine_chains_whole_batch_in_time_order(self):
        """回填用的 bulk 版：整批按 Topic 分组、按事件时间逐对相连。"""
        from datetime import datetime
        gs = _FakeGraphStore()
        nodes = []
        # 故意乱序传入，验证是按 memory_at 排序而不是按入参顺序
        for nid, month in (("b", 5), ("c", 9), ("a", 1)):
            n = _node(nid, tags=["work"])
            n.memory_at = datetime(2026, month, 1)
            nodes.append(n)

        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=nodes,
            temporal_spine_bulk=True,
        )
        assert stats["temporal"] == 2
        assert gs.temporal == [
            ("a", "b", "topic_work"), ("b", "c", "topic_work"),
        ]

    async def test_incremental_spine_would_build_nothing_for_backfill(self):
        """回填若误用增量版，会因"排除批内节点"而一条边都建不出来。

        这正是 bulk 版存在的理由 —— 两者的前驱来源不同。
        """
        from datetime import datetime
        gs = _FakeGraphStore(topic_memories={"topic_work": []})
        nodes = []
        for nid, month in (("a", 1), ("b", 5)):
            n = _node(nid, tags=["work"])
            n.memory_at = datetime(2026, month, 1)
            nodes.append(n)

        class _VS:
            async def get_by_ids(self, ids):
                return []

        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=None, nodes=nodes,
            vector_store=_VS(), temporal_spine=True,
        )
        assert stats["temporal"] == 0 and gs.temporal == []


# ================================================================
# Topic-scoped summary
# ================================================================

class _FakeVectorStore:
    def __init__(self, l3_nodes=None):
        self._l3 = l3_nodes or []
        self.upserted = []
        self.payload_updates = {}

    async def list_by_user(self, **kw):
        return list(self._l3)

    async def get_by_ids(self, ids):
        wanted = set(ids)
        return [node for node in self._l3 if node.node_id in wanted]

    async def upsert(self, node):
        self.upserted.append(node)
        return node.node_id

    async def update_payload(self, node_id, updates):
        self.payload_updates[node_id] = updates
        return True


class _FakeEmbedService:
    async def embed_queued(self, text):
        return [0.1, 0.2, 0.3]


class _FakeLLM:
    def __init__(self, text="The user works as a nurse in Berlin on night shifts."):
        self.text = text
        self.calls = []

    async def complete(self, prompt, max_tokens=500, temperature=0.7, **kw):
        self.calls.append(prompt)

        class _R:
            content = self.text
        return _R()


def _l3(node_id, topic_id, covered):
    from datetime import datetime
    return MemoryNode(
        node_id=node_id, user_id="u1", agent_id="a1", session_id="s1",
        layer=MemoryLayer.L3_SUMMARY, content="old summary",
        gmt_created=datetime(2026, 1, 1),
        custom={
            "summary_kind": SUMMARY_KIND_TOPIC,
            "topic_id": topic_id, "covered_count": covered,
        },
    )


@pytest.mark.asyncio
class TestTopicSummary:
    async def _run(self, *, mems, l3=None, min_memories=5, step=5, llm=None):
        gs = _FakeGraphStore(
            topic_memories={"t_work": mems},
            topics=[{"topic_id": "t_work", "name": "work"}],
        )
        vs = _FakeVectorStore(l3_nodes=l3 or [])
        llm = llm or _FakeLLM()
        stats = await maybe_summarize_topics(
            graph_store=gs, vector_store=vs, embed_service=_FakeEmbedService(),
            llm_provider=llm, user_id="u1", agent_id="a1", session_id="s1",
            isolation_key="u1::a1", touched_topic_ids=["t_work"],
            min_memories=min_memories, step=step,
        )
        return stats, vs, llm

    @staticmethod
    def _mems(n):
        return [{"node_id": f"m{i}", "content": f"fact {i}"} for i in range(n)]

    async def test_summarizes_when_threshold_reached(self):
        stats, vs, llm = await self._run(mems=self._mems(5))
        assert stats["summarized"] == 1
        node = vs.upserted[0]
        assert node.layer == MemoryLayer.L3_SUMMARY
        assert node.custom["summary_kind"] == SUMMARY_KIND_TOPIC
        assert node.custom["topic_id"] == "t_work"
        assert node.custom["covered_count"] == 5
        assert len(node.custom["source_memory_ids"]) == 5
        assert len(llm.calls) == 1

    async def test_skips_below_min_memories(self):
        stats, vs, _ = await self._run(mems=self._mems(3))
        assert stats["summarized"] == 0 and stats["skipped"] == 1
        assert vs.upserted == []

    async def test_skips_when_increment_below_step(self):
        """已总结过 5 条，现在 7 条 → 增量 2 < step 5，不重算（省 LLM）。"""
        stats, vs, llm = await self._run(
            mems=self._mems(7), l3=[_l3("s1", "t_work", 5)],
        )
        assert stats["summarized"] == 0 and stats["skipped"] == 1
        assert llm.calls == []

    async def test_resummarizes_and_shadows_previous(self):
        prev = _l3("s1", "t_work", 5)
        stats, vs, _ = await self._run(mems=self._mems(10), l3=[prev])
        assert stats["summarized"] == 1
        # 旧摘要置 SHADOW，避免同一 Topic 多条摘要重复召回
        assert vs.payload_updates["s1"]["status"] == MemoryStatus.SHADOW.value
        assert vs.upserted[0].custom["supersedes_summary_id"] == "s1"

    async def test_other_topics_summary_not_confused(self):
        """别的 Topic 的摘要不能被当成本 Topic 的上一版。"""
        stats, vs, llm = await self._run(
            mems=self._mems(6), l3=[_l3("s_other", "t_food", 100)],
        )
        assert stats["summarized"] == 1
        assert vs.upserted[0].custom["covered_count"] == 6

    async def test_strips_code_fence_from_llm_output(self):
        stats, vs, _ = await self._run(
            mems=self._mems(5), llm=_FakeLLM('```\nThe user is a nurse.\n```'),
        )
        assert vs.upserted[0].content == "The user is a nurse."

    async def test_empty_llm_output_counts_as_error(self):
        stats, vs, _ = await self._run(mems=self._mems(5), llm=_FakeLLM("  "))
        assert stats["summarized"] == 0 and stats["errors"] == 1
        assert vs.upserted == []

    async def test_no_llm_provider_is_noop(self):
        gs = _FakeGraphStore(topic_memories={"t": self._mems(10)})
        stats = await maybe_summarize_topics(
            graph_store=gs, vector_store=_FakeVectorStore(),
            embed_service=_FakeEmbedService(), llm_provider=None,
            user_id="u1", agent_id="a1", session_id="s1",
            isolation_key="u1::a1", touched_topic_ids=["t"],
        )
        assert stats["summarized"] == 0

    async def test_covered_count_handles_json_custom(self):
        node = _l3("s1", "t", 7)
        node.custom = '{"summary_kind": "topic", "topic_id": "t", "covered_count": 7}'
        assert covered_count_of(node) == 7
        assert covered_count_of(_node("x")) == 0


# ================================================================
# 架构不变量：light search / heavy write
# ================================================================

class TestReadPathHasNoLLM:
    """**检索链路不得有 LLM 调用** —— 架构约定是 light search / heavy write。

    推理放在写入侧（reconcile 标 typed 边、Topic 摘要），读侧只做确定性的图遍历
    和范围过滤。曾经在 reader 里加过 LLM 驱动的"推理多跳"，已移除：
    跨话题时序问题改用「派生时间锚点 + 二次纯向量检索」（用法 D），零 LLM。

    这条不变量必须由**结构**保证而不是靠开关 —— 靠 flag 守着的话，
    一旦全局 env 被打开，所有 search（含延迟敏感的 chat 路径）都会多一次 LLM。
    """

    @pytest.mark.parametrize("mod_name", [
        "reader", "reader_base", "reader_legacy", "reader_hybrid",
    ])
    def test_readers_do_not_import_or_call_llm(self, mod_name):
        import importlib
        import inspect

        mod = importlib.import_module(f"hy_memory.pipelines.{mod_name}")
        src = inspect.getsource(mod)
        for banned in ("LLMProvider", "llm_provider", "complete_messages"):
            assert banned not in src, (
                f"{mod_name} 出现 {banned!r} —— 检索链路不得引入 LLM"
            )

    def test_graph_read_helpers_are_llm_free(self):
        import inspect
        import hy_memory.pipelines._graph.rerank as rr

        for mod in (rr,):
            src = inspect.getsource(mod)
            for banned in ("LLMProvider", "llm_provider", ".complete("):
                assert banned not in src, f"{mod.__name__} 不得调用 LLM"

    def test_multihop_module_is_gone(self):
        """LLM 驱动的推理多跳已从 SDK 移除，不留死代码。"""
        with pytest.raises(ModuleNotFoundError):
            import hy_memory.pipelines._graph.multihop  # noqa: F401


# ================================================================
# 扩展候选的筛选漏斗
# ================================================================
#
# 扩展会带进很多新候选，筛选靠一个漏斗而不是一道关。顺序决定成本：
# 算候选与 query 的相似度是唯一有 I/O 的一步，必须先用免费的图信号砍到几十条。


class TestNormalizeByDegree:
    """度数归一化 —— 时间边能安全参与扩展的前提。"""

    def test_high_degree_neighbor_edges_are_devalued(self):
        # hub 有 4 个邻居，lonely 只有 1 个
        adj = build_adjacency([
            _edge("s", "hub", "co_occurs"), _edge("hub", "x1", "co_occurs"),
            _edge("hub", "x2", "co_occurs"), _edge("hub", "x3", "co_occurs"),
            _edge("s2", "lonely", "co_occurs"),
        ])
        norm = normalize_by_degree(adj)
        w_hub = next(w for nb, _t, w in norm["s"] if nb == "hub")
        w_lonely = next(w for nb, _t, w in norm["s2"] if nb == "lonely")
        assert w_hub < w_lonely, "高连接节点的每条边都该贬值"

    def test_empty(self):
        assert normalize_by_degree({}) == {}


class TestApplyTemporalAffinity:
    """时间维度：与锚点写入时间越近，联系越可能真实。"""

    def test_closer_in_time_keeps_more_support(self):
        day = 86400.0
        reach = {"near": (1.0, "seed", "co_occurs", 1),
                 "far": (1.0, "seed", "co_occurs", 1)}
        times = {"seed": 0.0, "near": day, "far": 90 * day}
        out = apply_temporal_affinity(reach, times=times, tau_days=7.0, floor=0.3)
        assert out["near"][0] > out["far"][0]

    def test_same_write_point_keeps_full_support(self):
        """同批次写入（Δt≈0）→ 因子 = 1，这正是"公园/骑车/吃饭"那个场景。"""
        reach = {"park": (0.8, "meal", "co_occurs", 1)}
        out = apply_temporal_affinity(
            reach, times={"meal": 1000.0, "park": 1000.0}, tau_days=7.0,
        )
        assert out["park"][0] == pytest.approx(0.8)

    def test_floor_prevents_time_from_erasing_strong_relations(self):
        """时间远但关系强（如 LLM 标的 causes）的边不该被时间抹平。"""
        reach = {"c": (1.0, "s", "causes", 1)}
        out = apply_temporal_affinity(
            reach, times={"s": 0.0, "c": 3650 * 86400.0}, tau_days=7.0, floor=0.3,
        )
        assert out["c"][0] == pytest.approx(0.3)

    def test_missing_times_are_not_penalized(self):
        reach = {"c": (0.7, "s", "causes", 1)}
        out = apply_temporal_affinity(reach, times={"s": 0.0}, tau_days=7.0)
        assert out["c"][0] == pytest.approx(0.7)


class TestApplyTypeQuota:
    """类型配额 —— 防止数量最多、信息量最低的时间边挤掉关系边。"""

    def test_relational_survives_flood_of_temporal(self):
        reach = {f"t{i}": (0.9, "s", "temporal_next", 1) for i in range(100)}
        reach["rel"] = (0.1, "s", "causes", 1)  # 分数最低，但类型信息量最高
        out = apply_type_quota(reach, top_n=10)
        assert "rel" in out, "关系边不该被时间边淹没"
        assert len(out) <= 12  # 配额取整可能略超，但量级受控

    def test_edge_group_mapping(self):
        assert edge_group("causes") == "relational"
        assert edge_group("co_occurs") == "relational"
        assert edge_group("temporal_next") == "temporal"
        assert edge_group("semantic_neighbor") == "semantic"

    def test_empty_and_zero_budget(self):
        assert apply_type_quota({}, top_n=10) == {}
        assert apply_type_quota({"a": (1.0, "s", "causes", 1)}, top_n=0) == {}


class TestMultiSeedCorroboration:
    """多 seed 佐证：两个不同 seed 同时指向同一候选，才是真正的佐证。"""

    def test_two_seeds_beat_one(self):
        """query 同时命中「吃饭」「骑车」，两者都指向「公园」→ 公园显著上浮。"""
        adj = build_adjacency([
            _edge("meal", "park", "co_occurs"),
            _edge("bike", "park", "co_occurs"),
            _edge("meal", "solo", "co_occurs"),
        ])
        got = reachable_within(
            {"meal": 0.8, "bike": 0.8}, adj, hops=1, seed_floor=0.6,
            multi_seed_bonus=0.5,
        )
        assert got["park"][0] > got["solo"][0], "被两个 seed 指向的候选该更高"

    def test_bonus_zero_falls_back_to_max_path(self):
        adj = build_adjacency([
            _edge("s1", "c", "co_occurs"), _edge("s2", "c", "co_occurs"),
        ])
        got = reachable_within(
            {"s1": 0.8, "s2": 0.8}, adj, hops=1, seed_floor=0.6,
            multi_seed_bonus=0.0,
        )
        one = reachable_within({"s1": 0.8}, adj, hops=1, seed_floor=0.6)
        assert got["c"][0] == pytest.approx(one["c"][0])


class TestExpandScoring:
    """打分：硬闸后多通道 / 或退回 sim + 有界结构加权。"""

    def test_structural_boost_without_channels(self):
        adj = build_adjacency([_edge("s", "c", "causes")])
        out = relax_admission(
            seed_scores={"s": 0.9}, adjacency=adj,
            candidate_sims={"c": 0.75}, min_score=0.4, gamma=0.3,
            boost_beta=0.1, boost_cap=1.0, seed_sim_delta=0.2,
        )
        assert len(out) == 1
        o = out[0]
        assert o["sim"] == 0.75
        assert o["score"] > o["sim"]
        assert o["score"] <= o["sim"] + 0.1

    def test_beta_zero_keeps_pure_similarity_without_channels(self):
        adj = build_adjacency([_edge("s", "c", "causes")])
        out = relax_admission(
            seed_scores={"s": 0.9}, adjacency=adj,
            candidate_sims={"c": 0.75}, min_score=0.4, gamma=0.3,
            boost_beta=0.0, seed_sim_delta=0.2,
        )
        assert out[0]["score"] == pytest.approx(0.75)

    def test_graph_still_cannot_invent_relevance(self):
        """无论结构支持多强，远低于 seed_sim−δ 就进不来。"""
        adj = build_adjacency([_edge("s", "junk", "causes")])
        out = relax_admission(
            seed_scores={"s": 1.0}, adjacency=adj,
            candidate_sims={"junk": 0.05}, min_score=0.4, gamma=0.3,
            boost_beta=0.5, seed_sim_delta=0.2,
        )
        assert out == []



class TestReachableWithin:
    """关系型结构多跳：k 跳可达 + 衰减 + 预算。"""

    def test_one_hop(self):
        adj = build_adjacency([_edge("s", "a", "causes")])
        got = reachable_within({"s": 0.9}, adj, hops=1, seed_floor=0.6)
        assert set(got) == {"a"} and got["a"][3] == 1

    def test_two_hops_reaches_through_middle_node(self):
        """"朋友推荐的餐厅"这类问题两端常隔一个中间节点 —— 1 跳到不了。"""
        adj = build_adjacency([
            _edge("s", "mid", "co_occurs"), _edge("mid", "far", "co_occurs"),
        ])
        one = reachable_within({"s": 0.9}, adj, hops=1, seed_floor=0.6)
        two = reachable_within({"s": 0.9}, adj, hops=2, seed_floor=0.6)
        assert "far" not in one
        assert "far" in two and two["far"][3] == 2

    def test_support_decays_with_hops(self):
        adj = build_adjacency([
            _edge("s", "mid", "co_occurs"), _edge("mid", "far", "co_occurs"),
        ])
        got = reachable_within({"s": 0.9}, adj, hops=2, seed_floor=0.6, hop_decay=0.5)
        assert got["far"][0] < got["mid"][0], "越远支持度必须越低"

    def test_pool_members_excluded(self):
        adj = build_adjacency([_edge("s", "inpool", "causes")])
        got = reachable_within({"s": 0.9, "inpool": 0.5}, adj, hops=2, seed_floor=0.6)
        assert "inpool" not in got

    def test_weak_seeds_do_not_expand(self):
        adj = build_adjacency([_edge("s", "a", "causes")])
        assert reachable_within({"s": 0.3}, adj, hops=2, seed_floor=0.6) == {}

    def test_first_edge_relation_is_reported(self):
        adj = build_adjacency([
            _edge("s", "mid", "causes"), _edge("mid", "far", "co_occurs"),
        ])
        got = reachable_within({"s": 0.9}, adj, hops=2, seed_floor=0.6)
        assert got["far"][2] == "causes", "应报首跳关系，便于解释路径来源"


class TestRelaxAdmissionMultiHop:
    def test_two_hop_candidate_can_be_admitted(self):
        adj = build_adjacency([
            _edge("seed", "mid", "causes"), _edge("mid", "far", "causes"),
        ])
        out = relax_admission(
            seed_scores={"seed": 0.9}, adjacency=adj,
            candidate_sims={"mid": 0.75, "far": 0.75},
            min_score=0.4, gamma=0.3, seed_floor=0.6, hops=2,
            seed_sim_delta=0.2,
        )
        got = {o["node_id"]: o["hop"] for o in out}
        assert got.get("mid") == 1
        assert "far" in got and got["far"] == 2

    def test_hops_one_keeps_old_behavior(self):
        adj = build_adjacency([
            _edge("seed", "mid", "causes"), _edge("mid", "far", "causes"),
        ])
        out = relax_admission(
            seed_scores={"seed": 0.9}, adjacency=adj,
            candidate_sims={"mid": 0.75, "far": 0.75},
            min_score=0.4, gamma=0.3, seed_floor=0.6, hops=1,
            seed_sim_delta=0.2,
        )
        got = {o["node_id"] for o in out}
        assert "mid" in got and "far" not in got
        assert [o["node_id"] for o in out] == ["mid"]



# ================================================================
# Cypher 静态守卫（Neo4j 路 CI 里跑不到，只能静态兜）
# ================================================================

class TestNeo4jCypherGuards:
    @pytest.mark.asyncio
    async def test_native_clone_snapshot_import_batches_and_remaps_scope(self):
        from datetime import datetime
        from hy_memory.data.graph_store_neo4j import Neo4jGraphStore

        gs = Neo4jGraphStore.__new__(Neo4jGraphStore)
        source = _node("old", "source", tags=["work"])
        source.user_id = "src"
        source.session_id = "session"
        source.memory_at = datetime(2026, 1, 1)
        source._graph_embedding = [1.0, 0.0]

        gs._record_to_memory_node = lambda record: source
        memory_batches = []
        edge_batches = []
        temporal_batches = []
        entity_batches = []
        writes = []

        async def memory_batch(nodes):
            memory_batches.append(list(nodes))
            return [node.node_id for node in nodes]

        async def edge_batch(edges):
            edge_batches.append(list(edges))
            return [True] * len(edges)

        async def temporal_batch(edges):
            temporal_batches.append(list(edges))
            return [True] * len(edges)

        async def entity_batch(assignments):
            entity_batches.append(list(assignments))
            return []

        async def capture(query, params=None):
            writes.append((query, params or {}))

        gs.upsert_memory_nodes_batch = memory_batch
        gs.add_edges_batch = edge_batch
        gs.add_temporal_edges_batch = temporal_batch
        gs.replace_entity_mentions_batch = entity_batch
        gs._run_write = capture
        gs.add_topic_path = AsyncMock(return_value=[])

        snapshot = {
            "user_id": "src",
            "nodes": [{"m": {"node_id": "old"}, "embedding": [1.0, 0.0], "beh_embedding": None}],
            "evidence": [{"source_id": "old", "target_id": "v1", "layer": "l1_raw"}],
            "related": [
                {"source_id": "old", "target_id": "old", "relation_type": "causes", "weight": 0.7},
            ],
            "temporal": [{"source_id": "old", "target_id": "old", "topic_id": "old-topic"}],
            "cross": [{"source_id": "old", "target_id": "old"}],
            "tags": [{
                "source_id": "old", "topic_id": "old-topic", "name": "work",
                "embedding": [0.5, 0.5], "isolation_key": "src::a",
            }],
            "entities": [{
                "source_id": "old", "name": "Paris", "label": "GPE",
                "isolation_key": "src::a",
            }],
        }
        id_map = {"old": "new"}

        count = await gs.import_clone_snapshot(
            snapshot, dst_user_id="dst", id_map=id_map, embed_service=None,
        )

        assert count == 1
        assert memory_batches[0][0].node_id == "new"
        assert memory_batches[0][0].user_id == "dst"
        assert memory_batches[0][0]._graph_embedding == [1.0, 0.0]
        assert edge_batches and edge_batches[0][0][0:2] == ("new", "new")
        expected_topic = Neo4jGraphStore._clone_scope("src::a", "src", "dst")
        assert expected_topic == "dst::a"
        tag_write = next(params for query, params in writes if "TAGGED_WITH" in query)
        new_topic_id = tag_write["rows"][0]["tid"]
        assert tag_write["rows"][0]["ik"] == "dst::a"
        assert temporal_batches == [[("new", "new", new_topic_id)]]
        assert entity_batches[0][0][0] == "new"
        assert entity_batches[0][0][2] == "dst::a"

    @pytest.mark.asyncio
    async def test_native_batch_primitives_each_use_one_round_trip(self):
        from datetime import datetime
        from hy_memory.data.graph_store_neo4j import Neo4jGraphStore

        gs = Neo4jGraphStore.__new__(Neo4jGraphStore)
        writes = []

        async def capture(query, params=None):
            writes.append((query, params or {}))

        gs._run_write = capture
        node = _node("batch-node", "latest", tags=["work"])
        node.memory_at = datetime(2026, 1, 1)
        assert await gs.upsert_memory_nodes_batch([node]) == ["batch-node"]
        assert len(writes) == 1
        assert "UNWIND $rows" in writes[-1][0]
        assert "MERGE (u:User" in writes[-1][0]
        assert "MERGE (u)-[:HAS_MEMORY]->(m)" in writes[-1][0]
        assert "WHEN row.emb IS NULL THEN m.embedding" in writes[-1][0]
        assert writes[-1][1]["rows"][0]["content"] == "latest"

        mentions = await gs.replace_entity_mentions_batch([
            ("batch-node", [("Paris", "gpe"), ("OpenAI", "ORG")], "u::a"),
        ])
        assert len(writes) == 2
        assert len(mentions) == 2
        assert "DELETE old" in writes[-1][0]
        assert "MERGE (e:Entity" in writes[-1][0]
        assert "MERGE (m)-[:MENTIONS]->(e)" in writes[-1][0]
        assert writes[-1][1]["rows"][0]["entities"][0]["lab"] == "GPE"

        related = await gs.add_edges_batch([
            ("batch-node", "other", "RELATED_TO", {
                "relation_type": "causes", "weight": 0.7,
            }),
        ])
        assert related == [True]
        assert len(writes) == 3
        assert writes[-1][0].count("MERGE") == 2
        assert "CASE WHEN row.w > r1.weight" in writes[-1][0]
        assert writes[-1][1]["rows"][0]["rtype"] == "causes"

        temporal = await gs.add_temporal_edges_batch([
            ("batch-node", "later", "topic_work"),
        ])
        assert temporal == [True]
        assert len(writes) == 4
        assert "MERGE (a)-[r:TEMPORAL_NEXT]->(b)" in writes[-1][0]
        assert writes[-1][1]["rows"][0]["tid"] == "topic_work"

    """起因是一个真实 bug：`get_topic_memories` 写成

        RETURN DISTINCT m.node_id AS node_id, m.content AS content
        ORDER BY m.created_at

    Neo4j 在 `DISTINCT` 之后只认投影里的变量，`m.created_at` 未投影 → SyntaxError。
    而该方法的异常是 `logger.debug` 吞掉 + `return []`，**表面无声**：
    `MEMORY_TOPIC_SUMMARY_ENABLED=true` 时永远拿不到成员记忆，摘要一条都不生成。

    CI 里没有 Neo4j 实例（端到端测试跑的是 Kuzu），所以只能静态兜住这一类问题。
    """

    def test_order_by_after_distinct_uses_projected_alias(self):
        import inspect
        import re
        import hy_memory.data.graph_store_neo4j as m

        src = inspect.getsource(m)
        offenders = []
        for match in re.finditer(r"RETURN\s+DISTINCT\b", src):
            tail = src[match.end(): match.end() + 800]
            ob = re.search(r"\bORDER\s+BY\s+([^\n]+)", tail)
            if not ob:
                continue
            expr = ob.group(1).strip().rstrip(",")
            # DISTINCT 之后只能按别名排序；出现 `var.prop` 就是本 bug
            if re.search(r"\b\w+\.\w+", expr):
                offenders.append(expr)
        assert not offenders, (
            "RETURN DISTINCT 之后的 ORDER BY 必须用投影别名，不能用 var.property: "
            f"{offenders}"
        )

    def test_topic_memories_projects_its_sort_key(self):
        import inspect
        import hy_memory.data.graph_store_neo4j as m

        src = inspect.getsource(m.Neo4jGraphStore.get_topic_memories)
        assert "m.created_at AS created_at" in src, "排序键必须投影出来"
        assert "ORDER BY created_at" in src, "ORDER BY 必须用别名"

    def test_both_backends_return_same_topic_memory_shape(self):
        """两个后端 get_topic_memories 的返回形状要一致（只 node_id / content）。"""
        import inspect
        import hy_memory.data.graph_store_kuzu as k
        import hy_memory.data.graph_store_neo4j as n

        for mod, cls in ((k, "KuzuGraphStore"), (n, "Neo4jGraphStore")):
            src = inspect.getsource(getattr(mod, cls).get_topic_memories)
            assert '"node_id"' in src and '"content"' in src, cls
            # created_at 只用于排序，不该进返回体
            assert '"created_at":' not in src, f"{cls} 不该把 created_at 放进返回体"


# ================================================================
# 端到端：Kuzu + Neo4j 两个后端都跑
# ================================================================
#
# Neo4j 路此前零覆盖，直接导致 dev6 那个 bug 漏出去：
# `get_topic_memories` 的 `RETURN DISTINCT ... ORDER BY m.created_at` 在 Neo4j 上是
# SyntaxError，而异常被 logger.debug 吞掉 + return []，表面无声。
# Kuzu 版语法合法，所以单跑 Kuzu 永远测不出来 —— 两个后端必须都跑。
#
# Neo4j 连接信息从 env 取，取不到就 skip（CI 无实例时不阻塞）：
#   HY_TEST_NEO4J_URL / HY_TEST_NEO4J_USER / HY_TEST_NEO4J_PASSWORD

_BACKENDS = ["kuzu", "neo4j"]


def _neo4j_conn():
    import os
    return (
        os.getenv("HY_TEST_NEO4J_URL", ""),
        os.getenv("HY_TEST_NEO4J_USER", "neo4j"),
        os.getenv("HY_TEST_NEO4J_PASSWORD", ""),
    )


async def _make_graph_store(backend: str, tmp_path, suffix: str):
    """按 backend 建一个干净的 GraphStore；不可用则 pytest.skip。"""
    from hy_memory.config import MemoryConfig, GraphStoreConfig

    cfg = MemoryConfig()
    if backend == "kuzu":
        from hy_memory.data.graph_store_kuzu import KuzuGraphStore

        cfg.graph_store = GraphStoreConfig(
            provider="kuzu", db_path=str(tmp_path / f"kuzu_{suffix}"),
        )
        gs = KuzuGraphStore(cfg)
        await gs.initialize()
        if not getattr(gs, "_available", False):
            pytest.skip("Kuzu unavailable in this environment")
        return gs

    url, user, pwd = _neo4j_conn()
    if not url or not pwd:
        pytest.skip(
            "Neo4j 未配置：设 HY_TEST_NEO4J_URL / HY_TEST_NEO4J_PASSWORD 后才跑"
        )
    from hy_memory.data.graph_store_neo4j import Neo4jGraphStore

    cfg.graph_store = GraphStoreConfig(
        provider="neo4j", url=url, username=user, password=pwd, database="neo4j",
    )
    gs = Neo4jGraphStore(cfg)
    try:
        await gs.initialize()
    except Exception as e:
        pytest.skip(f"Neo4j unreachable: {e}")
    # Community edition 只有一个 database，测试间必须自己清干净，否则互相污染
    await _wipe_neo4j(gs)
    return gs


async def _wipe_neo4j(gs) -> None:
    for label in ("Memory", "Topic", "Entity", "VdbRef", "User"):
        try:
            await gs._run_write(f"MATCH (n:{label}) DETACH DELETE n")
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", _BACKENDS)
@pytest.mark.parametrize("with_embed", [True, False], ids=["normalized", "fallback"])
async def test_tagged_with_edge_created_in_both_paths(backend, with_embed, tmp_path):
    """`add_topic_tag` 的两条路径都必须真的建出 Memory→Topic 边。

    回归一个真实 bug：Neo4j 的 fallback 分支（不传 embed_service，或归一化抛异常时）
    给 `_run_write` 多传了一个 params dict → TypeError 被 `except` 静默吞掉，
    **TAGGED_WITH 边从来没建出来**。后果是 tag 全变成孤立 Topic：
    `get_topic_memories` 返回空 → Topic 摘要不触发、时序脊找不到同 Topic 成员。

    单跑归一化路径测不出来（那条分支自己会建边），所以两条路径都要覆盖。
    """
    gs = await _make_graph_store(backend, tmp_path, f"tagpath_{int(with_embed)}")

    class _Embed:
        async def embed_queued(self, text):
            return [1.0, 0.0, 0.0]
        async def embed(self, text):  # 真实 EmbedService 两个都有
            return [1.0, 0.0, 0.0]

    try:
        node = _node("tp1", "some fact", tags=["work"])
        await gs.upsert_memory_node(node)
        tid = await gs.add_topic_tag(
            "tp1", "work", node.get_isolation_key(),
            embed_service=_Embed() if with_embed else None,
        )
        assert tid, "add_topic_tag 应返回 topic_id"

        mems = await gs.get_topic_memories(tid)
        assert [m["node_id"] for m in mems] == ["tp1"], (
            f"{backend}/{'normalized' if with_embed else 'fallback'} 路径没建出 "
            f"TAGGED_WITH 边 —— Topic 成了孤岛"
        )
    finally:
        await gs.close()



@pytest.mark.asyncio
@pytest.mark.parametrize("backend", _BACKENDS)
async def test_graph_end_to_end(backend, tmp_path):
    """投影 → get_related_edges → Topic 归一化，走真实图库。"""
    gs = await _make_graph_store(backend, tmp_path, "db")

    class _Embed:
        """fake 必须同时提供 embed_queued / embed —— 真实 EmbedService 两个都有。
        只实现一个会让某个后端的 tag 归一化静默退化成字符串精确匹配。"""

        _TABLE = {
            # work / job 近似同义 → 应被归一化成同一个 Topic
            "work": [1.0, 0.0, 0.0], "job": [0.99, 0.14, 0.0],
            "food": [0.0, 1.0, 0.0],
        }

        async def embed_queued(self, text):
            return self._TABLE.get(text, [0.0, 0.0, 1.0])

        async def embed(self, text):
            return self._TABLE.get(text, [0.0, 0.0, 1.0])

    try:
        n1 = _node("g1", "started running daily", tags=["fitness"])
        n2 = _node("g2", "knee started hurting", tags=["health"])
        stats = await project_memories_to_graph(
            graph_store=gs, embed_service=_Embed(), nodes=[n1, n2],
            related_by_node={"g1": [{"target_id": "g2", "relation_type": "causes"}]},
        )
        assert stats["nodes"] == 2
        assert stats["co_occurs"] == 1 and stats["typed"] == 1

        edges = await gs.get_related_edges(["g1"])
        # 无向去重：g1↔g2 之间两种关系各一条（co_occurs + causes）
        rtypes = sorted(e["relation_type"] for e in edges)
        assert rtypes == ["causes", "co_occurs"]
        assert all(e["target_status"] == "active" for e in edges)

        # 关系类型过滤
        only_causes = await gs.get_related_edges(["g1"], relation_types=["causes"])
        assert [e["relation_type"] for e in only_causes] == ["causes"]

        # shadow 后读侧必须能过滤掉
        await sync_graph_on_shadow(gs, ["g2"])
        adj = build_adjacency(await gs.get_related_edges(["g1"]))
        assert adj == {}

        # Topic 语义归一化：work / job 复用同一个 Topic，food 独立
        ik = n1.get_isolation_key()
        t_work = await gs.add_topic_tag("g1", "work", ik, embed_service=_Embed())
        t_job = await gs.add_topic_tag("g1", "job", ik, embed_service=_Embed())
        t_food = await gs.add_topic_tag("g1", "food", ik, embed_service=_Embed())
        assert t_job == t_work, "同义 tag 应复用同一 Topic，否则 tag 图会碎成同义孤岛"
        assert t_food != t_work

        topics = await gs.get_all_topics(ik)
        assert {t["name"] for t in topics} >= {"work", "food"}
        # 两个后端的返回键必须一致 —— degree 缺失会让画像聚合（§7.1）静默失效
        assert all({"topic_id", "name", "embedding", "degree"} <= set(t) for t in topics)
        assert all(t["degree"] >= 1 for t in topics if t["name"] == "work")

        # get_topic_memories：给 Topic-scoped summary 取素材
        mems = await gs.get_topic_memories(t_work)
        assert [m["node_id"] for m in mems] == ["g1"]
        # 图里没有 memory_at（Memory 表只有 created_at），事件时间以 VDB 为准
        assert "memory_at" not in mems[0]
    finally:
        await gs.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", _BACKENDS)
async def test_temporal_spine_end_to_end(backend, tmp_path):
    """时序脊：同 Topic 内按 memory_at 串有向边，两个方向都能查到。"""
    from datetime import datetime

    gs = await _make_graph_store(backend, tmp_path, "spine")

    class _Embed:
        async def embed_queued(self, text):
            return [1.0, 0.0, 0.0]

        async def embed(self, text):
            return [1.0, 0.0, 0.0]

    # 事件时间以 VDB 为准（图的 Memory 表没有 memory_at）
    written: Dict[str, Any] = {}

    class _VS:
        async def get_by_ids(self, ids):
            return [written[i] for i in ids if i in written]

    try:
        # 同一个 Topic（fitness）下三条按时间递进的记忆，分三批写入
        specs = [
            ("t1", "started jogging", datetime(2026, 1, 1)),
            ("t2", "ran a 10k", datetime(2026, 3, 1)),
            ("t3", "ran a half marathon", datetime(2026, 6, 1)),
        ]
        for nid, content, ts in specs:
            node = _node(nid, content, tags=["fitness"])
            node.memory_at = ts
            st = await project_memories_to_graph(
                graph_store=gs, embed_service=_Embed(), nodes=[node],
                vector_store=_VS(), temporal_spine=True,
            )
            written[nid] = node
            # 第一条没有前驱；后两条各接一条时序边
            assert st["temporal"] == (0 if nid == "t1" else 1), nid

        edges = await gs.get_related_edges(["t2"])
        temporal = [e for e in edges if e["relation_type"] == "temporal_next"]
        # t2 既有前驱 t1 也有后继 t3 —— 两个方向都要能查到，
        # 否则 "X 之前发生了什么" 走不通
        assert {(e["source_id"], e["target_id"]) for e in temporal} == {
            ("t1", "t2"), ("t2", "t3"),
        }
        assert all(e["directed"] for e in temporal)

        # 方向要能落到路径输出上
        fwd = collect_directed_edges(edges)
        assert ("t1", "t2") in fwd and ("t2", "t3") in fwd
        paths = find_relation_paths(
            hit_scores={"t1": 0.9, "t3": 0.85},
            adjacency=build_adjacency(edges),
            forward_dirs=fwd,
        )
        two_hop = [p for p in paths if p["hops"] == 2 and p["nodes"][0] == "t1"]
        assert two_hop, "t1 →(t2)→ t3 的时序路径应被找到"
        assert all(r.get("direction") == "forward" for r in two_hop[0]["relations"])

        # include_temporal=False 时不返回时序边
        assert not [
            e for e in await gs.get_related_edges(["t2"], include_temporal=False)
            if e["relation_type"] == "temporal_next"
        ]
    finally:
        await gs.close()
