from __future__ import annotations

import re

import pytest

from ledger.matching import check_pattern_safety, compile_rule_pattern


def test_nested_quantifier_rejected():
    reason = check_pattern_safety("(a+)+")
    assert reason is not None
    assert "回溯" in reason
    assert compile_rule_pattern("(a+)+") is None


def test_multiple_dotstar_rejected():
    reason = check_pattern_safety("a.*b.*c")
    assert reason is not None
    assert "回溯" in reason
    assert compile_rule_pattern("a.*b.*c") is None


def test_backreference_rejected():
    reason = check_pattern_safety(r"(a)\1")
    assert reason is not None
    assert "回溯" in reason
    assert compile_rule_pattern(r"(a)\1") is None


def test_pattern_length_boundary():
    too_long = "x" * 201
    reason_long = check_pattern_safety(too_long)
    assert reason_long is not None
    assert "过长" in reason_long
    assert compile_rule_pattern(too_long) is None

    at_limit = "x" * 200
    assert check_pattern_safety(at_limit) is None
    assert compile_rule_pattern(at_limit) is not None


def test_empty_pattern_rejected():
    for blank in ("", "   "):
        reason = check_pattern_safety(blank)
        assert reason is not None
        assert "不能为空" in reason
        assert compile_rule_pattern(blank) is None


def test_safe_pattern_compiles_and_matches():
    assert check_pattern_safety(r"abc\d+") is None
    compiled = compile_rule_pattern(r"abc\d+")
    assert compiled is not None
    assert compiled.search("xxabc123") is not None
    assert bool(compiled.search("xxabc123")) is True


def test_invalid_syntax_passes_safety_but_fails_compile():
    assert check_pattern_safety("(") is None
    assert compile_rule_pattern("(") is None


def test_safe_regex_search_haystack_fuse():
    from ledger.matching import MAX_REGEX_HAYSTACK, safe_regex_search

    compiled = re.compile(r"abc\d+")
    assert safe_regex_search(compiled, None) is False
    assert safe_regex_search(compiled, "abc123") is True
    assert safe_regex_search(compiled, "z" * MAX_REGEX_HAYSTACK) is False
    assert safe_regex_search(compiled, "abc123" + "z" * MAX_REGEX_HAYSTACK) is False
    boundary = "abc123" + "z" * (MAX_REGEX_HAYSTACK - 6)
    assert len(boundary) == MAX_REGEX_HAYSTACK
    assert safe_regex_search(compiled, boundary) is True


def test_compile_rule_pattern_returns_usable_regex():
    compiled = compile_rule_pattern("餐.*费")
    assert compiled is not None
    assert compiled.search("今天餐费支出") is not None
    assert compiled.search("打车") is None
    with pytest.raises(re.error):
        re.compile("(")
