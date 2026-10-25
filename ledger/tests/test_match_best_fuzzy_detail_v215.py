"""match_best 模糊分支带 detail（v2.15.0）：与 v2.14 预览链条 detail 同口径。"""

from ledger.matching import match_best


def _fuzzy_rule(keyword="星巴克"):
    return {
        "id": 1,
        "keyword": keyword,
        "pattern_type": "fuzzy",
        "category_id": 5,
        "direction": "any",
        "priority": 1,
        "is_enabled": 1,
    }


def test_fuzzy_hit_carries_detail_substring():
    result = match_best(
        "星巴克", "咖啡", "out",
        rules=[_fuzzy_rule()], aliases=[], history=[], top_categories=[],
    )
    assert result["source"] == "rule_fuzzy"
    assert result["confidence"] == 92
    assert result["detail"] == {
        "matched": True, "distance": 0, "window": "星巴克", "threshold": 1,
    }


def test_fuzzy_hit_carries_detail_one_char_diff():
    result = match_best(
        "", "星巴客咖啡", "out",
        rules=[_fuzzy_rule()], aliases=[], history=[], top_categories=[],
    )
    assert result["source"] == "rule_fuzzy"
    assert result["detail"]["matched"] is True
    assert result["detail"]["distance"] == 1
    assert result["detail"]["window"] == "星巴"


def test_non_fuzzy_branch_has_no_detail():
    rule = {
        "id": 2, "keyword": "美团", "pattern_type": "keyword",
        "category_id": 6, "direction": "any", "priority": 1, "is_enabled": 1,
    }
    result = match_best(
        "美团", "外卖", "out",
        rules=[rule], aliases=[], history=[], top_categories=[],
    )
    assert result["source"] == "rule_keyword"
    assert "detail" not in result
