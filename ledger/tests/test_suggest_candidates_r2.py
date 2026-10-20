from __future__ import annotations

from ledger.matching import suggest_candidates


def test_history_cap_three_and_confidence_order():
    history = [
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
        {"category_id": 20, "direction": "out"},
        {"category_id": 20, "direction": "out"},
        {"category_id": 20, "direction": "out"},
        {"category_id": 30, "direction": "out"},
        {"category_id": 30, "direction": "out"},
        {"category_id": 40, "direction": "out"},
    ]
    result = suggest_candidates("", "", "out", history, [])
    assert result == [
        (10, "该商户历史多归为此分类", 55),
        (20, "该商户历史多归为此分类", 45),
        (30, "该商户历史多归为此分类", 35),
    ]
    assert len(result) == 3
    assert [c for _cid, _reason, c in result] == [55, 45, 35]


def test_history_plus_top_categories_dedup_and_fill():
    history = [
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
    ]
    top_categories = [(10, 9), (20, 8), (30, 7), (40, 6)]
    result = suggest_candidates("", "", "out", history, top_categories)
    assert result == [
        (10, "该商户历史多归为此分类", 55),
        (20, "同方向常用分类", 45),
        (30, "同方向常用分类", 35),
    ]
    assert len(result) == 3


def test_empty_history_and_empty_top_categories():
    assert suggest_candidates("", "", "out", [], []) == []
    assert suggest_candidates("kfc", "lunch", "in", [], []) == []


def test_reason_texts_per_source():
    history = [{"category_id": 7, "direction": "in"}]
    top_categories = [(8, 5), (9, 4)]
    result = suggest_candidates("", "", "in", history, top_categories)
    assert result == [
        (7, "该商户历史多归为此分类", 55),
        (8, "同方向常用分类", 45),
        (9, "同方向常用分类", 35),
    ]
    assert result[0][1] == "该商户历史多归为此分类"
    assert result[1][1] == "同方向常用分类"
    assert result[2][1] == "同方向常用分类"


def test_history_direction_filter():
    history = [
        {"category_id": 10, "direction": "out"},
        {"category_id": 10, "direction": "out"},
        {"category_id": 20, "direction": "in"},
        {"category_id": 30, "direction": "in"},
        {"category_id": 30, "direction": "in"},
        {"category_id": 30, "direction": "in"},
    ]
    result = suggest_candidates("", "", "in", history, [])
    assert result == [
        (30, "该商户历史多归为此分类", 55),
        (20, "该商户历史多归为此分类", 45),
    ]
    assert len(result) == 2
    assert all(cid != 10 for cid, _reason, _c in result)

    out_result = suggest_candidates("", "", "out", history, [])
    assert out_result == [(10, "该商户历史多归为此分类", 55)]
