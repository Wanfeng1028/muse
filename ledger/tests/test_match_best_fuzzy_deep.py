"""match_best 深测：fuzzy 类型规则的调度行为。

本文件聚焦 pattern_type="fuzzy" 的规则在 match_best 中的处理，
包括：
1. 规则集合中 fuzzy 规则是否被纳入候选（已知行为记录）；
2. preview 链路中 fuzzy 规则的展示形式（source=rule_fuzzy）。

纯单元测试，直接调用 ledger.matching.match_best，不启动 app。
"""

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
async def test_fuzzy_rule_currently_ignored_known_behavior():
    """已知行为：match_best 目前只收 keyword / regex 规则，fuzzy 规则被忽略。

    当规则集合中仅存在 pattern_type="fuzzy" 的规则时，match_best
    不会命中该规则，返回的 source 不应为 rule_fuzzy，
    category_id 应为 None（无匹配）。
    """
    rules = [R(1, "星巴克", "fuzzy", 101)]
    result = call("", "星巴克咖啡", "out", rules)
    # 已知行为：fuzzy 规则当前不参与匹配
    assert result.get("source") != "rule_fuzzy"
    assert result.get("category_id") is None


@pytest.mark.asyncio
async def test_keyword_rule_still_matches_when_fuzzy_present():
    """已知行为对照：fuzzy 规则被忽略时，keyword 规则仍正常命中。

    规则中同时包含一条 fuzzy 规则和一条 keyword 规则，
    期望命中 keyword 规则，source=rule，category_id=202。
    """
    rules = [
        R(1, "星巴克", "fuzzy", 101),
        R(2, "咖啡", "keyword", 202),
    ]
    result = call("", "星巴克咖啡", "out", rules)
    assert result.get("source") == "rule_keyword"
    assert result.get("category_id") == 202


@pytest.mark.asyncio
async def test_preview_fuzzy_source_and_category_id():
    """fuzzy pattern_type 规则暂未实现（已知缺口）：match_by_rules 忽略 fuzzy 规则。

    当前行为：fuzzy 规则不参与匹配，返回 None。
    TODO: 实现 fuzzy 规则的编辑距离匹配后，恢复 source="rule_fuzzy" 断言。
    """
    rules = [R(7, "滴滴", "fuzzy", 303)]
    result = call("", "滴滴出行", "out", rules)
    assert result.get("source") == "none"
