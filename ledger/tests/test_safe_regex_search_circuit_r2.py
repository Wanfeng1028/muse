from __future__ import annotations

import re

from ledger.matching import MAX_REGEX_HAYSTACK, safe_regex_search


def test_haystack_501_with_match_is_circuit_broken() -> None:
    compiled = re.compile(r"abc")
    haystack = "abc" + "x" * 498
    assert len(haystack) == 501
    assert safe_regex_search(compiled, haystack) is False


def test_haystack_exactly_500_with_match_returns_true() -> None:
    compiled = re.compile(r"abc")
    haystack = "abc" + "x" * 497
    assert len(haystack) == 500
    assert safe_regex_search(compiled, haystack) is True


def test_haystack_none_returns_false() -> None:
    compiled = re.compile(r"abc")
    assert safe_regex_search(compiled, None) is False


def test_normal_short_haystack_match_and_miss() -> None:
    compiled = re.compile(r"abc")
    assert safe_regex_search(compiled, "xxabcxx") is True
    assert safe_regex_search(compiled, "xxabx") is False


def test_circuit_break_independent_of_pattern() -> None:
    compiled = re.compile(r".*")
    haystack = "y" * 501
    assert len(haystack) == 501
    assert safe_regex_search(compiled, haystack) is False
    assert MAX_REGEX_HAYSTACK == 500
