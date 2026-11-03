import datetime

from ledger.matching import (
    _fuzzy_hit,
    _top_vote,
    amount_within,
    detect_transfer,
    detect_transfer_pair,
    match_by_alias,
    match_by_history,
    match_by_rules,
    normalize,
    suggest_candidates,
    within_date_window,
)


# ---------- 1. 规则优先级冲突 ----------

def test_rules_priority_higher_wins():
    rules = [
        {"keyword": "淘宝", "category_id": 10, "priority": 1},
        {"keyword": "商城", "category_id": 20, "priority": 5},
    ]
    result = match_by_rules("淘宝商城", "", "out", rules)
    assert result == (20, 95)


def test_rules_priority_tie_longer_keyword_wins():
    rules = [
        {"keyword": "淘宝", "category_id": 10, "priority": 3},
        {"keyword": "淘宝商城旗舰店", "category_id": 20, "priority": 3},
    ]
    result = match_by_rules("淘宝商城旗舰店", "", "out", rules)
    assert result == (20, 95)


def test_rules_priority_tie_longer_keyword_wins_reverse_order():
    rules = [
        {"keyword": "淘宝商城旗舰店", "category_id": 20, "priority": 3},
        {"keyword": "淘宝", "category_id": 10, "priority": 3},
    ]
    result = match_by_rules("淘宝商城旗舰店", "", "out", rules)
    assert result == (20, 95)


# ---------- 2. direction 过滤 ----------

def test_rules_direction_mismatch_no_hit():
    rules = [{"keyword": "工资", "category_id": 30, "direction": "in"}]
    assert match_by_rules("工资发放", "", "out", rules) is None


def test_rules_direction_any_matches_both():
    rules = [{"keyword": "超市", "category_id": 40, "direction": "any"}]
    assert match_by_rules("超市购物", "", "in", rules) == (40, 95)
    assert match_by_rules("超市购物", "", "out", rules) == (40, 95)


def test_rules_direction_explicit_match():
    rules = [{"keyword": "退款", "category_id": 50, "direction": "in"}]
    assert match_by_rules("退款", "", "in", rules) == (50, 95)


# ---------- 3. 空 keyword / 空 haystack ----------

def test_rules_empty_keyword_skipped():
    rules = [
        {"keyword": "", "category_id": 1, "priority": 99},
        {"keyword": "   ", "category_id": 2, "priority": 99},
        {"keyword": "真实", "category_id": 3, "priority": 1},
    ]
    result = match_by_rules("真实交易", "", "out", rules)
    assert result == (3, 95)


def test_rules_all_punctuation_haystack_returns_none():
    rules = [{"keyword": "abc", "category_id": 1}]
    assert match_by_rules("，。！？", "、；：", "out", rules) is None


# ---------- 4. normalize ----------

def test_normalize_strips_punct_and_lowercases():
    assert normalize(" 淘宝商城，旗舰店！ ") == "淘宝商城旗舰店"


def test_normalize_removes_only_listed_punctuation():
    # 全角逗号、句号、感叹号在列表中，会被去掉
    assert normalize("a，b。c！d") == "abcd"
    # 星号不在 _PUNCTUATION 列表中，应保留
    assert normalize("a*b") == "a*b"
    # 井号不在列表中
    assert normalize("a#b") == "a#b"


# ---------- 5. 历史精确匹配 ----------

def test_history_exact_two_votes_hits():
    history = [
        {"direction": "out", "counterparty": "星巴克", "category_id": 7},
        {"direction": "out", "counterparty": "星巴克", "category_id": 7},
    ]
    result = match_by_history("星巴克", "", "out", history)
    assert result == (7, 80)


def test_history_exact_one_vote_no_hit():
    history = [
        {"direction": "out", "counterparty": "星巴克", "category_id": 7},
    ]
    assert match_by_history("星巴克", "", "out", history) is None


def test_history_exact_direction_mismatch_not_counted():
    history = [
        {"direction": "in", "counterparty": "星巴克", "category_id": 7},
        {"direction": "in", "counterparty": "星巴克", "category_id": 7},
    ]
    assert match_by_history("星巴克", "", "out", history) is None


