from __future__ import annotations

from ledger.matching import _PUNCTUATION, normalize


def test_normalize_removes_chinese_punctuation() -> None:
    assert normalize("招商银行，借记卡。") == "招商银行借记卡"
    assert normalize("户名：张三；卡号：123") == "户名张三卡号123"


def test_normalize_removes_dot_bullet_pipe_slash_dash() -> None:
    assert normalize("工商银行·借记卡") == "工商银行借记卡"
    assert normalize("a/b-c") == "abc"
    assert normalize("a•b|c") == "abc"
    assert normalize("·•|/-") == ""


def test_normalize_lowercases() -> None:
    assert normalize("StarBucks COFFEE") == "starbuckscoffee"
    assert normalize("ABC") == "abc"


def test_normalize_strips_all_whitespace() -> None:
    assert normalize("  盒马 鲜生 ") == "盒马鲜生"
    assert normalize("\t盒马\n鲜生\r") == "盒马鲜生"


def test_normalize_empty_and_none() -> None:
    assert normalize("") == ""
    assert normalize(None) == ""


def test_normalize_keeps_characters_outside_punctuation_set() -> None:
    assert "（" not in _PUNCTUATION
    assert "）" not in _PUNCTUATION
    assert normalize("喜茶（深圳）") == "喜茶（深圳）"
    assert normalize("微信+支付宝") == "微信+支付宝"
    assert normalize("100%") == "100%"
