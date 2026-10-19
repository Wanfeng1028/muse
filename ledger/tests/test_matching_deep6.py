"""规则引擎 v2 深度测试：正则规则与 match_best 统一调度。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ledger.matching import compile_rule_pattern, match_best, normalize  # noqa: E402


def _regex_rule(rule_id, pattern, category_id, priority=0, direction="any", enabled=1):
    return {
        "id": rule_id,
        "pattern_type": "regex",
        "keyword": pattern,
        "category_id": category_id,
        "priority": priority,
        "direction": direction,
        "is_enabled": enabled,
    }


def _keyword_rule(rule_id, keyword, category_id, priority=0, direction="any", enabled=1):
    return {
        "id": rule_id,
        "pattern_type": "keyword",
        "keyword": keyword,
        "category_id": category_id,
        "priority": priority,
        "direction": direction,
        "is_enabled": enabled,
    }


def _call(counterparty, summary="", direction="out", rules=None, aliases=None,
          history=None, top_categories=None):
    return match_best(
        counterparty,
        summary,
        direction,
        rules=rules or [],
        aliases=aliases or [],
        history=history or [],
        top_categories=top_categories or [],
    )


def test_compile_rule_pattern_valid_and_invalid():
    """合法正则能编译，非法正则返回 None 且不抛异常。"""
    assert compile_rule_pattern("星巴克.*上海") is not None
    assert compile_rule_pattern("([a-z") is None


def test_regex_hit_and_miss():
    """正则 星巴克.*上海 命中上海店，不命中北京店。"""
    rules = [_regex_rule(1, "星巴克.*上海", 101)]
    hit = _call("星巴克静安寺店上海", rules=rules)
    assert hit["source"] == "rule_regex"
    assert hit["category_id"] == 101
    miss = _call("星巴克北京三里屯", rules=rules)
    assert miss["source"] == "none"


def test_invalid_regex_skipped_others_still_work():
    """非法正则被跳过，合法规则照常命中。"""
    rules = [
        _regex_rule(1, "([a-z", 900, priority=999),
        _keyword_rule(2, "星巴克", 102),
    ]
    result = _call("星巴克静安寺店", rules=rules)
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 102


def test_regex_beats_keyword_same_priority():
    """同 priority 下正则优先于关键词。"""
    rules = [
        _regex_rule(1, "星巴克", 201, priority=5),
        _keyword_rule(2, "星巴克", 202, priority=5),
    ]
    result = _call("星巴克静安寺店", rules=rules)
    assert result["source"] == "rule_regex"
    assert result["category_id"] == 201


def test_keyword_beats_regex_when_higher_priority():
    """关键词 priority 更高时，关键词胜出。"""
    rules = [
        _regex_rule(1, "星巴克", 201, priority=5),
        _keyword_rule(2, "星巴克", 202, priority=10),
    ]
    result = _call("星巴克静安寺店", rules=rules)
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 202


def test_keyword_longer_wins_same_priority():
    """同 priority 关键词，更长的 盒马鲜生 胜 盒马。"""
    rules = [
        _keyword_rule(1, "盒马", 301, priority=5),
        _keyword_rule(2, "盒马鲜生", 302, priority=5),
    ]
    result = _call("盒马鲜生会员店", rules=rules)
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 302


def test_alias_beats_high_priority_rule():
    """别名命中优先于任意 priority 的规则。"""
    rules = [_keyword_rule(1, "星巴克", 999, priority=999)]
    aliases = [{"alias": normalize("星巴克"), "category_id": 888, "direction": "out"}]
    result = _call("星巴克", direction="out", rules=rules, aliases=aliases)
    assert result["source"] == "alias"
    assert result["category_id"] == 888


def test_disabled_rule_skipped():
    """is_enabled=0 的规则被跳过。"""
    rules = [_keyword_rule(1, "星巴克", 401, enabled=0)]
    result = _call("星巴克静安寺店", rules=rules)
    assert result["source"] == "none"


def test_direction_mismatch_skipped():
    """direction=in 的规则不命中 direction=out 的条目。"""
    rules = [_keyword_rule(1, "星巴克", 501, direction="in")]
    result = _call("星巴克静安寺店", direction="out", rules=rules)
    assert result["source"] == "none"


def test_keyword_normalization_with_spaces():
    """含空格的商户名归一化后仍被关键词命中。"""
    rules = [_keyword_rule(1, "星巴克", 601)]
    result = _call("星 巴 克", rules=rules)
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 601


def test_match_best_returns_all_keys_and_none_source():
    """match_best 返回含全部五个键；无命中时 source 为 none。"""
    result = _call("完全不认识的商户")
    for key in ("category_id", "confidence", "source", "rule_id", "reason"):
        assert key in result
    assert result["source"] == "none"
    assert result["category_id"] is None
    assert result["confidence"] == 0


def test_chinese_regex_didi():
    """中文正则 滴滴.*出行 命中 滴滴出行科技有限公司。"""
    rules = [_regex_rule(1, "滴滴.*出行", 701)]
    result = _call("滴滴出行科技有限公司", rules=rules)
    assert result["source"] == "rule_regex"
    assert result["category_id"] == 701
