from __future__ import annotations

from ledger.matching import match_by_alias


def test_exact_alias_after_normalization() -> None:
    aliases = [{"alias": "星巴克", "category_id": 12, "direction": "out"}]
    assert match_by_alias("  星巴克，", "out", aliases) == (12, 85)


def test_direction_mismatch_returns_none() -> None:
    aliases = [{"alias": "星巴克", "category_id": 12, "direction": "in"}]
    assert match_by_alias("星巴克", "out", aliases) is None


def test_empty_counterparty_returns_none() -> None:
    aliases = [{"alias": "星巴克", "category_id": 12, "direction": "out"}]
    assert match_by_alias("", "out", aliases) is None
    assert match_by_alias("   ", "out", aliases) is None


def test_empty_aliases_returns_none() -> None:
    assert match_by_alias("星巴克", "out", []) is None


def test_skips_first_direction_mismatch_then_hits_second() -> None:
    aliases = [
        {"alias": "星巴克", "category_id": 12, "direction": "in"},
        {"alias": "星巴克", "category_id": 34, "direction": "out"},
    ]
    assert match_by_alias(" 星巴克，", "out", aliases) == (34, 85)
