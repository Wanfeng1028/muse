from __future__ import annotations

from ledger.matching import match_best


def _empty_inputs():
    return {
        "rules": [],
        "aliases": [],
        "history": [],
        "top_categories": [],
    }


def test_all_empty_returns_none_marker():
    result = match_best("unknown merchant", "some summary", "expense", **_empty_inputs())
    assert result["category_id"] is None
    assert result["confidence"] == 0
    assert result["source"] == "none"
    assert result["rule_id"] is None
    assert result["reason"] == "无匹配"


def test_only_top_categories_yields_suggest():
    result = match_best(
        "unknown merchant",
        "some summary",
        "expense",
        rules=[],
        aliases=[],
        history=[],
        top_categories=[(7, 10)],
    )
    assert result["source"] == "suggest"
    assert result["category_id"] == 7
    assert result["confidence"] == 55
    assert result["reason"] == "同方向常用分类"
    assert result["rule_id"] is None


def test_empty_counterparty_still_none():
    result = match_best("", "", "expense", **_empty_inputs())
    assert result["source"] == "none"
    assert result["category_id"] is None
    assert result["confidence"] == 0
    assert result["reason"] == "无匹配"


def test_history_hit_marks_history():
    history = [
        {"counterparty": "星巴克", "summary": "咖啡", "direction": "expense", "category_id": 3},
        {"counterparty": "星巴克", "summary": "拿铁", "direction": "expense", "category_id": 3},
    ]
    result = match_best(
        "星巴克",
        "咖啡",
        "expense",
        rules=[],
        aliases=[],
        history=history,
        top_categories=[],
    )
    assert result["source"] == "history"
    assert result["category_id"] == 3
    assert result["reason"] == "历史记录推断"
    assert result["rule_id"] is None


def test_alias_hit_marks_alias():
    aliases = [
        {"alias": "星巴克", "category_id": 4, "direction": "out"},
    ]
    result = match_best(
        "星巴克",
        "咖啡",
        "out",
        rules=[],
        aliases=aliases,
        history=[],
        top_categories=[(9, 20)],
    )
    assert result["source"] == "alias"
    assert result["category_id"] == 4
    assert result["confidence"] == 85
    assert result["reason"] == "别名记忆命中"
    assert result["rule_id"] is None
