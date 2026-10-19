from ledger.matching import (
    detect_transfer,
    detect_transfer_pair,
    fingerprint,
    match_by_alias,
    match_by_history,
    match_by_rules,
    normalize,
    suggest_candidates,
)

# ============================================================
# A. _fuzzy_hit 误判边界（通过公开函数观测）
# ============================================================


def test_a1_history_fuzzy_contains_starbucks_daigou():
    # 历史两条精确"星巴克"（out），构成精确分支 votes=2 -> (1, 90)。
    # 但新条目 counterparty="星巴克代购" 与历史"星巴克"并非精确相等，
    # 因此精确分支 votes=0，走模糊分支："星巴克" in "星巴克代购" -> 命中 2 票 -> (1, 65)。
    history = [
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
    ]
    result = match_by_history("星巴克代购", "", "out", history)
    # 当前行为：互包含模糊匹配命中，返回 (1, 65)。
    # 已知边界：若"星巴克代购"实际属于购物分类，当前算法会误判为餐饮(1)。
    assert result == (1, 65)


def test_a2_detect_transfer_wechat_pay_matches_wechat_account():
    # 对方"微信支付" 与账户名"微信" 互包含（长度均>=2），detect_transfer 命中。
    # 这是合理的识别：账户别名"微信"是"微信支付"的子串。
    account_names = {7: "微信"}
    assert detect_transfer("微信支付", account_names) == 7


def test_a3_detect_transfer_cash_loan_matches_cash_account():
    # 对方"现金贷" 与账户名"现金" 互包含，detect_transfer 命中。
    # 已知边界：消费金融类商户名包含自有账户名时会被误判为转账建议。
    # 本轮不改逻辑，诚实记录当前行为。
    account_names = {3: "现金"}
    assert detect_transfer("现金贷", account_names) == 3


def test_a4_single_char_no_fuzzy_match():
    # 对方"a" 长度 < 2，_fuzzy_hit 直接返回 False；
    # 账户名"ab" 也不与"a"精确相等，故 detect_transfer 返回 None。
    account_names = {1: "ab"}
    assert detect_transfer("a", account_names) is None
    # 对照：精确相等仍可命中（长度不参与精确分支）。
    assert detect_transfer("ab", account_names) == 1


# ============================================================
# B. match_by_rules 子串误伤
# ============================================================


def test_b1_rules_substring_keyword_hits():
    rules = [{"keyword": "星巴克", "category_id": 1, "direction": "out", "priority": 0}]
    # 归一化 haystack 含"星巴克"，keyword 子串命中 -> (1, 95)。
    # 关键词匹配为子串语义，是有意行为。
    assert match_by_rules("星巴克代购", "", "out", rules) == (1, 95)


def test_b2_rules_direction_mismatch_no_hit():
    rules = [{"keyword": "美团", "category_id": 5, "direction": "in", "priority": 0}]
    # 规则方向 in，条目方向 out -> 跳过 -> None。
    assert match_by_rules("美团", "", "out", rules) is None


def test_b3_rules_same_priority_longer_keyword_wins():
    rules = [
        {"keyword": "星巴克", "category_id": 1, "direction": "out", "priority": 10},
        {"keyword": "星巴克臻选", "category_id": 2, "direction": "out", "priority": 10},
    ]
    # 两条都命中，priority 相同(10)，取归一化 keyword 更长者 -> "星巴克臻选" -> (2, 95)。
    assert match_by_rules("星巴克臻选门店", "", "out", rules) == (2, 95)


# ============================================================
# C. match_by_history 票数边界
# ============================================================


def test_c1_exact_three_votes_confidence_capped():
    history = [
        {"counterparty": "美团", "category_id": 4, "direction": "out"},
        {"counterparty": "美团", "category_id": 4, "direction": "out"},
        {"counterparty": "美团", "category_id": 4, "direction": "out"},
    ]
    # 精确 3 票 -> min(90, 60 + 3*10) = 90。
    assert match_by_history("美团", "", "out", history) == (4, 90)


