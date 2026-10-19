import re

import pytest

from ledger import matching


def test_empty_pattern_rejected():
    """空字符串应被判定为不安全，返回非空原因。"""
    reason = matching.check_pattern_safety("")
    assert reason is not None
    assert "正则不能为空" in reason


def test_whitespace_pattern_rejected():
    """纯空白字符串应被判定为不安全，返回非空原因。"""
    reason = matching.check_pattern_safety("   ")
    assert reason is not None
    assert "正则不能为空" in reason


def test_too_long_pattern_rejected():
    """超过长度上限的模式应被判定为不安全，原因含过长提示。"""
    reason = matching.check_pattern_safety("a" * 201)
    assert reason is not None
    assert "过长" in reason


def test_boundary_length_pattern_allowed():
    """恰好 200 个字符的模式应在长度上限内，不因长度被拒。"""
    reason = matching.check_pattern_safety("a" * 200)
    assert reason is None


def test_nested_quantifier_rejected():
    """嵌套量词如 (a+)+$ 应被判定为不安全，原因含嵌套量词提示。"""
    reason = matching.check_pattern_safety("(a+)+$")
    assert reason is not None
    assert "嵌套量词" in reason


def test_single_quantifier_allowed():
    """单层量词如 (a|b)*c 属于安全模式，应返回 None。"""
    reason = matching.check_pattern_safety("(a|b)*c")
    assert reason is None


def test_normal_chinese_pattern_allowed():
    """正常中文正则 滴滴.*出行 必须放行，返回 None。"""
    reason = matching.check_pattern_safety("滴滴.*出行")
    assert reason is None


def test_backreference_rejected():
    """包含回溯引用 \\1 的模式应被判定为不安全，原因含回溯引用提示。"""
    reason = matching.check_pattern_safety(r"(a)\1")
    assert reason is not None
    assert "回溯引用" in reason


def test_backtracking_risk_rejected():
    """连续通配如 .*.*x 应被判定为不安全，原因含回溯风险提示。"""
    reason = matching.check_pattern_safety(".*.*x")
    assert reason is not None
    assert "回溯风险" in reason


def test_safe_search_haystack_limit_returns_false():
    """haystack 超过熔断阈值时 safe_regex_search 应返回 False。"""
    assert matching.safe_regex_search(re.compile("a+"), "a" * 600) is False


def test_safe_search_normal_match_returns_true():
    """正常 haystack 内命中时应返回 True。"""
    assert matching.safe_regex_search(re.compile("滴滴"), "滴滴出行") is True


def test_safe_search_no_match_returns_false():
    """正常 haystack 内未命中时应返回 False。"""
    assert matching.safe_regex_search(re.compile("滴滴"), "公交出行") is False


def test_compile_rule_pattern_invalid_regex_returns_none():
    """非法正则表达式经 compile_rule_pattern 应返回 None（保持原有行为）。"""
    assert matching.compile_rule_pattern("(a+") is None


def test_compile_rule_pattern_valid_regex_returns_pattern():
    """合法正则经 compile_rule_pattern 应返回可用的编译对象。"""
    compiled = matching.compile_rule_pattern("滴滴.*出行")
    assert compiled is not None
    assert compiled.search("滴滴快车出行") is not None


def test_compile_rule_pattern_unsafe_returns_none():
    """不安全模式经 compile_rule_pattern 应返回 None。"""
    assert matching.compile_rule_pattern("(a+)+$") is None
