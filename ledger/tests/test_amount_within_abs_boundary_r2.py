from __future__ import annotations

from ledger.matching import amount_within


def test_diff_equals_abs_tol_is_within() -> None:
    assert amount_within(100, 101, 1, 0) is True


def test_diff_exceeds_abs_tol_and_pct_fails() -> None:
    assert amount_within(100, 102, 1, 0) is False


def test_both_zero_with_zero_tol_is_within() -> None:
    assert amount_within(0, 0, 0, 0) is True


def test_both_zero_with_nonzero_abs_tol_is_within() -> None:
    assert amount_within(0, 0, 5, 0) is True


def test_equal_amounts_zero_tol_is_within() -> None:
    assert amount_within(5000, 5000, 0, 0) is True


def test_one_cent_diff_with_one_cent_tol_is_within() -> None:
    assert amount_within(10000, 9999, 1, 0) is True
    assert amount_within(9999, 10000, 1, 0) is True
    assert amount_within(10000, 9999, 0, 0) is False
