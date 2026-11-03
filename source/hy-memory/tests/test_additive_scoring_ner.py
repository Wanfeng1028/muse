# -*- coding: utf-8 -*-
"""Additive VDB scoring + month lemmatize + NER tag helpers."""

import pytest

from hy_memory.pipelines._retrieval.scoring import (
    score_vdb_node,
    score_vdb_node_additive,
)
from hy_memory.pipelines._retrieval.lemmatize import lemmatize_for_bm25
from hy_memory.pipelines._retrieval.ner import (
    BOOST_ENTITY_LABELS,
    _get_nlp,
    classify_tag,
    annotate_tag_ners,
    entity_tag_pairs,
    extract_entities,
    max_entity_tag_cos,
    same_entity_group,
)

requires_spacy_model = pytest.mark.skipif(
    _get_nlp() is None,
    reason="spaCy English NER model is not installed",
)


class TestScoreVdbNodeAdditive:
    def test_no_bm25_keeps_full_sem(self):
        # 旧公式会把无 BM25 的 sem 乘 0.6；新公式应保留满权重
        assert abs(score_vdb_node_additive(0.3578) - 0.3578) < 1e-6
        assert abs(score_vdb_node(0.3578, 0.0, 0.6, 0.4) - 0.21468) < 1e-4

    def test_bm25_is_bonus_not_dilution(self):
        s = score_vdb_node_additive(0.5, bm25_score=0.4, w_bm25=0.2)
        assert abs(s - (0.5 + 0.2 * 0.4)) < 1e-6

    def test_tag_cos_bonus(self):
        s = score_vdb_node_additive(
            0.3578, bm25_score=0.0, tag_cos=0.665, w_tag=0.3,
        )
        assert abs(s - (0.3578 + 0.3 * 0.665)) < 1e-4

    def test_clamp01(self):
        s = score_vdb_node_additive(
            0.9, bm25_score=1.0, tag_cos=0.9, w_bm25=0.2, w_tag=0.3,
        )
        assert s == 1.0


class TestMonthLemmatize:
    def test_may_preserved(self):
        out = lemmatize_for_bm25("Which country was Evan visiting in May 2023?")
        tokens = set(out.split())
        assert "may" in tokens
        assert "2023" in tokens


class TestNerTag:
    def test_boost_excludes_person(self):
        assert "PERSON" not in BOOST_ENTITY_LABELS
        assert "LAW" not in BOOST_ENTITY_LABELS
        assert "LANGUAGE" not in BOOST_ENTITY_LABELS
        assert "GPE" in BOOST_ENTITY_LABELS
        assert "PRODUCT" in BOOST_ENTITY_LABELS

    def test_query_person_not_for_boost(self):
        ents = extract_entities(
            "What kind of car does Evan drive?", for_boost=True,
        )
        assert all(lab != "PERSON" for _, lab in ents)

    @requires_spacy_model
    def test_classify_jasper(self):
        lab = classify_tag("Jasper")
        assert lab in ("GPE", "LOC", "FAC")

    def test_classify_prius_not_gpe_heuristic(self):
        # spaCy 常不认 Prius；旧 TitleCase→GPE 启发式会误标，现应为空或 PRODUCT
        lab = classify_tag("Prius")
        assert lab in ("", "PRODUCT")

    def test_classify_topic_empty(self):
        assert classify_tag("travel") == ""
        assert classify_tag("health") == ""

    @requires_spacy_model
    def test_annotate_parallel(self):
        tags = ["travel", "Jasper", "family"]
        ners = annotate_tag_ners(tags)
        assert len(ners) == 3
        assert ners[0] == ""
        assert ners[1] != ""
        assert ners[2] == ""

    def test_entity_tag_pairs_skips_person(self):
        pairs = entity_tag_pairs(
            ["Evan", "Jasper", "fitness"],
            ["PERSON", "GPE", ""],
            for_boost=True,
        )
        assert pairs == [("Jasper", "GPE")]

    def test_same_group_geo(self):
        assert same_entity_group("GPE", "LOC")
        assert not same_entity_group("PERSON", "GPE")

    def test_max_entity_tag_cos_threshold(self):
        import math

        def n(v):
            s = math.sqrt(sum(x * x for x in v)) or 1
            return [x / s for x in v]

        q = [1.0, 0.0, 0.0]
        t_hi = [0.9, 0.43589, 0.0]  # cos≈0.9
        t_lo = [0.3, 0.9539, 0.0]   # cos≈0.3
        emb = {"Canada": n(q), "Jasper": n(t_hi), "Banff": n(t_lo)}
        cos, pair = max_entity_tag_cos(
            [("Canada", "GPE")],
            [("Jasper", "GPE"), ("Banff", "GPE")],
            emb,
            min_cos=0.55,
        )
        assert cos >= 0.55
        assert pair[2] == "Jasper"

    def test_max_entity_tag_cos_ignores_person(self):
        emb = {"Evan": [1.0, 0.0], "Sam": [1.0, 0.0]}
        cos, pair = max_entity_tag_cos(
            [("Evan", "PERSON")],
            [("Sam", "PERSON")],
            emb,
            min_cos=0.5,
        )
        assert cos == 0.0
        assert pair is None
