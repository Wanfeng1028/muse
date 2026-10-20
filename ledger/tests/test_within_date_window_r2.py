from __future__ import annotations

from ledger.matching import within_date_window


def test_within_date_window_exact_boundary_true() -> None:
    assert within_date_window("2026-01-01", "2026-01-04", 3) is True


def test_within_date_window_over_boundary_false() -> None:
    assert within_date_window("2026-01-01", "2026-01-05", 3) is False


def test_within_date_window_invalid_date_returns_false() -> None:
    assert within_date_window("2026-02-30", "2026-01-01", 60) is False
    assert within_date_window("abc", "2026-01-01", 60) is False
    assert within_date_window("", "", 3) is False


def test_within_date_window_order_independent() -> None:
    assert within_date_window("2026-01-05", "2026-01-01", 4) is True


def test_within_date_window_leap_year() -> None:
    assert within_date_window("2024-02-28", "2024-02-29", 1) is True


def test_within_date_window_cross_year() -> None:
    assert within_date_window("2025-12-31", "2026-01-01", 1) is True


def test_within_date_window_same_day_zero_window() -> None:
    assert within_date_window("2026-06-01", "2026-06-01", 0) is True
