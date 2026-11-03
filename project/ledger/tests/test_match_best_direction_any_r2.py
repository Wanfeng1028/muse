from __future__ import annotations

from ledger.matching import match_best


def _rule(rid: int, keyword: str, category_id: int, direction: str, priority: int = 10) -> dict:
    return {
        "id": rid,
        "keyword": keyword,
        "pattern_type": "keyword",
        "category_id": category_id,
        "direction": direction,
        "priority": priority,
        "is_enabled": 1,
    }


def test_keyword_rule_direction_any_hits_both_in_and_out() -> None:
    rules = [_rule(1, "星巴克", 88, "any")]
    in_result = match_best(
        "星巴克",
        "",
        "in",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert in_result["source"] == "rule_keyword"
    assert in_result["category_id"] == 88
    assert in_result["confidence"] == 95
    assert in_result["rule_id"] == 1
    out_result = match_best(
        "星巴克",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert out_result["source"] == "rule_keyword"
    assert out_result["category_id"] == 88
    assert out_result["confidence"] == 95
    assert out_result["rule_id"] == 1


def test_keyword_rule_direction_in_misses_out_query() -> None:
    rules = [_rule(2, "工资", 91, "in")]
    result = match_best(
        "工资",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "none"
    assert result["category_id"] is None
    assert result["confidence"] == 0
    assert result["rule_id"] is None
    assert result["reason"] == "无匹配"


def test_keyword_rule_direction_out_misses_in_query() -> None:
    rules = [_rule(3, "房租", 77, "out")]
    result = match_best(
        "房租",
        "",
        "in",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "none"
    assert result["category_id"] is None
    assert result["confidence"] == 0
    assert result["rule_id"] is None


def test_alias_direction_in_misses_out_query_but_hits_in_query() -> None:
    aliases = [{"alias": "星巴克", "direction": "in", "category_id": 66}]
    out_result = match_best(
        "星巴克",
        "",
        "out",
        rules=[],
        aliases=aliases,
        history=[],
        top_categories=[],
    )
    assert out_result["source"] == "none"
    assert out_result["category_id"] is None
    in_result = match_best(
        "星巴克",
        "",
        "in",
        rules=[],
        aliases=aliases,
        history=[],
        top_categories=[],
    )
    assert in_result["source"] == "alias"
    assert in_result["category_id"] == 66
    assert in_result["rule_id"] is None
    assert in_result["reason"] == "别名记忆命中"
