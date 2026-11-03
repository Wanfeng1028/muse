from __future__ import annotations

from ledger.matching import match_by_history


def _entry(counterparty: str, summary: str, category_id: int, direction: str) -> dict:
    return {
        "counterparty": counterparty,
        "summary": summary,
        "category_id": category_id,
        "direction": direction,
    }


def test_exact_single_vote_returns_none() -> None:
    history = [
        _entry("星巴克", "咖啡", 3, "out"),
    ]
    assert match_by_history("星巴克", "咖啡", "out", history) is None


def test_exact_two_votes_returns_confidence_80() -> None:
    history = [
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
    ]
    assert match_by_history("星巴克", "咖啡", "out", history) == (3, 80)


def test_exact_five_votes_caps_confidence_at_90() -> None:
    history = [
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
    ]
    assert match_by_history("星巴克", "咖啡", "out", history) == (3, 90)


def test_fuzzy_two_votes_returns_confidence_65() -> None:
    history = [
        _entry("星巴克咖啡", "拿铁", 3, "out"),
        _entry("星巴克咖啡", "拿铁", 3, "out"),
    ]
    assert match_by_history("星巴克", "拿铁", "out", history) == (3, 65)


def test_tie_breaks_to_smaller_category_id() -> None:
    history = [
        _entry("星巴克", "咖啡", 7, "out"),
        _entry("星巴克", "咖啡", 7, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
    ]
    assert match_by_history("星巴克", "咖啡", "out", history) == (3, 80)


def test_direction_filter_excludes_other_direction() -> None:
    history = [
        _entry("星巴克", "咖啡", 3, "in"),
        _entry("星巴克", "咖啡", 3, "in"),
    ]
    assert match_by_history("星巴克", "咖啡", "out", history) is None


def test_empty_counterparty_and_summary_returns_none() -> None:
    history = [
        _entry("星巴克", "咖啡", 3, "out"),
        _entry("星巴克", "咖啡", 3, "out"),
    ]
    assert match_by_history("", "", "out", history) is None
