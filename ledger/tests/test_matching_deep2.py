import hashlib
from datetime import date

from ledger.matching import (
    normalize,
    fingerprint,
    match_by_rules,
    match_by_history,
    _top_vote,
    _fuzzy_hit,
    suggest_candidates,
    detect_transfer,
    amount_within,
    within_date_window,
    match_by_alias,
    detect_transfer_pair,
)


def test_normalize_punctuation_deep2():
    assert normalize("，。、；：！？,.!?:;·•|/-") == ""


def test_normalize_whitespace_and_case_deep2():
    assert normalize("  Hello   World  ") == "helloworld"


def test_normalize_none_and_empty_deep2():
    assert normalize(None) == ""
    assert normalize("") == ""


def test_fingerprint_deterministic_and_field_sensitive_deep2():
    fp = fingerprint("2024-01-01", 1000, "out", "商户", "备注")
    assert fp == fingerprint("2024-01-01", 1000, "out", "商户", "备注")
    assert len(fp) == 32
    assert fp == hashlib.sha256(
        "2024-01-01|1000|out|商户|备注".encode("utf-8")
    ).hexdigest()[:32]
    assert fp != fingerprint("2024-01-02", 1000, "out", "商户", "备注")
    assert fp != fingerprint("2024-01-01", 1001, "out", "商户", "备注")
    assert fp != fingerprint("2024-01-01", 1000, "in", "商户", "备注")
    assert fp != fingerprint("2024-01-01", 1000, "out", "商", "备注")
    assert fp != fingerprint("2024-01-01", 1000, "out", "商户", "备")


def test_fingerprint_ignores_punctuation_and_case_deep2():
    a = fingerprint("2024-01-01", 100, "out", "ABC", "Hi!")
    b = fingerprint("2024-01-01", 100, "out", "abc", "hi")
    assert a == b


def test_match_by_rules_direction_filter_deep2():
    rules = [
        {"keyword": "咖啡", "category_id": 1, "direction": "out", "priority": 1},
    ]
    assert match_by_rules("咖啡店", "", "in", rules) is None
    assert match_by_rules("咖啡店", "", "out", rules) == (1, 95)


def test_match_by_rules_priority_wins_deep2():
    rules = [
        {"keyword": "餐", "category_id": 1, "priority": 1},
        {"keyword": "餐厅", "category_id": 2, "priority": 5},
    ]
    assert match_by_rules("某某餐厅", "", "out", rules) == (2, 95)


def test_match_by_rules_tie_longer_keyword_wins_deep2():
    rules = [
        {"keyword": "商", "category_id": 1, "priority": 3},
        {"keyword": "商店", "category_id": 2, "priority": 3},
    ]
    assert match_by_rules("便利商店", "", "out", rules) == (2, 95)


def test_match_by_rules_empty_haystack_deep2():
    rules = [{"keyword": "x", "category_id": 1}]
    assert match_by_rules("", "", "out", rules) is None
    assert match_by_rules("，。", "！？", "out", rules) is None


def test_match_by_history_exact_two_votes_confidence_80_deep2():
    history = [
        {"counterparty": "商户A", "summary": "", "direction": "out", "category_id": 7},
        {"counterparty": "商户a", "summary": "", "direction": "out", "category_id": 7},
    ]
    assert match_by_history("商户A", "", "out", history) == (7, 80)


def test_match_by_history_exact_one_vote_falls_to_fuzzy_deep2():
    history = [
        {"counterparty": "大商户有限公司", "summary": "", "direction": "out", "category_id": 3},
        {"counterparty": "大商户有限公司", "summary": "", "direction": "out", "category_id": 3},
    ]
    assert match_by_history("大商户", "", "out", history) == (3, 65)


def test_match_by_history_fuzzy_two_votes_confidence_65_deep2():
    history = [
        {"counterparty": "星巴克咖啡", "summary": "", "direction": "out", "category_id": 5},
        {"counterparty": "星巴克咖啡店", "summary": "", "direction": "out", "category_id": 5},
    ]
    assert match_by_history("星巴克", "", "out", history) == (5, 65)


def test_match_by_history_tie_takes_smaller_id_deep2():
    history = [
        {"counterparty": "X", "summary": "", "direction": "out", "category_id": 9},
        {"counterparty": "X", "summary": "", "direction": "out", "category_id": 9},
        {"counterparty": "X", "summary": "", "direction": "out", "category_id": 4},
        {"counterparty": "X", "summary": "", "direction": "out", "category_id": 4},
    ]
    assert match_by_history("X", "", "out", history) == (4, 80)


def test_match_by_history_no_match_deep2():
    history = [
        {"counterparty": "甲", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "乙", "summary": "", "direction": "out", "category_id": 2},
    ]
    assert match_by_history("丙", "", "out", history) is None


def test_top_vote_tie_smaller_id_deep2():
    assert _top_vote({5: 3, 2: 3, 8: 1}) == (2, 3)
    assert _top_vote({7: 4, 3: 2}) == (7, 4)


def test_fuzzy_hit_short_strings_false_deep2():
    assert _fuzzy_hit("", "abc") is False
    assert _fuzzy_hit("a", "abc") is False
    assert _fuzzy_hit("abc", "a") is False
    assert _fuzzy_hit("a", "b") is False


