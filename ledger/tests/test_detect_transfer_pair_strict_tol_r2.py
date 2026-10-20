from __future__ import annotations

from ledger.matching import detect_transfer_pair


def _make_item(
    item_id: int,
    occurred_on: str,
    amount_cents: int,
    direction: str,
    counterparty: str,
) -> dict:
    return {
        "id": item_id,
        "occurred_on": occurred_on,
        "amount_cents": amount_cents,
        "direction": direction,
        "counterparty": counterparty,
    }


ACCOUNTS = {1: "招商银行"}


def test_exact_amount_pairs_with_zero_tolerances() -> None:
    items = [
        _make_item(1, "2026-01-15", 50000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 50000, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0,
        date_window_days=3,
    )
    assert result == [(1, 2)]


def test_one_cent_diff_fails_with_zero_tolerances() -> None:
    items = [
        _make_item(1, "2026-01-15", 50000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 50001, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0,
        date_window_days=3,
    )
    assert result == []


def test_one_cent_diff_fails_abs_zero_pct_zero_only_absolute() -> None:
    items = [
        _make_item(1, "2026-01-15", 100000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 100001, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0,
        date_window_days=3,
    )
    assert result == []


def test_one_cent_diff_pairs_with_abs_tol_one() -> None:
    items = [
        _make_item(1, "2026-01-15", 50000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 50001, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=1,
        pct_tol=0,
        date_window_days=3,
    )
    assert result == [(1, 2)]


def test_same_day_pairs_with_date_window_zero() -> None:
    items = [
        _make_item(1, "2026-01-15", 50000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 50000, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0,
        date_window_days=0,
    )
    assert result == [(1, 2)]


def test_one_day_apart_fails_with_date_window_zero() -> None:
    items = [
        _make_item(1, "2026-01-15", 50000, "out", "招商银行"),
        _make_item(2, "2026-01-16", 50000, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0,
        date_window_days=0,
    )
    assert result == []


def test_half_percent_diff_pairs_with_pct_tol_half() -> None:
    items = [
        _make_item(1, "2026-01-15", 10000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 10050, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0.5,
        date_window_days=3,
    )
    assert result == [(1, 2)]


def test_above_half_percent_diff_fails_with_pct_tol_half() -> None:
    items = [
        _make_item(1, "2026-01-15", 10000, "out", "招商银行"),
        _make_item(2, "2026-01-15", 10051, "in", "招商银行"),
    ]
    result = detect_transfer_pair(
        items,
        ACCOUNTS,
        abs_tol_cents=0,
        pct_tol=0.5,
        date_window_days=3,
    )
    assert result == []
