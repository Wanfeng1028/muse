from __future__ import annotations

import re

from ledger.matching import fingerprint


def test_fingerprint_stable_across_calls() -> None:
    first = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    second = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    assert first == second


def test_fingerprint_counterparty_punctuation_normalized() -> None:
    a = fingerprint("2026-01-01", 10000, "out", "招商银行，", "买菜")
    b = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    assert a == b


def test_fingerprint_differs_on_amount() -> None:
    a = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    b = fingerprint("2026-01-01", 10001, "out", "招商银行", "买菜")
    assert a != b


def test_fingerprint_differs_on_direction() -> None:
    a = fingerprint("2026-01-01", 10000, "in", "招商银行", "买菜")
    b = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    assert a != b


def test_fingerprint_differs_on_date() -> None:
    a = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    b = fingerprint("2026-01-02", 10000, "out", "招商银行", "买菜")
    assert a != b


def test_fingerprint_is_32_lowercase_hex() -> None:
    value = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    assert len(value) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", value) is not None


def test_fingerprint_differs_on_summary() -> None:
    a = fingerprint("2026-01-01", 10000, "out", "招商银行", "")
    b = fingerprint("2026-01-01", 10000, "out", "招商银行", "买菜")
    assert a != b
