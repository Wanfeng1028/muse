"""v2.13.0 落地说明：fuzzy 规则参与 match_best 调度，
层级在关键词之后、历史之前；对照用例：精确规则层级高于模糊。"""

import pytest

from ledger import matching


def R(id, kw, pt, cid, direction="any", priority=0, enabled=1):
    return {
        "id": id,
        "keyword": kw,
        "pattern_type": pt,
        "category_id": cid,
        "direction": direction,
        "priority": priority,
        "is_enabled": enabled,
    }


def call(cp, summary, direction, rules, aliases=[], history=[]):
    return matching.match_best(
        cp,
        summary,
        direction,
        rules=rules,
        aliases=aliases,
        history=history,
        top_categories=[],
    )


@pytest.mark.asyncio
async def test_fuzzy_rule_now_matches():
    """v2.13.0：fuzzy 规则已落地"""
    rules = [R(1, "星巴克", "fuzzy", 101)]
    result = call("", "星巴克咖啡", "out", rules)
    assert result["source"] == "rule_fuzzy"
    assert result["category_id"] == 101
    assert result["confidence"] == 92


@pytest.mark.asyncio
async def test_keyword_rule_still_matches_when_fuzzy_present():
    """keyword 层级高于 fuzzy，即使存在 fuzzy 规则也应命中 keyword"""
    rules = [
        R(1, "星巴克", "fuzzy", 101),
        R(2, "咖啡", "keyword", 202),
    ]
    result = call("", "星巴克咖啡", "out", rules)
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 202


@pytest.mark.asyncio
async def test_preview_fuzzy_source_and_category_id():
    """v2.13.0：fuzzy 规则已实现"""
    rules = [R(7, "滴滴", "fuzzy", 303)]
    result = call("", "滴滴出行", "out", rules)
    assert result["source"] == "rule_fuzzy"
    assert result["category_id"] == 303
