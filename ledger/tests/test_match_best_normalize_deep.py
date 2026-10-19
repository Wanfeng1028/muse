"""match_best 归一化边界深测。

覆盖：
1. 大小写/全半角/空格归一化（normalize 的原文语义）；
2. 空 counterparty + 空 summary；
3. 超长输入（2000 字符）不卡死（计时断言 < 1s）。

全部为纯单元测试，直接调用 ledger.matching.match_best，不启动 app。
"""

import time

import pytest

from ledger import matching


def R(id, kw, pt, cid, direction="any", priority=0, enabled=1):
    return {"id": id, "keyword": kw, "pattern_type": pt, "category_id": cid,
            "direction": direction, "priority": priority, "is_enabled": enabled}


def call(cp, summary, direction, rules, aliases=[], history=[]):
    return matching.match_best(cp, summary, direction, rules=rules, aliases=aliases,
                               history=history, top_categories=[])


def _cid(result):
    """从 match_best 结果中取出 category_id（兼容 dict/None）。"""
    if result is None:
        return None
    if isinstance(result, dict):
        return result.get("category_id")
    return getattr(result, "category_id", None)


def _source(result):
    if result is None:
        return None
    if isinstance(result, dict):
        return result.get("source")
    return getattr(result, "source", None)


@pytest.mark.asyncio
async def test_normalize_case_insensitive_keyword():
    """关键词为英文小写，交易对手方为大写：应命中同一规则。

    预期：source == 'keyword'，category_id == 11。
    """
    rules = [R(1, "starbucks", "keyword", 11, direction="expense")]
    result = call("STARBUCKS", "", "expense", rules)
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 11


@pytest.mark.asyncio
async def test_normalize_fullwidth_consistent():
    """全角字符串归一化保持一致：相同全角关键词可命中。

    normalize 不做全角→半角转换（已知局限），但相同全角串应一致匹配。
    关键词全角 "ａｂｃ１２３"，输入全角 "ａｂｃ１２３"。
    预期：source == 'rule_keyword'，category_id == 12。
    """
    rules = [R(2, "ａｂｃ１２３", "keyword", 12, direction="out")]
    result = call("ａｂｃ１２３", "", "out", rules)
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 12


async def test_normalize_fullwidth_halfwidth_no_match():
    """全角与半角不互通（已知局限）：半角关键词不匹配全角输入。"""
    rules = [R(20, "abc123", "keyword", 12, direction="out")]
    result = call("ａｂｃ１２３", "", "out", rules)
    assert result is None or _cid(result) is None


@pytest.mark.asyncio
async def test_normalize_whitespace_trim():
    """首尾空白应被归一化剥离后匹配。

    关键词 "coffee"，输入 "   coffee   "。
    预期：source == 'keyword'，category_id == 13。
    """
    rules = [R(3, "coffee", "keyword", 13, direction="expense")]
    result = call("   coffee   ", "", "expense", rules)
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 13


@pytest.mark.asyncio
async def test_normalize_internal_spaces_in_summary():
    """summary 中的多余内部空格不应阻碍关键词子串匹配。

    关键词 "metro"，summary "  go   METRO   now "。
    预期：source == 'keyword'，category_id == 14。
    """
    rules = [R(4, "metro", "keyword", 14, direction="expense")]
    result = call("", "  go   METRO   now ", "expense", rules)
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 14


@pytest.mark.asyncio
async def test_normalize_mixed_case_keyword():
    """关键词大小写混合：归一化转小写后应命中。

    关键词 "Café Noodle"，输入 "café noodle"。
    预期：source == 'rule_keyword'，category_id == 15。
    """
    rules = [R(5, "Café Noodle", "keyword", 15, direction="out")]
    result = call("café noodle", "", "out", rules)
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 15


@pytest.mark.asyncio
async def test_empty_counterparty_and_empty_summary_no_match():
    """空 counterparty + 空 summary：不应匹配任何规则。

    预期：返回 None 或 category_id 为 None，且 source 不是 'keyword'。
    """
    rules = [R(6, "anything", "keyword", 16, direction="any")]
    result = call("", "", "any", rules)
    assert _cid(result) is None
    assert _source(result) != "keyword"


@pytest.mark.asyncio
async def test_empty_counterparty_and_empty_summary_with_aliases():
    """空输入 + 提供别名规则，仍不应凭空命中。

    预期：category_id 为 None。
    """
    rules = [R(7, "alias_target", "keyword", 17, direction="any")]
    aliases = [{"keyword": "alias_target", "category_id": 17, "direction": "any"}]
    result = call("", "", "any", rules, aliases=aliases)
    assert _cid(result) is None


@pytest.mark.asyncio
async def test_long_input_2000_chars_no_hang():
    """2000 字符的超长输入不应卡死，且应在 1 秒内返回。

    关键词置于超长串中部，验证归一化不因长度爆炸。
    预期：耗时 < 1.0s；source == 'keyword'，category_id == 18。
    """
    long_summary = ("x" * 990) + "needle" + ("y" * 1004)
    assert len(long_summary) == 2000
    rules = [R(8, "needle", "keyword", 18, direction="expense")]

    start = time.perf_counter()
    result = call("", long_summary, "expense", rules)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"超长输入耗时 {elapsed:.3f}s，超过 1s 阈值"
    assert _source(result) == "rule_keyword"
    assert _cid(result) == 18


@pytest.mark.asyncio
async def test_long_input_no_match_still_fast():
    """2000 字符输入且无任何命中时也应在 1 秒内返回。

    预期：耗时 < 1.0s；category_id 为 None。
    """
    long_summary = "z" * 2000
    rules = [R(9, "absent", "keyword", 19, direction="expense")]

    start = time.perf_counter()
    result = call("", long_summary, "expense", rules)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"超长输入无命中耗时 {elapsed:.3f}s，超过 1s 阈值"
    assert _cid(result) is None
