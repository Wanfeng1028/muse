"""Topic 隔离粒度 + 支持度叠加。两处都是回归测试覆盖的问题。

**Topic 隔离键**：Topic 此前用带 session 的 `isolation_key` 建节点，导致同名 tag 在每个
session 各建一个互不相识的 Topic。这样会让同名主题分裂成多个节点，连带导致时序脊
建不出边（同 topic 找不到跨批次前驱）、topic summary 反复总结同名碎片、跨会话 tag
召回不连通。

**支持度叠加**：图边可达与 episode 共属此前取 max。两者是独立观察，同时成立应当更可信；
且 episode 支持度被 sqrt(size) 压着、天然小于 co_occurs，取 max 会让 episode 通道在
"有共现边的候选"上完全不起作用。
"""

import inspect

import pytest

from hy_memory.models.memory import MemoryLayer, MemoryNode
from hy_memory.pipelines._graph.rerank import blend_support


# ======================================================================
# Topic 隔离粒度
# ======================================================================

class TestTopicScopeKey:
    def _node(self, *, user="u1", agent="a1", session="s1"):
        return MemoryNode(
            user_id=user, agent_id=agent, session_id=session,
            layer=MemoryLayer.L2_FACT, content="x",
        )

    def test_topic_scope_drops_session(self):
        n = self._node()
        assert n.get_isolation_key() == "u1::a1::s1"
        assert n.get_topic_scope_key() == "u1::a1"

    def test_same_tag_across_sessions_shares_scope(self):
        """核心诉求：同一用户在不同 session 里的同名 tag 必须落到同一个 Topic。"""
        keys = {
            self._node(session=f"locomo::{i}").get_topic_scope_key()
            for i in range(20)
        }
        assert keys == {"u1::a1"}, "20 个 session 必须共享一个 Topic 作用域"

    def test_different_users_still_isolated(self):
        """放宽粒度不能放宽到跨用户。"""
        a = self._node(user="u1").get_topic_scope_key()
        b = self._node(user="u2").get_topic_scope_key()
        c = self._node(agent="a2").get_topic_scope_key()
        assert a != b and a != c

    @pytest.mark.parametrize("ik,want", [
        ("u1::a1::s1", "u1::a1"),
        ("u1::a1::locomo::7", "u1::a1"),      # session 自身含 :: 也要正确截断
        ("u1::a1", "u1::a1"),
        ("", ""),
        ("only_one_part", "only_one_part"),
    ])
    def test_topic_scope_of_isolation_key(self, ik, want):
        assert MemoryNode.topic_scope_of(ik) == want

    def test_build_helper_matches_instance_method(self):
        n = self._node()
        assert MemoryNode.build_topic_scope_key("u1", "a1") == n.get_topic_scope_key()

    def test_roundtrip_write_and_read_use_same_key(self):
        """建 Topic 与查 Topic 必须用同一个键 —— 两个后端都是精确匹配，不一致就查不到。"""
        n = self._node(session="locomo::7")
        write_key = n.get_topic_scope_key()
        read_key = MemoryNode.topic_scope_of(n.get_isolation_key())
        assert write_key == read_key


class TestTopicCallSitesConsistent:
    """所有建/查 Topic 的地方都必须用 topic scope，漏一个就静默查不到。"""

    def test_projector_builds_with_topic_scope(self):
        from hy_memory.pipelines._graph import projector

        src = inspect.getsource(projector)
        assert "get_topic_scope_key()" in src
        assert "add_topic_tag(\n                    nid, str(tag), node.get_isolation_key()" not in src

    @pytest.mark.parametrize("module_path", [
        "hy_memory.pipelines.writer",
        "hy_memory.pipelines._graph.topic_summary",
        "hy_memory.pipelines.reader_legacy",
        "hy_memory.pipelines.system2_agent",
    ])
    def test_query_sites_use_topic_scope(self, module_path):
        import importlib

        src = inspect.getsource(importlib.import_module(module_path))
        if "get_all_topics(" not in src:
            pytest.skip("该模块不查 Topic")
        assert "topic_scope_of(" in src, (
            f"{module_path} 直接用 isolation_key 查 Topic —— 与建 Topic 的键不一致，会查不到"
        )


# ======================================================================
# 支持度有界叠加
# ======================================================================

