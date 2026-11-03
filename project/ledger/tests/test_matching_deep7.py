"""detect_transfer_pair_cross_batch 的纯函数语义测试。

覆盖跨批次配对、方向顺序、金额/日期/对方名条件、new 侧与 old 侧互斥、
空输入以及默认参数一致性。
"""

from __future__ import annotations

import inspect

from ledger.matching import detect_transfer_pair, detect_transfer_pair_cross_batch

ACCOUNTS = {1: "支付宝", 2: "招商银行"}


def _item(
    item_id: int,
    occurred_on: str,
    amount_cents: int,
    direction: str,
    counterparty: str,
) -> dict:
    """构造一条符合 detect_transfer_pair 形状的条目。"""
    return {
        "id": item_id,
        "occurred_on": occurred_on,
        "amount_cents": amount_cents,
        "direction": direction,
        "counterparty": counterparty,
    }


def test_basic_new_out_old_in():
    """基本跨批次配对：new out + old in 条件满足 -> (out_id, in_id)。"""
    new_items = [_item(1, "2024-01-10", 10000, "out", "支付宝")]
    old_items = [_item(101, "2024-01-11", 10050, "in", "未知对方")]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == [(1, 101)]


def test_reverse_new_in_old_out():
    """反向：new in + old out -> 元组仍为 (out_id, in_id)，out 在前。"""
    new_items = [_item(5, "2024-01-10", 10000, "in", "未知对方")]
    old_items = [_item(205, "2024-01-11", 10050, "out", "支付宝")]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == [(205, 5)]


def test_amount_out_of_tolerance():
    """金额超容差（差 200 分，绝对 100 且超 1%）-> 不配对。"""
    new_items = [_item(1, "2024-01-10", 10000, "out", "支付宝")]
    old_items = [_item(101, "2024-01-10", 10200, "in", "支付宝")]
    result = detect_transfer_pair_cross_batch(
        new_items, old_items, ACCOUNTS, abs_tol_cents=100, pct_tol=1
    )
    assert result == []


def test_date_out_of_window():
    """日期超窗口（相差 4 天，窗口 3 天）-> 不配对。"""
    new_items = [_item(1, "2024-01-10", 10000, "out", "支付宝")]
    old_items = [_item(101, "2024-01-14", 10000, "in", "支付宝")]
    result = detect_transfer_pair_cross_batch(
        new_items, old_items, ACCOUNTS, date_window_days=3
    )
    assert result == []


def test_no_intra_new_or_old_pairing():
    """同批次内不配对：new-new 与 old-old 即便条件满足也不产生配对。"""
    new_items = [
        _item(1, "2024-01-10", 10000, "out", "支付宝"),
        _item(2, "2024-01-10", 10000, "in", "支付宝"),
    ]
    old_items = [
        _item(101, "2024-01-10", 10000, "out", "支付宝"),
        _item(102, "2024-01-10", 10000, "in", "支付宝"),
    ]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    # 跨批次配对：new 的 out 配 old 的 in 得 (1, 102)，
    # new 的 in 配 old 的 out 得 (101, 2)（out 在前）；
    # new-new / old-old 之间无配对。
    assert result == [(1, 102), (101, 2)]


def test_old_side_mutual_exclusion():
    """old 侧互斥：两个 new out 争一个 old in -> 只有 id 小的 new out 配上。"""
    new_items = [
        _item(1, "2024-01-10", 10000, "out", "支付宝"),
        _item(2, "2024-01-10", 10000, "out", "支付宝"),
    ]
    old_items = [_item(101, "2024-01-10", 10000, "in", "支付宝")]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == [(1, 101)]


def test_new_side_mutual_exclusion():
    """new 侧互斥：一个 new out 对应两个 old in -> 只配 id 小的 old in。"""
    new_items = [_item(1, "2024-01-10", 10000, "out", "支付宝")]
    old_items = [
        _item(101, "2024-01-10", 10000, "in", "支付宝"),
        _item(102, "2024-01-10", 10000, "in", "支付宝"),
    ]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == [(1, 101)]


def test_both_counterparties_unmatched():
    """双方 counterparty 都不是自有账户名 -> 不配对。"""
    new_items = [_item(1, "2024-01-10", 10000, "out", "张三")]
    old_items = [_item(101, "2024-01-10", 10000, "in", "李四")]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == []


def test_invalid_date_does_not_raise():
    """非法日期字符串 -> 不配对且不抛异常。"""
    new_items = [_item(1, "not-a-date", 10000, "out", "支付宝")]
    old_items = [_item(101, "2024-01-10", 10000, "in", "支付宝")]
    result = detect_transfer_pair_cross_batch(new_items, old_items, ACCOUNTS)
    assert result == []


def test_pct_tolerance_boundary():
    """百分比容差边界：100000 分差 900（0.9%）配对，差 1100（1.1%）不配对。"""
    new_items = [_item(1, "2024-01-10", 100000, "out", "支付宝")]
    old_ok = [_item(101, "2024-01-10", 100900, "in", "支付宝")]
    old_bad = [_item(102, "2024-01-10", 101100, "in", "支付宝")]
    assert detect_transfer_pair_cross_batch(new_items, old_ok, ACCOUNTS) == [(1, 101)]
    assert detect_transfer_pair_cross_batch(new_items, old_bad, ACCOUNTS) == []


def test_empty_inputs_return_empty():
    """空 new_items 或空 old_items -> 返回 []。"""
    assert detect_transfer_pair_cross_batch([], [], ACCOUNTS) == []
    assert detect_transfer_pair_cross_batch(
        [], [_item(101, "2024-01-10", 10000, "in", "支付宝")], ACCOUNTS
    ) == []
    assert detect_transfer_pair_cross_batch(
        [_item(1, "2024-01-10", 10000, "out", "支付宝")], [], ACCOUNTS
    ) == []


def test_default_params_match_detect_transfer_pair():
    """默认参数与 detect_transfer_pair 一致（100, 1, 3）。"""
    cross = inspect.signature(detect_transfer_pair_cross_batch)
    same = inspect.signature(detect_transfer_pair)
    assert cross.parameters["abs_tol_cents"].default == 100
    assert cross.parameters["pct_tol"].default == 1
    assert cross.parameters["date_window_days"].default == 3
    assert (
        cross.parameters["abs_tol_cents"].default
        == same.parameters["abs_tol_cents"].default
    )
    assert cross.parameters["pct_tol"].default == same.parameters["pct_tol"].default
    assert (
        cross.parameters["date_window_days"].default
        == same.parameters["date_window_days"].default
    )
