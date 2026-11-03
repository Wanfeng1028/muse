from __future__ import annotations

from ledger.matching import match_best


def _rules(*items: dict) -> list[dict]:
    return list(items)


def test_regex_higher_priority_beats_keyword():
    rules = _rules(
        {
            "id": 11,
            "keyword": "星巴克",
            "pattern_type": "keyword",
            "category_id": 201,
            "direction": "any",
            "priority": 5,
            "is_enabled": 1,
        },
        {
            "id": 22,
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": 202,
            "direction": "any",
            "priority": 10,
            "is_enabled": 1,
        },
    )
    result = match_best(
        "星巴克咖啡",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "rule_regex"
    assert result["confidence"] == 97
    assert result["rule_id"] == 22
    assert result["category_id"] == 202
    assert "星巴克.*" in result["reason"]


def test_equal_priority_prefers_regex():
    rules = _rules(
        {
            "id": 31,
            "keyword": "星巴克",
            "pattern_type": "keyword",
            "category_id": 301,
            "direction": "any",
            "priority": 7,
            "is_enabled": 1,
        },
        {
            "id": 32,
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": 302,
            "direction": "any",
            "priority": 7,
            "is_enabled": 1,
        },
    )
    result = match_best(
        "星巴克咖啡",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "rule_regex"
    assert result["confidence"] == 97
    assert result["rule_id"] == 32
    assert result["category_id"] == 302
    assert result["reason"] == "正则规则「星巴克.*」命中"


def test_keyword_higher_priority_beats_regex():
    rules = _rules(
        {
            "id": 41,
            "keyword": "星巴克",
            "pattern_type": "keyword",
            "category_id": 401,
            "direction": "any",
            "priority": 10,
            "is_enabled": 1,
        },
        {
            "id": 42,
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": 402,
            "direction": "any",
            "priority": 5,
            "is_enabled": 1,
        },
    )
    result = match_best(
        "星巴克咖啡",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "rule_keyword"
    assert result["confidence"] == 95
    assert result["rule_id"] == 41
    assert result["category_id"] == 401
    assert result["reason"] == "关键词规则「星巴克」命中"


def test_winning_reason_contains_rule_keyword():
    rules = _rules(
        {
            "id": 51,
            "keyword": "星巴克",
            "pattern_type": "keyword",
            "category_id": 501,
            "direction": "any",
            "priority": 3,
            "is_enabled": 1,
        },
        {
            "id": 52,
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": 502,
            "direction": "any",
            "priority": 9,
            "is_enabled": 1,
        },
    )
    result = match_best(
        "星巴克咖啡",
        "",
        "out",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["reason"] == "正则规则「星巴克.*」命中"
    assert result["rule_id"] == 52
    assert result["confidence"] == 97

    flipped = _rules(
        {
            "id": 53,
            "keyword": "星巴克",
            "pattern_type": "keyword",
            "category_id": 503,
            "direction": "any",
            "priority": 9,
            "is_enabled": 1,
        },
        {
            "id": 54,
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": 504,
            "direction": "any",
            "priority": 3,
            "is_enabled": 1,
        },
    )
    result2 = match_best(
        "星巴克咖啡",
        "",
        "out",
        rules=flipped,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result2["reason"] == "关键词规则「星巴克」命中"
    assert result2["rule_id"] == 53
    assert result2["confidence"] == 95