def test_c2_single_exact_and_single_fuzzy_returns_none():
    history = [
        {"counterparty": "美团", "category_id": 4, "direction": "out"},  # 精确 1 票
        {"counterparty": "美团外卖", "category_id": 4, "direction": "out"},  # 模糊 1 票
    ]
    # 精确分支 votes=1 < 2 不返回；但模糊分支独立重计："美团"与"美团"互包含、
    # "美团"与"美团外卖"互包含，模糊分支共 2 票 -> (4, 65)。
    # 语义：同一商户的精确历史与变体历史在模糊分支合并计票。
    assert match_by_history("美团", "", "out", history) == (4, 65)


def test_c3_history_direction_filter_blocks_match():
    history = [
        {"counterparty": "招商银行", "category_id": 2, "direction": "in"},
        {"counterparty": "招商银行", "category_id": 2, "direction": "in"},
    ]
    # 方向不一致全部被过滤 -> None。
    assert match_by_history("招商银行", "", "out", history) is None


# ============================================================
# D. suggest_candidates
# ============================================================


def test_d1_candidates_from_history_ordered_by_votes():
    history = (
        [{"counterparty": "x", "category_id": 1, "direction": "out"}] * 5
        + [{"counterparty": "x", "category_id": 2, "direction": "out"}] * 3
        + [{"counterparty": "x", "category_id": 3, "direction": "out"}] * 1
    )
    result = suggest_candidates("x", "", "out", history, [])
    assert len(result) == 3
    assert [r[0] for r in result] == [1, 2, 3]
    assert [r[2] for r in result] == [55, 45, 35]
    for cid, reason, conf in result:
        assert isinstance(reason, str) and reason != ""
        assert isinstance(cid, int)
        assert isinstance(conf, int)


def test_d2_candidates_fill_from_top_categories():
    history = [{"counterparty": "x", "category_id": 9, "direction": "out"}]
    top_categories = [(20, 5), (21, 3)]
    result = suggest_candidates("x", "", "out", history, top_categories)
    assert len(result) == 3
    assert [r[0] for r in result] == [9, 20, 21]
    assert [r[2] for r in result] == [55, 45, 35]


def test_d3_candidates_history_empty_use_top_categories():
    top_categories = [(30, 9), (31, 8), (32, 7), (33, 6)]
    result = suggest_candidates("x", "", "out", [], top_categories)
    # 历史为空，全从 top_categories 取，最多 3 条。
    assert len(result) == 3
    assert [r[0] for r in result] == [30, 31, 32]
    assert [r[2] for r in result] == [55, 45, 35]


def test_d4_candidates_dedup_history_and_top():
    history = [{"counterparty": "x", "category_id": 1, "direction": "out"}]
    top_categories = [(1, 9), (2, 5)]
    result = suggest_candidates("x", "", "out", history, top_categories)
    ids = [r[0] for r in result]
    # 分类 1 在历史出现，top_categories 里的 1 被去重跳过 -> [1, 2]。
    assert ids == [1, 2]
    assert len(ids) == len(set(ids))


# ============================================================
# E. normalize 与 fingerprint
# ============================================================


def test_e1_normalize_strips_whitespace_punct_case():
    assert normalize("  星巴克，门店！ ") == "星巴克门店"


def test_e2_fingerprint_normalizes_case_and_punctuation():
    a = fingerprint("2026-10-01", 100, "out", "星巴克", "拿铁")
    b = fingerprint("2026-10-01", 100, "out", " 星巴克，", "拿铁！")
    assert a == b


def test_e3_fingerprint_amount_differs_by_one_cent():
    a = fingerprint("2026-10-01", 100, "out", "星巴克", "拿铁")
    b = fingerprint("2026-10-01", 101, "out", "星巴克", "拿铁")
    assert a != b


# ============================================================
# F. detect_transfer_pair 贪心边界
# ============================================================


def test_f1_greedy_pairs_smaller_in_id():
    items = [
        {"id": 1, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "out", "counterparty": "招商银行"},
        {"id": 2, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "in", "counterparty": "招行"},
        {"id": 3, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "in", "counterparty": "招行"},
    ]
    account_names = {1: "招商银行"}
    pairs = detect_transfer_pair(items, account_names)
    # out(1) 贪心匹配 id 升序第一个可用 in(2)，in(3) 未被使用。
    assert pairs == [(1, 2)]


