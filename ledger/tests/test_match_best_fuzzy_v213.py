"""fuzzy 规则落地的测试"""

from ledger.matching import _pick_best_fuzzy, fuzzy_rule_matches, match_best


def test_fuzzy_rule_matches_substring():
    assert fuzzy_rule_matches("星巴克", "星巴克咖啡") is True


def test_fuzzy_rule_matches_one_char_diff():
    assert fuzzy_rule_matches("星巴克", "星巴客咖啡") is True


def test_fuzzy_rule_matches_two_char_word_diff():
    assert fuzzy_rule_matches("北京", "南京烤鸭") is False


def test_fuzzy_rule_matches_empty_and_short():
    assert fuzzy_rule_matches("", "星巴克") is False
    assert fuzzy_rule_matches("星", "星巴克") is False


def test_fuzzy_rule_matches_far_word():
    assert fuzzy_rule_matches("星巴克", "肯德基") is False


def test_pick_best_fuzzy_direction_filter():
    rule = {
        "id": 1,
        "keyword": "滴滴",
        "pattern_type": "fuzzy",
        "category_id": 303,
        "direction": "in",
        "priority": 1,
        "is_enabled": 1,
    }
    result = _pick_best_fuzzy([rule], "滴滴", "滴滴出行", "out")
    assert result is None


def test_pick_best_fuzzy_disabled_filter():
    rule = {
        "id": 1,
        "keyword": "滴滴",
        "pattern_type": "fuzzy",
        "category_id": 303,
        "direction": "any",
        "priority": 1,
        "is_enabled": 0,
    }
    result = _pick_best_fuzzy([rule], "滴滴", "滴滴出行", "out")
    assert result is None


def test_pick_best_fuzzy_tiebreaker():
    rule1 = {
        "id": 1,
        "keyword": "星巴克",
        "pattern_type": "fuzzy",
        "category_id": 101,
        "direction": "any",
        "priority": 10,
        "is_enabled": 1,
    }
    rule2 = {
        "id": 2,
        "keyword": "星巴克咖啡",
        "pattern_type": "fuzzy",
        "category_id": 102,
        "direction": "any",
        "priority": 5,
        "is_enabled": 1,
    }
    result = _pick_best_fuzzy([rule1, rule2], "", "星巴克咖啡", "out")
    assert result["category_id"] == 101

    rule3 = {
        "id": 3,
        "keyword": "星巴克",
        "pattern_type": "fuzzy",
        "category_id": 103,
        "direction": "any",
        "priority": 5,
        "is_enabled": 1,
    }
    rule4 = {
        "id": 4,
        "keyword": "星巴克咖啡",
        "pattern_type": "fuzzy",
        "category_id": 104,
        "direction": "any",
        "priority": 5,
        "is_enabled": 1,
    }
    result = _pick_best_fuzzy([rule3, rule4], "", "星巴克咖啡", "out")
    assert result["category_id"] == 104


def test_match_best_fuzzy_solo():
    rules = [
        {
            "id": 1,
            "keyword": "滴滴",
            "pattern_type": "fuzzy",
            "category_id": 303,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        }
    ]
    result = match_best("", "滴滴出行", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "rule_fuzzy"
    assert result["category_id"] == 303
    assert result["confidence"] == 92


def test_match_best_keyword_over_fuzzy():
    rules = [
        {
            "id": 1,
            "keyword": "星巴克",
            "pattern_type": "fuzzy",
            "category_id": 101,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        },
        {"id": 2, "keyword": "咖啡", "category_id": 202, "direction": "any", "priority": 1, "is_enabled": 1},
    ]
    result = match_best("", "星巴克咖啡", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 202


def test_match_best_fuzzy_over_history():
    rules = [
        {
            "id": 1,
            "keyword": "星巴克",
            "pattern_type": "fuzzy",
            "category_id": 101,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        }
    ]
    history = [
        {"counterparty": "星巴克", "summary": "", "category_id": 999, "direction": "out"},
        {"counterparty": "星巴克", "summary": "", "category_id": 999, "direction": "out"},
    ]
    result = match_best("", "星巴客咖啡", "out", rules=rules, aliases=[], history=history, top_categories=[])
    assert result["source"] == "rule_fuzzy"
    assert result["category_id"] == 101


def test_match_best_fuzzy_not_over_regex():
    rules = [
        {
            "id": 1,
            "keyword": "滴滴.*出行",
            "pattern_type": "regex",
            "category_id": 404,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        },
        {
            "id": 2,
            "keyword": "滴滴",
            "pattern_type": "fuzzy",
            "category_id": 303,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        },
    ]
    result = match_best("", "滴滴出行", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "rule_regex"
    assert result["category_id"] == 404
