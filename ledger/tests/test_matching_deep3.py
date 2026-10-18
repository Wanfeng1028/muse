
from ledger.matching import (
    _fuzzy_hit,
    _top_vote,
    amount_within,
    detect_transfer,
    detect_transfer_pair,
    fingerprint,
    match_by_alias,
    match_by_history,
    match_by_rules,
    normalize,
    suggest_candidates,
    within_date_window,
)


def test_normalize_preserves_non_ascii_and_digits_deep3():
    assert normalize("订单 123 号") == "订单123号"
    assert normalize("ABC-123_xyz") == "abc123_xyz"


def test_normalize_only_whitespace_returns_empty_deep3():
    assert normalize("   \t\n  ") == ""
    assert normalize("\u3000") == ""


def test_fingerprint_normalize_collapses_variants_deep3():
    a = fingerprint("2024-05-05", 999, "in", "  张三  ", "转账，备注")
    b = fingerprint("2024-05-05", 999, "in", "张三", "转账备注")
    assert a == b


def test_fingerprint_negative_amount_distinct_deep3():
    pos = fingerprint("2024-01-01", 100, "out", "x", "y")
    neg = fingerprint("2024-01-01", -100, "out", "x", "y")
    assert pos != neg
    assert len(neg) == 32


def test_match_by_rules_priority_zero_default_deep3():
    rules = [
        {"keyword": "星", "category_id": 1},
        {"keyword": "巴克", "category_id": 2},
    ]
    result = match_by_rules("星巴克", "", "out", rules)
    assert result is not None
    assert result[0] in (1, 2)
    assert result[1] == 95


def test_match_by_rules_keyword_blank_skipped_deep3():
    rules = [
        {"keyword": "  ", "category_id": 1, "priority": 10},
        {"keyword": "店", "category_id": 2, "priority": 1},
    ]
    assert match_by_rules("商店", "", "out", rules) == (2, 95)


def test_match_by_rules_direction_any_matches_both_deep3():
    rules = [{"keyword": "工资", "category_id": 3, "direction": "any"}]
    assert match_by_rules("工资发放", "", "in", rules) == (3, 95)
    assert match_by_rules("工资发放", "", "out", rules) == (3, 95)


def test_match_by_rules_empty_rules_list_deep3():
    assert match_by_rules("商户", "备注", "out", []) is None


def test_match_by_history_direction_mismatch_returns_none_deep3():
    history = [
        {"counterparty": "商户A", "summary": "", "direction": "in", "category_id": 7},
        {"counterparty": "商户A", "summary": "", "direction": "in", "category_id": 7},
    ]
    assert match_by_history("商户A", "", "out", history) is None


def test_match_by_history_only_summary_exact_no_match_deep3():
    history = [
        {"counterparty": "", "summary": "工资", "direction": "in", "category_id": 1},
        {"counterparty": "", "summary": "工资", "direction": "in", "category_id": 1},
    ]
    assert match_by_history("", "工资", "in", history) == (1, 65)


def test_match_by_history_exact_votes_confidence_scaling_deep3():
    history = [
        {"counterparty": "商户X", "summary": "", "direction": "out", "category_id": 5},
        {"counterparty": "商户X", "summary": "", "direction": "out", "category_id": 5},
        {"counterparty": "商户X", "summary": "", "direction": "out", "category_id": 5},
    ]
    assert match_by_history("商户X", "", "out", history) == (5, 90)


def test_match_by_history_fuzzy_summary_match_deep3():
    history = [
        {"counterparty": "", "summary": "超市购物日常", "direction": "out", "category_id": 4},
        {"counterparty": "", "summary": "超市购物", "direction": "out", "category_id": 4},
    ]
    assert match_by_history("", "超市购物", "out", history) == (4, 65)


def test_match_by_history_empty_history_returns_none_deep3():
    assert match_by_history("商户", "备注", "out", []) is None


def test_match_by_history_whitespace_only_inputs_deep3():
    history = [
        {"counterparty": "商户", "summary": "", "direction": "out", "category_id": 1},
    ]
    assert match_by_history("   ", "\t", "out", history) is None


def test_top_vote_empty_dict_deep3():
    assert _top_vote({}) == (-1, -1)


def test_top_vote_single_entry_deep3():
    assert _top_vote({42: 1}) == (42, 1)


def test_fuzzy_hit_identical_single_char_false_deep3():
    assert _fuzzy_hit("a", "a") is False
    assert _fuzzy_hit("aa", "aa") is True


def test_fuzzy_hit_no_overlap_deep3():
    assert _fuzzy_hit("abcd", "wxyz") is False


def test_suggest_candidates_empty_inputs_deep3():
    assert suggest_candidates("", "", "out", [], []) == []


def test_suggest_candidates_direction_filter_deep3():
    history = [
        {"counterparty": "A", "summary": "", "direction": "in", "category_id": 1},
    ]
    top_categories = [(10, 5), (11, 3)]
    result = suggest_candidates("", "", "out", history, top_categories)
    assert [r[0] for r in result] == [10, 11]
    assert all(r[1] == "同方向常用分类" for r in result)
    assert [r[2] for r in result] == [55, 45]


def test_suggest_candidates_history_over_three_capped_deep3():
    history = []
    for cid in (1, 2, 3, 4, 5):
        history.append({"counterparty": "A", "summary": "", "direction": "out", "category_id": cid})
    result = suggest_candidates("", "", "out", history, [])
    assert len(result) == 3
    assert [r[0] for r in result] == [1, 2, 3]
    assert [r[2] for r in result] == [55, 45, 35]