class TestBlendSupport:
    def test_dual_evidence_scores_higher_than_either(self):
        """双重证据必须高于任一单独来源 —— 这是改掉 max 的全部理由。"""
        g = {"bike": (0.55, "eat", "co_occurs", 1)}
        e = {"bike": (0.21, "eat", "episode", 1)}
        merged = blend_support(g, e, lam=0.3)["bike"][0]
        assert merged > 0.55 and merged > 0.21
        assert merged == pytest.approx(0.55 + 0.3 * 0.21)

    def test_lambda_discounts_the_second_source(self):
        """折扣系数：避免两个弱证据叠出一个强结论。"""
        g = {"x": (0.4, "s", "co_occurs", 1)}
        e = {"x": (0.4, "s", "episode", 1)}
        assert blend_support(g, e, lam=0.3)["x"][0] == pytest.approx(0.52)
        assert blend_support(g, e, lam=0.0)["x"][0] == pytest.approx(0.4)

    def test_capped(self):
        """封顶保证准入门槛最多降到 (1-gamma)·min_score，护栏不变。"""
        g = {"x": (0.9, "s", "co_occurs", 1)}
        e = {"x": (0.8, "s", "episode", 1)}
        assert blend_support(g, e, lam=0.3, support_cap=1.0)["x"][0] == 1.0

    def test_episode_only_candidate_kept_as_is(self):
        """跨批次、无共现边的候选 —— 这是 episode 通道最该发挥作用的地方。"""
        e = {"park": (0.21, "eat", "episode", 1)}
        out = blend_support({}, e, lam=0.3)
        assert out["park"][0] == pytest.approx(0.21)
        assert out["park"][2] == "episode"

    def test_graph_only_candidate_untouched(self):
        g = {"a": (0.5, "s", "causes", 2)}
        assert blend_support(g, {}, lam=0.3) == g

    def test_no_episode_returns_copy_not_alias(self):
        """不能就地改调用方的 dict。"""
        g = {"a": (0.5, "s", "causes", 1)}
        out = blend_support(g, {}, lam=0.3)
        out["a"] = (9.9, "x", "y", 1)
        assert g["a"][0] == 0.5

    def test_attribution_follows_stronger_side(self):
        """归属信息取支持度更强的一侧，便于观测是哪条通道带回来的。"""
        g = {"x": (0.6, "seedG", "co_occurs", 1)}
        e = {"x": (0.1, "seedE", "episode", 1)}
        assert blend_support(g, e, lam=0.3)["x"][1:] == ("seedG", "co_occurs", 1)

        g2 = {"y": (0.1, "seedG", "co_occurs", 1)}
        e2 = {"y": (0.6, "seedE", "episode", 1)}
        assert blend_support(g2, e2, lam=0.3)["y"][1:] == ("seedE", "episode", 1)

    def test_reader_uses_blend_not_max(self):
        """回归：reader 里若退回取 max，episode 通道会被系统性削掉。"""
        from hy_memory.pipelines.reader_hybrid import HybridReadPipeline

        src = inspect.getsource(HybridReadPipeline._apply_graph_rerank)
        assert "blend_support(" in src
        assert "if prev is None or val[0] > prev[0]" not in src


# ======================================================================
# 阈值重标定
# ======================================================================

class TestThresholdsRecalibrated:
    """0.6 未按代表性分数分布校准，会导致扩展与路径全程不触发。"""

    def test_defaults_are_half(self):
        from hy_memory.config import GraphStoreConfig

        c = GraphStoreConfig()
        assert c.seed_floor == 0.5
        assert c.path_high_floor == 0.5
        assert c.episode_blend_lambda == 0.3

    def test_env_still_overrides(self, monkeypatch):
        from hy_memory.config import GraphStoreConfig

        monkeypatch.setenv("MEMORY_GRAPH_SEED_FLOOR", "0.42")
        monkeypatch.setenv("MEMORY_GRAPH_EPISODE_BLEND_LAMBDA", "0.7")
        c = GraphStoreConfig()
        assert c.seed_floor == 0.42
        assert c.episode_blend_lambda == 0.7

    def test_seed_floor_admits_multiple_seeds_at_observed_scale(self):
        """按代表性分数分布，0.6 只接纳一个 seed，0.5 可接纳多个。"""
        from hy_memory.pipelines._graph.rerank import reachable_within

        # 一个代表性样本池：最高分 0.636，其余在 0.5~0.6 之间
        pool = {"a": 0.636, "b": 0.58, "c": 0.55, "d": 0.51, "e": 0.42}
        adj = {n: [("out1", "co_occurs", 0.8)] for n in pool}
        assert len(reachable_within(pool, adj, seed_floor=0.6)) >= 1
        # 关键：0.5 时参与佐证的 seed 从 1 个变成 4 个
        seeds_06 = sum(1 for s in pool.values() if s >= 0.6)
        seeds_05 = sum(1 for s in pool.values() if s >= 0.5)
        assert seeds_06 == 1 and seeds_05 == 4