def test_fuzzy_hit_substring_true_deep2():
    assert _fuzzy_hit("星巴克", "星巴克咖啡") is True
    assert _fuzzy_hit("星巴克咖啡", "星巴克") is True
    assert _fuzzy_hit("星巴克", "肯德基") is False


def test_suggest_candidates_cap_and_confidence_sequence_deep2():
    history = [
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "B", "summary": "", "direction": "out", "category_id": 2},
        {"counterparty": "B", "summary": "", "direction": "out", "category_id": 2},
        {"counterparty": "C", "summary": "", "direction": "out", "category_id": 3},
        {"counterparty": "C", "summary": "", "direction": "out", "category_id": 3},
        {"counterparty": "D", "summary": "", "direction": "out", "category_id": 4},
        {"counterparty": "D", "summary": "", "direction": "out", "category_id": 4},
    ]
    top_categories = [(10, 5), (11, 3)]
    result = suggest_candidates("", "", "out", history, top_categories)
    assert len(result) == 3
    assert [r[0] for r in result] == [1, 2, 3]
    assert [r[2] for r in result] == [55, 45, 35]
    assert all(r[1] == "该商户历史多归为此分类" for r in result)


def test_suggest_candidates_dedup_and_fill_from_top_deep2():
    history = [
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
    ]
    top_categories = [(1, 9), (2, 8), (3, 7)]
    result = suggest_candidates("", "", "out", history, top_categories)
    assert len(result) == 3
    assert [r[0] for r in result] == [1, 2, 3]
    assert result[0][1] == "该商户历史多归为此分类"
    assert result[1][1] == "同方向常用分类"
    assert result[2][1] == "同方向常用分类"
    assert [r[2] for r in result] == [55, 45, 35]


def test_detect_transfer_exact_and_fuzzy_deep2():
    accounts = {2: "招商银行", 1: "支付宝"}
    assert detect_transfer("支付宝", accounts) == 1
    assert detect_transfer("招商银行储蓄", accounts) == 2


def test_detect_transfer_empty_and_skip_empty_names_deep2():
    accounts = {1: "", 2: "支付宝"}
    assert detect_transfer("", accounts) is None
    assert detect_transfer("支付宝", accounts) == 2


def test_detect_transfer_no_match_deep2():
    accounts = {1: "支付宝"}
    assert detect_transfer("微信支付", accounts) is None


def test_amount_within_abs_tolerance_boundary_deep2():
    assert amount_within(100, 150, 50, 0) is True
    assert amount_within(100, 151, 50, 0) is False


def test_amount_within_pct_tol_nonpositive_deep2():
    assert amount_within(100, 200, 0, 0) is False
    assert amount_within(100, 200, 0, -1) is False


def test_amount_within_double_zero_deep2():
    assert amount_within(0, 0, 0, 0) is True


def test_amount_within_integer_arithmetic_boundary_deep2():
    assert amount_within(100, 200, 0, 100) is True
    assert amount_within(100, 201, 0, 100) is True


def test_within_date_window_invalid_dates_deep2():
    assert within_date_window("not-a-date", "2024-01-10", 3) is False
    assert within_date_window("2024-01-10", "2024-13-40", 3) is False
    assert within_date_window("2024-01-10", "2024-13-40", 3) is False


def test_within_date_window_boundary_deep2():
    assert within_date_window("2024-01-10", "2024-01-13", 3) is True
    assert within_date_window("2024-01-10", "2024-01-14", 3) is False


def test_match_by_alias_direction_mismatch_skipped_deep2():
    aliases = [
        {"alias": "美团", "direction": "out", "category_id": 5},
    ]
    assert match_by_alias("美团", "in", aliases) is None
    assert match_by_alias("美团", "out", aliases) == (5, 85)


def test_match_by_alias_empty_counterparty_deep2():
    aliases = [{"alias": "美团", "direction": "out", "category_id": 5}]
    assert match_by_alias("", "out", aliases) is None
    assert match_by_alias("，。", "out", aliases) is None


def test_detect_transfer_pair_greedy_smaller_out_first_deep2():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "out", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 3, "direction": "in", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 4, "direction": "in", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    accounts = {1: "支付宝"}
    result = detect_transfer_pair(items, accounts)
    assert result == [(1, 3), (2, 4)]


def test_detect_transfer_pair_used_items_not_reused_deep2():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    accounts = {1: "支付宝"}
    result = detect_transfer_pair(items, accounts)
    assert result == [(1, 2)]


def test_detect_transfer_pair_no_account_match_no_pair_deep2():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "微信"},
    ]
    accounts = {1: "招商银行"}
    result = detect_transfer_pair(items, accounts)
    assert result == []


def test_detect_transfer_pair_amount_or_date_mismatch_deep2():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 500, "occurred_on": date(2024, 1, 1), "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 9000, "occurred_on": date(2024, 1, 1), "counterparty": "支付宝"},
        {"id": 3, "direction": "in", "amount_cents": 500, "occurred_on": date(2024, 3, 1), "counterparty": "支付宝"},
    ]
    accounts = [{"account_id": 1, "name": "支付宝"}]
    result = detect_transfer_pair(items, accounts)
    assert result == []