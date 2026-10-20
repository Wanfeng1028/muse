from __future__ import annotations

from ledger.matching import detect_transfer


def test_counterparty_extends_account_name_returns_account_id() -> None:
    account_names = {1: "招商银行"}
    assert detect_transfer("招商银行股份有限公司", account_names) == 1


def test_account_name_extends_counterparty_returns_account_id() -> None:
    account_names = {1: "招商银行股份有限公司"}
    assert detect_transfer("招商银行", account_names) == 1


def test_punctuation_difference_normalized_equal_returns_account_id() -> None:
    account_names = {1: "工商银行借记卡"}
    assert detect_transfer("工商银行·借记卡", account_names) == 1


def test_case_insensitive_match_returns_account_id() -> None:
    account_names = {1: "icbc"}
    assert detect_transfer("ICBC", account_names) == 1


def test_multiple_fuzzy_hits_returns_smallest_account_id() -> None:
    account_names = {5: "招商银行", 3: "招商银行信用卡"}
    assert detect_transfer("招商银行", account_names) == 3


def test_unrelated_counterparty_returns_none() -> None:
    account_names = {1: "招商银行"}
    assert detect_transfer("麦当劳餐厅", account_names) is None


def test_empty_counterparty_returns_none() -> None:
    account_names = {1: "招商银行"}
    assert detect_transfer("", account_names) is None


def test_empty_account_names_returns_none() -> None:
    assert detect_transfer("招商银行", {}) is None
