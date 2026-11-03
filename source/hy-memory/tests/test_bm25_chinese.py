# -*- coding: utf-8 -*-
"""
中文 BM25 对称性测试 — 防止下次再有人意外打破 query/candidate 端的分词一致性。

覆盖：
1. _node_to_payload 产出的 search_text 是 jieba 切过的（带空格）
2. ReconcileHybridRetriever 内部 lemmatize candidate 路径
"""

import pytest

from hy_memory.data.vector_store_base import VectorStoreBase
from hy_memory.models.memory import MemoryNode, MemoryLayer, MemoryStatus, SourceType
from hy_memory.pipelines._retrieval import bm25 as rbm25
from hy_memory.pipelines._retrieval.lemmatize import lemmatize_for_bm25


def _make_node(content: str, tags=None) -> MemoryNode:
    return MemoryNode(
        node_id="n1",
        user_id="u1",
        agent_id="a1",
        session_id="s1",
        layer=MemoryLayer.L2_FACT,
        content=content,
        status=MemoryStatus.ACTIVE,
        confidence=1.0,
        source_type=SourceType.EXPLICIT,
        tags=tags or [],
    )


class TestNodeToPayloadSearchText:
    """_node_to_payload 产出的 payload.search_text 必须是 jieba 切过的"""

    def test_chinese_content_is_jieba_segmented(self):
        node = _make_node("用户倾向于接受务实的解决方案")
        payload = VectorStoreBase._node_to_payload(node)
        st = payload["search_text"]
        # jieba 切完会是带空格的
        assert " " in st, f"expected jieba-segmented (with spaces), got {st!r}"
        # content 字段保持原样
        assert payload["content"] == "用户倾向于接受务实的解决方案"
        # search_text 包含 jieba 切出的关键词
        tokens = st.split()
        assert "用户" in tokens
        assert "倾向" in tokens
        assert "解决方案" in tokens or ("解决" in tokens and "方案" in tokens)

    def test_english_content_lemmatized(self):
        node = _make_node("The user prefers pragmatic solutions for deployment")
        payload = VectorStoreBase._node_to_payload(node)
        st = payload["search_text"]
        # 英文 lemmatize 后应该全小写、关键词保留
        assert "user" in st
        assert "pragmatic" in st
        # content 字段保持原大小写
        assert payload["content"] == "The user prefers pragmatic solutions for deployment"

    def test_tags_concatenated_then_lemmatized(self):
        node = _make_node("用户喜欢猫", tags=["宠物", "动物"])
        payload = VectorStoreBase._node_to_payload(node)
        st = payload["search_text"]
        tokens = st.split()
        assert "宠物" in tokens
        assert "动物" in tokens
        assert "用户" in tokens

    def test_empty_content_safe(self):
        node = _make_node("")
        payload = VectorStoreBase._node_to_payload(node)
        assert payload["search_text"] == ""

    def test_idempotent_already_segmented(self):
        """已经切过的输入再切，结果稳定（len、token 集合一致）"""
        once = lemmatize_for_bm25("用户倾向于接受务实的解决方案")
        twice = lemmatize_for_bm25(once)
        assert sorted(once.split()) == sorted(twice.split())


class TestReconcileBM25Symmetric:
    """直接用 compute_bm25_scores 验对称性 — 候选端必须 lemmatize"""

    def test_unfixed_pattern_is_zero(self):
        """复现原 bug：jieba query + 原始中文 candidate → 全零"""
        query_terms = rbm25.tokenize(lemmatize_for_bm25("用户倾向于接受"))
        # candidate 不 lemmatize（旧行为）
        contents_raw = ["用户倾向于接受务实的解决方案"]
        raw = rbm25.compute_bm25_scores(query_terms, contents_raw)
        assert raw == [0.0], f"expected old buggy zero, got {raw}"

    def test_fixed_pattern_is_nonzero(self):
        """新链路：双端都 lemmatize → 命中"""
        query = "用户倾向于接受"
        cand = "用户倾向于接受务实的解决方案"
        q_terms = rbm25.tokenize(lemmatize_for_bm25(query))
        contents = [lemmatize_for_bm25(cand)]
        raw = rbm25.compute_bm25_scores(q_terms, contents)
        assert raw[0] > 0.0, f"expected non-zero after fix, got {raw}"