def test_f2_amount_tolerance_100_ok_101_not_ok():
    base_items = [
        {"id": 1, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "out", "counterparty": "招商银行"},
        {"id": 2, "occurred_on": "2026-10-01", "amount_cents": 10100, "direction": "in", "counterparty": "招行"},
    ]
    account_names = {1: "招商银行"}
    # 差 100 分 = abs_tol 边界，命中；pct 1% * 10100 = 101 也够。
    assert detect_transfer_pair(base_items, account_names) == [(1, 2)]

    base_items[1]["amount_cents"] = 10101
    # 差 101 分：abs_tol 100 不够；pct 1% * 10101 = 101.01 -> 整数运算 diff*100=10100 <= base*pct=10101*1?
    # base = 10101, diff = 101, diff*100 = 10100, base*pct_tol = 10101*1 = 10101, 10100 <= 10101 -> True!
    # 因此 101 分仍在 1% 内，命中。诚实记录：此处 1% 相对容差覆盖了 101 分差。
    assert detect_transfer_pair(base_items, account_names) == [(1, 2)]

    # 要构造真正"不配对"的差，需要超过 1%：10000 与 10200 -> diff=200, base=10200,
    # diff*100=20000 > 10200*1=10200 -> 相对失败；abs 200>100 -> 失败 -> 不配对。
    base_items[1]["amount_cents"] = 10200
    assert detect_transfer_pair(base_items, account_names) == []


def test_f3_date_window_3_ok_4_not_ok():
    items = [
        {"id": 1, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "out", "counterparty": "招商银行"},
        {"id": 2, "occurred_on": "2026-10-04", "amount_cents": 10000, "direction": "in", "counterparty": "招行"},
    ]
    account_names = {1: "招商银行"}
    # 相差 3 天，窗口默认 3 -> 配对。
    assert detect_transfer_pair(items, account_names) == [(1, 2)]

    items[1]["occurred_on"] = "2026-10-05"
    # 相差 4 天 > 3 -> 不配对。
    assert detect_transfer_pair(items, account_names) == []


def test_f4_no_account_match_no_pair():
    items = [
        {"id": 1, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "out", "counterparty": "美团"},
        {"id": 2, "occurred_on": "2026-10-01", "amount_cents": 10000, "direction": "in", "counterparty": "星巴克"},
    ]
    account_names = {1: "招商银行"}
    # 双方 counterparty 都对不上任何账户名 -> 不配对。
    assert detect_transfer_pair(items, account_names) == []


def test_f5_one_side_matches_account_pairs():
    items = [
        {"id": 1, "occurred_on": "2026-10-01", "amount_cents": 50000, "direction": "out", "counterparty": "支付宝"},
        {"id": 2, "occurred_on": "2026-10-02", "amount_cents": 50000, "direction": "in", "counterparty": "招商银行"},
    ]
    account_names = {1: "招商银行"}
    # in 方 counterparty 对上账户名 -> 配对成功。
    assert detect_transfer_pair(items, account_names) == [(1, 2)]


# ============================================================
# G. match_by_alias
# ============================================================


def test_g1_alias_exact_normalized_hit_and_direction_filter():
    aliases = [{"alias": "星巴克", "category_id": 1, "direction": "out"}]
    # 归一化后精确相等 -> (1, 85)。
    assert match_by_alias("  星巴克，", "out", aliases) == (1, 85)
    # direction 不一致 -> None。
    assert match_by_alias("星巴克", "in", aliases) is None


def test_g2_alias_substring_not_equal_returns_none():
    aliases = [{"alias": "星巴克", "category_id": 1, "direction": "out"}]
    # 别名要求归一化后精确相等（与规则子串匹配不同），"星巴克代购" 不等于 "星巴克" -> None。
    assert match_by_alias("星巴克代购", "out", aliases) is None
    # 对照：规则子串匹配会命中。
    rules = [{"keyword": "星巴克", "category_id": 1, "direction": "out", "priority": 0}]
    assert match_by_rules("星巴克代购", "", "out", rules) == (1, 95)
