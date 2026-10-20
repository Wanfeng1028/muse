from __future__ import annotations

from ledger.matching import match_by_rules


def test_meituan_keyword_hit_returns_category_and_95() -> None:
    rules = [
        {"id": 1, "keyword": "美团", "category_id": 301, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("美团外卖", "", "out", rules)
    assert result == (301, 95)


def test_xicha_with_full_width_paren_still_matches() -> None:
    rules = [
        {"id": 2, "keyword": "喜茶", "category_id": 302, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("喜茶（深圳）", "", "out", rules)
    assert result == (302, 95)


def test_starbucks_case_insensitive_match() -> None:
    rules = [
        {"id": 3, "keyword": "starbucks", "category_id": 303, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("StarBucks 咖啡", "", "out", rules)
    assert result == (303, 95)


def test_cmb_with_punctuation_removed_still_matches() -> None:
    rules = [
        {"id": 4, "keyword": "招商银行", "category_id": 304, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("招商银行，借记卡。", "", "out", rules)
    assert result == (304, 95)


def test_direction_filter_blocks_mismatch_and_any_passes() -> None:
    rules = [
        {"id": 5, "keyword": "工资", "category_id": 401, "direction": "in", "priority": 5, "is_enabled": 1},
    ]
    assert match_by_rules("工资发放", "", "out", rules) is None
    assert match_by_rules("工资发放", "", "in", rules) == (401, 95)

    any_rules = [
        {"id": 6, "keyword": "工资", "category_id": 402, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    assert match_by_rules("工资发放", "", "in", any_rules) == (402, 95)
    assert match_by_rules("工资发放", "", "out", any_rules) == (402, 95)


def test_haystack_combines_counterparty_and_summary() -> None:
    rules = [
        {"id": 7, "keyword": "地铁", "category_id": 501, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("", "地铁通勤", "out", rules)
    assert result == (501, 95)
