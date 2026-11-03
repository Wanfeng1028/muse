import pytest

from ledger.matching import check_pattern_safety, compile_rule_pattern, match_best


@pytest.mark.parametrize(
    "pattern",
    [
        "([a-z]+){2,}",
        "(a+){2,}",
        "(a+){2}",
        "(a+){1,3}",
        "([a-z]{2})+",
        "(?:a+)+",
    ],
)
def test_brace_nested_quantifier_rejected(pattern):
    result = check_pattern_safety(pattern)
    assert result is not None, f"模式 {pattern} 应被拒绝但返回了 None"
    assert "嵌套量词" in result, f"模式 {pattern} 的拒绝原因应包含'嵌套量词'，实际为: {result}"


@pytest.mark.parametrize(
    "pattern",
    [
        "(ab){2}",
        "(a|b){2}",
        "\\d{3}",
    ],
)
def test_brace_quantifier_without_inner_quantifier_allowed(pattern):
    result = check_pattern_safety(pattern)
    assert result is None, f"模式 {pattern} 应被允许但返回了: {result}"


def test_unclosed_group_not_flagged():
    result = check_pattern_safety("(a+")
    assert result is None


def test_compile_rule_pattern_rejects_brace_nested():
    result = compile_rule_pattern("([a-z]+){2,}")
    assert result is None


def test_match_best_skips_historic_dirty_regex_rule():
    rules = [
        {
            "id": 1,
            "keyword": "([a-z]+){2,}",
            "category_id": 11,
            "priority": 9,
            "pattern_type": "regex",
            "is_enabled": 1,
            "direction": "any",
        },
        {
            "id": 2,
            "keyword": "星巴克",
            "category_id": 22,
            "priority": 1,
            "pattern_type": "keyword",
            "is_enabled": 1,
            "direction": "any",
        },
    ]
    result = match_best("星巴克", "", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 22


def test_match_best_dirty_regex_alone_matches_nothing():
    rules = [
        {
            "id": 1,
            "keyword": "([a-z]+){2,}",
            "category_id": 11,
            "priority": 9,
            "pattern_type": "regex",
            "is_enabled": 1,
            "direction": "any",
        },
    ]
    result = match_best("aaaa", "", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "none"
    assert result["category_id"] is None