def test_history_exact_confidence_capped_at_90():
    history = [
        {"direction": "out", "counterparty": "商户", "category_id": 9},
        {"direction": "out", "counterparty": "商户", "category_id": 9},
        {"direction": "out", "counterparty": "商户", "category_id": 9},
        {"direction": "out", "counterparty": "商户", "category_id": 9},
    ]
    # 60 + 4*10 = 100 -> min(90, 100) = 90
    result = match_by_history("商户", "", "out", history)
    assert result == (9, 90)


# ---------- 6. 历史模糊匹配 ----------

def test_fuzzy_hit_short_string_false():
    assert _fuzzy_hit("a", "abcdef") is False
    assert _fuzzy_hit("ab", "c") is False
    assert _fuzzy_hit("", "") is False


def test_history_fuzzy_mutual_containment_hits():
    history = [
        {"direction": "out", "counterparty": "星巴克咖啡", "category_id": 11},
        {"direction": "out", "counterparty": "星巴克咖啡", "category_id": 11},
    ]
    result = match_by_history("星巴克", "", "out", history)
    assert result == (11, 65)


def test_history_fuzzy_one_vote_no_hit():
    history = [
        {"direction": "out", "counterparty": "星巴克咖啡", "category_id": 11},
    ]
    assert match_by_history("星巴克", "", "out", history) is None


# ---------- 7. 投票并列 ----------

def test_top_vote_tie_smaller_id():
    assert _top_vote({5: 3, 2: 3, 9: 1}) == (2, 3)


def test_top_vote_clear_winner():
    assert _top_vote({5: 1, 2: 4}) == (2, 4)


# ---------- 8. suggest_candidates ----------

def test_suggest_candidates_max_three():
    history = [
        {"direction": "out", "category_id": 1},
        {"direction": "out", "category_id": 2},
        {"direction": "out", "category_id": 3},
        {"direction": "out", "category_id": 4},
    ]
    top_categories = [(10, 100), (11, 90), (12, 80)]
    result = suggest_candidates("x", "", "out", history, top_categories)
    assert len(result) == 3


def test_suggest_candidates_no_duplicate_categories():
    history = [
        {"direction": "out", "category_id": 1},
        {"direction": "out", "category_id": 1},
    ]
    top_categories = [(1, 100), (2, 90)]
    result = suggest_candidates("x", "", "out", history, top_categories)
    ids = [r[0] for r in result]
    assert ids == [1, 2]


def test_suggest_candidates_confidence_sequence():
    history = [
        {"direction": "out", "category_id": 1},
    ]
    top_categories = [(2, 100), (3, 90)]
    result = suggest_candidates("x", "", "out", history, top_categories)
    assert [r[2] for r in result] == [55, 45, 35]


def test_suggest_candidates_empty_history_uses_top():
    top_categories = [(10, 100), (11, 90)]
    result = suggest_candidates("x", "", "out", [], top_categories)
    assert result == [
        (10, "同方向常用分类", 55),
        (11, "同方向常用分类", 45),
    ]


# ---------- 9. detect_transfer ----------

def test_detect_transfer_exact_name():
    accounts = {1: "招商银行", 2: "工商银行"}
    assert detect_transfer("招商银行", accounts) == 1


def test_detect_transfer_fuzzy_containment():
    accounts = {1: "招商银行储蓄卡"}
    assert detect_transfer("招商银行", accounts) == 1


def test_detect_transfer_empty_counterparty_none():
    accounts = {1: "招商银行"}
    assert detect_transfer("", accounts) is None
    assert detect_transfer("   ", accounts) is None


def test_detect_transfer_multiple_accounts_sorted_by_id():
    accounts = {5: "招商银行", 2: "招商银行"}
    assert detect_transfer("招商银行", accounts) == 2


# ---------- 10. amount_within ----------

def test_amount_within_abs_tol_boundary():
    assert amount_within(1000, 1100, 100, 0) is True
    assert amount_within(1000, 1101, 100, 0) is False


def test_amount_within_pct_tol_zero_only_abs():
    assert amount_within(1000, 2000, 0, 0) is False
    assert amount_within(1000, 2000, 0, -1) is False


def test_amount_within_both_zero():
    assert amount_within(0, 0, 0, 0) is True


def test_amount_within_pct_boundary_integer_math():
    # diff=1, base=100 -> 1*100=100 <= 100*1=100 -> True (刚好边界内)
    assert amount_within(100, 101, 0, 1) is True
    # diff=2, base=100 -> 2*100=200 <= 100 -> False
    assert amount_within(100, 102, 0, 1) is False


