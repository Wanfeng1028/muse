from __future__ import annotations

from ledger.matching import _pick_best_keyword, match_best, match_by_rules


def _kw(rule_id: int, keyword: str, category_id: int, priority: int = 5, direction: str = "any") -> dict:
    return {
        "id": rule_id,
        "keyword": keyword,
        "category_id": category_id,
        "priority": priority,
        "direction": direction,
        "pattern_type": "keyword",
        "is_enabled": 1,
    }


def test_pick_best_keyword_tiebreak_smaller_id_wins_when_bigger_id_first() -> None:
    big_id_first = _kw(20, "咖啡", 101)
    small_id_second = _kw(7, "咖啡", 202)
    rules = [big_id_first, small_id_second]
    winner = _pick_best_keyword(rules, "星巴克咖啡", "", "expense")
    assert winner is not None
    assert winner["id"] == 7
    assert winner["category_id"] == 202


def test_match_best_uses_rule_keyword_source_and_smaller_rule_id() -> None:
    rules = [_kw(20, "咖啡", 101), _kw(7, "咖啡", 202)]
    result = match_best(
        "星巴克咖啡",
        "",
        "expense",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert result["source"] == "rule_keyword"
    assert result["rule_id"] == 7
    assert result["category_id"] == 202
    assert result["confidence"] == 95
    assert result["reason"] == "关键词规则「咖啡」命中"


def test_pick_best_keyword_three_way_tie_chooses_min_id() -> None:
    rules = [_kw(31, "超市", 301), _kw(12, "超市", 302), _kw(25, "超市", 303)]
    winner = _pick_best_keyword(rules, "永辉超市", "", "expense")
    assert winner is not None
    assert winner["id"] == 12
    assert winner["category_id"] == 302


def test_match_best_vs_match_by_rules_tiebreak_differs() -> None:
    rules = [_kw(20, "咖啡", 101), _kw(7, "咖啡", 202)]

    best = match_best(
        "星巴克咖啡",
        "",
        "expense",
        rules=rules,
        aliases=[],
        history=[],
        top_categories=[],
    )
    assert best["source"] == "rule_keyword"
    assert best["rule_id"] == 7
    assert best["category_id"] == 202

    by_rules = match_by_rules("星巴克咖啡", "", "expense", rules=rules, include_rule_id=True)
    assert by_rules is not None
    assert by_rules[0] == 101
    assert by_rules[0] != best["category_id"]