def test_suggest_candidates_history_ranking_by_count_deep3():
    history = [
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 2},
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
    ]
    result = suggest_candidates("", "", "out", history, [])
    assert result[0][0] == 1
    assert result[1][0] == 2


def test_suggest_candidates_history_and_top_fill_to_three_deep3():
    history = [
        {"counterparty": "A", "summary": "", "direction": "out", "category_id": 1},
    ]
    top_categories = [(2, 5), (3, 4), (4, 3)]
    result = suggest_candidates("", "", "out", history, top_categories)
    assert [r[0] for r in result] == [1, 2, 3]
    assert result[0][1] == "该商户历史多归为此分类"
    assert result[1][1] == "同方向常用分类"
    assert result[2][1] == "同方向常用分类"


def test_detect_transfer_empty_accounts_dict_deep3():
    assert detect_transfer("支付宝", {}) is None


def test_detect_transfer_fuzzy_both_directions_deep3():
    accounts = {1: "招商银行储蓄卡"}
    assert detect_transfer("招商银行", accounts) == 1
    assert detect_transfer("储蓄卡", accounts) == 1


def test_detect_transfer_single_char_counterparty_no_fuzzy_deep3():
    accounts = {1: "支付宝"}
    assert detect_transfer("支", accounts) is None


def test_detect_transfer_accounts_sorted_by_id_deep3():
    accounts = {5: "支付宝", 2: "支付宝"}
    assert detect_transfer("支付宝", accounts) == 2


def test_amount_within_negative_amounts_symmetric_deep3():
    assert amount_within(-100, -150, 50, 0) is True
    assert amount_within(-100, -151, 50, 0) is False


def test_amount_within_pct_uses_max_abs_base_deep3():
    assert amount_within(0, 10, 0, 100) is True
    assert amount_within(0, 11, 0, 10) is False


def test_amount_within_zero_abs_tol_positive_pct_deep3():
    assert amount_within(1000, 1005, 0, 1) is True
    assert amount_within(1000, 1011, 0, 1) is False


def test_amount_within_pct_exact_boundary_deep3():
    assert amount_within(100, 105, 0, 5) is True
    assert amount_within(100, 106, 0, 5) is False


def test_within_date_window_same_date_deep3():
    assert within_date_window("2024-02-29", "2024-02-29", 0) is True


def test_within_date_window_negative_n_days_deep3():
    assert within_date_window("2024-01-10", "2024-01-10", -1) is False


def test_within_date_window_cross_year_deep3():
    assert within_date_window("2023-12-31", "2024-01-01", 1) is True
    assert within_date_window("2023-12-30", "2024-01-02", 2) is False


def test_within_date_window_only_one_invalid_deep3():
    assert within_date_window("bad", "2024-01-10", 5) is False
    assert within_date_window("2024-01-10", "bad", 5) is False


def test_match_by_alias_first_match_wins_deep3():
    aliases = [
        {"alias": "美团", "direction": "out", "category_id": 5},
        {"alias": "美团", "direction": "out", "category_id": 9},
    ]
    assert match_by_alias("美团", "out", aliases) == (5, 85)


def test_match_by_alias_empty_aliases_deep3():
    assert match_by_alias("美团", "out", []) is None


def test_match_by_alias_alias_requires_already_normalized_deep3():
    aliases = [{"alias": "美团外卖", "direction": "out", "category_id": 5}]
    assert match_by_alias("美团外卖", "out", aliases) == (5, 85)
    assert match_by_alias("美团 外卖", "out", aliases) == (5, 85)


def test_detect_transfer_pair_empty_items_deep3():
    assert detect_transfer_pair([], {1: "支付宝"}) == []


def test_detect_transfer_pair_only_outs_no_pairs_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}) == []


def test_detect_transfer_pair_direction_other_ignored_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 3, "direction": "unknown", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}) == [(1, 2)]


def test_detect_transfer_pair_date_window_custom_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 100, "occurred_on": "2024-01-05", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}, date_window_days=3) == []
    assert detect_transfer_pair(items, {1: "支付宝"}, date_window_days=5) == [(1, 2)]


def test_detect_transfer_pair_pct_tolerance_custom_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 1050, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}, abs_tol_cents=0, pct_tol=6) == [(1, 2)]
    assert detect_transfer_pair(items, {1: "支付宝"}, abs_tol_cents=0, pct_tol=0) == []


def test_detect_transfer_pair_counterparty_match_only_on_in_side_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "无关"},
        {"id": 2, "direction": "in", "amount_cents": 500, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}) == [(1, 2)]


def test_detect_transfer_pair_greedy_uses_each_in_once_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 3, "direction": "in", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}) == [(1, 3)]


def test_detect_transfer_pair_amount_tolerance_abs_default_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 1000, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 1100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}, abs_tol_cents=100, pct_tol=0) == [(1, 2)]
    assert detect_transfer_pair(items, {1: "支付宝"}, abs_tol_cents=99, pct_tol=0) == []


def test_detect_transfer_pair_invalid_date_no_pair_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "bad-date", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {1: "支付宝"}) == []


def test_detect_transfer_pair_empty_accounts_no_pair_deep3():
    items = [
        {"id": 1, "direction": "out", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
        {"id": 2, "direction": "in", "amount_cents": 100, "occurred_on": "2024-01-01", "counterparty": "支付宝"},
    ]
    assert detect_transfer_pair(items, {}) == []