# ---------- 11. within_date_window ----------

def test_within_date_window_exact_n_days():
    assert within_date_window("2024-01-01", "2024-01-04", 3) is True


def test_within_date_window_n_plus_one_false():
    assert within_date_window("2024-01-01", "2024-01-05", 3) is False


def test_within_date_window_invalid_date_false():
    assert within_date_window("not-a-date", "2024-01-01", 3) is False
    assert within_date_window("2024-01-01", "2024-13-01", 3) is False


# ---------- 12. match_by_alias ----------

def test_match_by_alias_exact_hit():
    aliases = [{"alias": "星巴克", "category_id": 7, "direction": "out"}]
    assert match_by_alias("星巴克", "out", aliases) == (7, 85)


def test_match_by_alias_direction_mismatch_skip():
    aliases = [{"alias": "星巴克", "category_id": 7, "direction": "in"}]
    assert match_by_alias("星巴克", "out", aliases) is None


def test_match_by_alias_not_normalized_input():
    aliases = [{"alias": "星巴克", "category_id": 7, "direction": "out"}]
    # 输入带标点空格，normalize 后应命中
    assert match_by_alias(" 星巴克！ ", "out", aliases) == (7, 85)


# ---------- 13. detect_transfer_pair ----------

def _mk_item(item_id, occurred_on, amount_cents, direction, counterparty):
    return {
        "id": item_id,
        "occurred_on": occurred_on,
        "amount_cents": amount_cents,
        "direction": direction,
        "counterparty": counterparty,
    }


def test_detect_transfer_pair_success():
    items = [
        _mk_item(1, "2024-01-01", 10000, "out", "招商银行"),
        _mk_item(2, "2024-01-02", 10000, "in", "某商户"),
    ]
    accounts = {1: "招商银行"}
    assert detect_transfer_pair(items, accounts) == [(1, 2)]


def test_detect_transfer_pair_amount_mismatch():
    items = [
        _mk_item(1, "2024-01-01", 10000, "out", "招商银行"),
        _mk_item(2, "2024-01-02", 50000, "in", "某商户"),
    ]
    accounts = {1: "招商银行"}
    assert detect_transfer_pair(items, accounts, abs_tol_cents=100, pct_tol=1) == []


def test_detect_transfer_pair_date_out_of_window():
    items = [
        _mk_item(1, "2024-01-01", 10000, "out", "招商银行"),
        _mk_item(2, "2024-02-01", 10000, "in", "某商户"),
    ]
    accounts = {1: "招商银行"}
    assert detect_transfer_pair(items, accounts, date_window_days=3) == []


def test_detect_transfer_pair_no_account_match():
    items = [
        _mk_item(1, "2024-01-01", 10000, "out", "某商户A"),
        _mk_item(2, "2024-01-02", 10000, "in", "某商户B"),
    ]
    accounts = {1: "招商银行"}
    assert detect_transfer_pair(items, accounts) == []


def test_detect_transfer_pair_each_item_used_once():
    items = [
        _mk_item(1, "2024-01-01", 10000, "out", "招商银行"),
        _mk_item(2, "2024-01-01", 10000, "out", "招商银行"),
        _mk_item(3, "2024-01-02", 10000, "in", "某商户"),
    ]
    accounts = {1: "招商银行"}
    result = detect_transfer_pair(items, accounts)
    assert result == [(1, 3)]


# ---------- 14. 集成：三路皆 None 的侦探候选 ----------

def test_detective_candidate_all_routes_none():
    counterparty = "神秘商户"
    summary = "神秘消费"
    direction = "out"
    rules = [{"keyword": "淘宝", "category_id": 1}]
    history = [
        {"direction": "out", "counterparty": "其他商户", "category_id": 2},
    ]
    aliases = [{"alias": "已登记别名", "category_id": 3, "direction": "out"}]

    assert match_by_rules(counterparty, summary, direction, rules) is None
    assert match_by_history(counterparty, summary, direction, history) is None
    assert match_by_alias(counterparty, direction, aliases) is None

    candidates = suggest_candidates(
        counterparty, summary, direction, history=[], top_categories=[]
    )
    assert candidates == []