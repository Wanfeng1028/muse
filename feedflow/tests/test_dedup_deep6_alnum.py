import pytest
from feedflow.dedup import tokenize, simhash


def test_upper_lower_same_tokens():
    assert tokenize("ABC123") == ["abc123"]


def test_case_insensitive_simhash():
    assert simhash("ABC123") == simhash("abc123")


def test_dot_skipped():
    assert tokenize("v2.0") == ["v2", "0"]
