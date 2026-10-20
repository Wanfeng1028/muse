from __future__ import annotations

from ledger.matching import detect_transfer_pair


def _item(id: int, occurred_on: str, amount_cents: int, direction: str, counterparty: str) -> dict:
    return {
        "id": id,
        "occurred_on": occurred_on,
        "amount_cents": amount_cents,
        "direction": direction,
        "counterparty": counterparty,
    }


def test_one_out_two_ins_picks_lowest_in_id() -> None:
    items = [
        _item(10, "2026-01-15", 5000, "out", "招商银行"),
        _item(20, "2026-01-16", 5000, "in", "微信钱包"),
        _item(21, "2026-01-16", 5000, "in", "招商银行"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == [(10, 20)]
    assert len(result) == 1


def test_two_outs_one_in_lowest_out_id_wins() -> None:
    items = [
        _item(30, "2026-01-15", 8000, "out", "招商银行"),
        _item(31, "2026-01-15", 8000, "out", "微信钱包"),
        _item(40, "2026-01-16", 8000, "in", "招商银行"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == [(30, 40)]
    assert len(result) == 1


def test_in_consumed_by_first_out_excludes_second_out() -> None:
    items = [
        _item(1, "2026-01-15", 6000, "out", "招商银行"),
        _item(2, "2026-01-15", 6000, "out", "招商银行"),
        _item(3, "2026-01-16", 6000, "in", "微信钱包"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == [(1, 3)]
    assert len(result) == 1


def test_both_counterparties_unmatched_returns_empty() -> None:
    items = [
        _item(5, "2026-01-15", 4000, "out", "张三"),
        _item(6, "2026-01-15", 4000, "in", "李四"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == []


def test_one_side_matched_is_enough() -> None:
    items = [
        _item(7, "2026-01-15", 9000, "out", "招商银行"),
        _item(8, "2026-01-15", 9000, "in", "陌生人"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == [(7, 8)]


def test_amount_diff_one_cent_and_three_day_window() -> None:
    items = [
        _item(11, "2026-01-15", 10000, "out", "招商银行"),
        _item(12, "2026-01-18", 10001, "in", "微信钱包"),
    ]
    result = detect_transfer_pair(items, {1: "招商银行", 2: "微信钱包"})
    assert result == [(11, 12)]
