# -*- coding: utf-8 -*-
"""事实层 BM25 词面通道（coding/lexical.py + store.search_facts 的重排路径）。

MockEmbedService 是 md5 哈希向量，语义上没有意义——这恰好适合测这一路：稠密顺序
基本是随机的，词面命中就成了唯一有信号的排序依据，混检起没起作用一眼可辨。
"""

import pytest

from hy_memory.coding.lexical import rerank, tokenize
from hy_memory.coding.types import WorkingFact


class TestTokenize:
    def test_keeps_numbers_whole(self):
        """给定量的辨识度全在完整数值上，切碎了就白搭。"""
        assert "1e" not in tokenize("tolerance 1e-6")
        assert "64" in tokenize("step 3 input: n=64")
        assert "688.7" in tokenize("cost 688.7-721.3 per unit")

    def test_case_insensitive(self):
        assert tokenize("Get-ChildItem") == tokenize("get-childitem")

    def test_mixed_cjk_and_latin(self):
        toks = tokenize("第3天晚餐预算 77-91 USD")
        assert "77" in toks and "91" in toks and "usd" in toks
        assert any("晚餐" in t for t in toks)

    def test_empty(self):
        assert tokenize("") == []
        assert tokenize("!!! ???") == []


class TestRerank:
    def test_exact_token_beats_dense_order(self):
        """混检要解决的正是这个：n=64 和 n=32 语义几乎一样，查询要的是其中一条。"""
        # 稠密把 a 排前面（0.81 vs 0.80）——语义上两条几乎不可分，正是词面该说话的场合
        cands = [("a", 0.81, "step 3 input: n=32, tolerance 1e-6"),
                 ("b", 0.80, "step 3 input: n=64, tolerance 1e-6")]
        order = rerank("what was n=64", cands)
        assert order[0] == "b"

    def test_returns_all_ids_exactly_once(self):
        cands = [(str(i), 0.9 - i * 0.01, f"fact {i} value={i * 7}") for i in range(6)]
        order = rerank("value=21", cands)
        assert sorted(order) == sorted(c[0] for c in cands)

    def test_no_lexical_hit_keeps_dense(self):
        """词面全 0 时它的排名是任意的，融合进去等于拿噪声扰动稠密顺序。"""
        cands = [("a", 0.9, "alpha beta"), ("b", 0.8, "gamma delta")]
        assert rerank("完全无关的中文查询", cands) is None

    def test_single_candidate_is_noop(self):
        assert rerank("q", [("a", 0.9, "text")]) is None

    def test_empty_query_is_noop(self):
        assert rerank("!!!", [("a", 0.9, "alpha"), ("b", 0.8, "beta")]) is None

    def test_no_lexical_discrimination_is_noop(self):
        """词面分全等时它的顺序是任意的，不能拿它去扰动稠密。"""
        # 两条文本相同 => 词面无区分力 => 不重排，交回调用方保持纯稠密
        cands = [("a", 0.8, "same text here"), ("b", 0.9, "same text here")]
        assert rerank("same text", cands) is None

    def test_lex_cannot_override_a_large_dense_gap(self):
        """词面是补丁不是主索引：0.4 的余弦鸿沟不该被一个词面命中翻掉。

        这条是 lex_weight 的语义边界——它就等于"词面最多能翻过多大的余弦间距"。
        """
        cands = [("far", 0.90, "完全不同的话题"), ("near", 0.50, "retry budget = 5")]
        order = rerank("retry budget 5", cands, lex_weight=0.05)
        assert order[0] == "far"


@pytest.mark.asyncio
class TestSearchFactsRerank:
    async def _seed(self, store, statements):
        for fid, stmt in statements:
            await store.insert_fact(WorkingFact(
                fact_id=fid, user_id="u1", statement=stmt,
            ))

    async def test_query_text_can_change_the_top(self, coding_store):
        """候选比名额多时，词面命中的那条必须进得来。"""
        await self._seed(coding_store, [
            (f"f{i}", f"step {i} input: n={2 ** i}, tolerance 1e-6") for i in range(8)
        ])
        emb = await coding_store.embed_service.embed("step input tolerance")

        dense = await coding_store.search_facts(emb, user_id="u1", top=3)
        fused = await coding_store.search_facts(
            emb, user_id="u1", top=3, query_text="what was n=64",
        )
        assert len(fused) == len(dense) == 3
        assert "f6" in {f.fact_id for f, _ in fused}  # n=64

    async def test_scores_stay_dense_not_rrf(self, coding_store):
        """融合分是另一套量纲，返回它等于把 client.py:851 的 0.30 闸门静默清空。"""
        await self._seed(coding_store, [
            (f"f{i}", f"发布流程第 {i} 步，超时 {i * 10}s") for i in range(8)
        ])
        emb = await coding_store.embed_service.embed("发布流程第 3 步，超时 30s")
        fused = await coding_store.search_facts(
            emb, user_id="u1", top=3, query_text="超时 30s",
        )
        assert fused and all(s > 0.5 for _, s in fused), [s for _, s in fused]

    async def test_rerank_never_returns_fewer_than_dense(self, coding_store):
        """这条是整个设计的地基。

        若先重排再过闸门，BM25 可能把一条低余弦的事实顶进前 top，它随后被上层闸门
        丢掉——混检就会比纯稠密召回得更少。所以 min_score 必须先砍候选池再重排。
        """
        await self._seed(coding_store, [
            (f"f{i}", f"任务 {i}：把索引基准定为 {i}，重试预算 {i + 1}") for i in range(10)
        ])
        emb = await coding_store.embed_service.embed("任务 7：把索引基准定为 7，重试预算 8")
        for ms in (0.0, 0.3, 0.5, 0.7):
            dense = await coding_store.search_facts(emb, user_id="u1", top=4, min_score=ms)
            fused = await coding_store.search_facts(
                emb, user_id="u1", top=4, min_score=ms, query_text="重试预算 8",
            )
            assert len(fused) == len(dense), f"min_score={ms}"
            assert all(s >= ms for _, s in fused)

    async def test_no_query_text_is_pure_dense(self, coding_store):
        """不传 query_text 必须和改动前逐条一致——这一路是可选补丁，不是新默认。"""
        await self._seed(coding_store, [
            (f"f{i}", f"事实 {i}") for i in range(6)
        ])
        emb = await coding_store.embed_service.embed("事实 0")
        a = await coding_store.search_facts(emb, user_id="u1", top=3)
        b = await coding_store.search_facts(emb, user_id="u1", top=3, query_text="   ")
        assert [f.fact_id for f, _ in a] == [f.fact_id for f, _ in b]

    async def test_min_score_filters(self, coding_store):
        await self._seed(coding_store, [("f1", "打包发布到私有包索引")])
        emb = await coding_store.embed_service.embed("打包发布到私有包索引")
        assert len(await coding_store.search_facts(emb, user_id="u1", min_score=0.9)) == 1
        assert await coding_store.search_facts(emb, user_id="u1", min_score=1.01) == []

    async def test_superseded_still_excluded_under_rerank(self, coding_store):
        """重排不能成为过期结论的旁路。"""
        await self._seed(coding_store, [
            (f"f{i}", f"结论 {i}，阈值 {i * 5}") for i in range(8)
        ])
        assert await coding_store.supersede_fact("f3", "f_new") is True
        emb = await coding_store.embed_service.embed("结论 3，阈值 15")
        fused = await coding_store.search_facts(
            emb, user_id="u1", top=5, query_text="阈值 15",
        )
        assert "f3" not in {f.fact_id for f, _ in fused}


class TestKillSwitch:
    """消融要能不改代码就切换：闸门的教训是"只靠环境变量、代码默认相反"会静默回退，
    这里反过来——代码默认开启，环境变量只用于关掉和调权重。"""

    def test_env_off_disables(self, monkeypatch):
        from hy_memory.coding import lexical
        cands = [("a", 0.81, "n=32"), ("b", 0.80, "n=64")]
        assert lexical.rerank("n=64", cands)[0] == "b"
        monkeypatch.setenv(lexical.ENV_DISABLE, "1")
        assert lexical.rerank("n=64", cands) is None

    def test_env_weight_overrides(self, monkeypatch):
        from hy_memory.coding import lexical
        cands = [("far", 0.90, "完全不同的话题"), ("near", 0.50, "retry budget = 5")]
        assert lexical.rerank("retry budget 5", cands)[0] == "far"
        monkeypatch.setenv(lexical.ENV_WEIGHT, "9.0")   # 权重大到盖过余弦鸿沟
        assert lexical.rerank("retry budget 5", cands)[0] == "near"

    def test_bad_weight_falls_back(self, monkeypatch):
        from hy_memory.coding import lexical
        monkeypatch.setenv(lexical.ENV_WEIGHT, "not-a-number")
        cands = [("a", 0.81, "n=32"), ("b", 0.80, "n=64")]
        assert lexical.rerank("n=64", cands) is not None   # 不抛，退回默认权重
