"""Extraction window: outside it, evidence stays searchable and out of the queue.

The 675-item backlog came from treating every imported chat as extractable.
A 90-day window keeps cold start short without dropping the verbatim: older
evidence is imported, stored, and searchable, and simply not classified into
QueuedWork until the user widens the window or asks for it by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from one_memory.memory_queue import (
    EXTRACTION_WINDOW,
    classify,
    within_extraction_window,
)


def test_extraction_window_defaults_to_ninety_days() -> None:
    assert timedelta(days=90) == EXTRACTION_WINDOW


def test_evidence_older_than_the_window_is_outside() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    old = now - timedelta(days=91)
    assert within_extraction_window(old, now=now) is False
    assert within_extraction_window(now - timedelta(days=89), now=now) is True


def test_naive_now_is_normalized_to_utc() -> None:
    """The window comparison must not crash on a naive caller clock.

    Evidence timestamps already fall back to UTC, and the caller clock is
    another input at the same boundary. Treating a naive clock as UTC keeps
    classification deterministic instead of raising a tz-aware/naive
    TypeError deep in the extraction path.
    """
    aware_now = datetime(2026, 9, 9, tzinfo=UTC)
    naive_now = aware_now.replace(tzinfo=None)

    assert within_extraction_window(aware_now - timedelta(days=89), now=naive_now) is True
    assert within_extraction_window(aware_now - timedelta(days=91), now=naive_now) is False


def test_classify_naive_now_is_normalized_to_utc() -> None:
    """A naive caller clock must not crash the freshness classification."""
    aware_now = datetime(2026, 9, 9, tzinfo=UTC)
    naive_now = aware_now.replace(tzinfo=None)

    work = classify(
        "fresh-chat",
        at=aware_now - timedelta(hours=1),
        imported_at=aware_now,
        workspace="/Users/me/project",
        length=40,
        now=naive_now,
    )

    assert work is not None
    assert work.fresh is True


def test_classify_drops_work_outside_the_window() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    work = classify(
        "old-chat",
        at=now - timedelta(days=120),
        imported_at=now,
        workspace="/Users/me/project",
        length=40,
        now=now,
    )
    assert work is None


def test_classify_keeps_work_inside_the_window() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    work = classify(
        "recent-chat",
        at=now - timedelta(days=30),
        imported_at=now,
        workspace="/Users/me/project",
        length=40,
        now=now,
    )
    assert work is not None
    assert work.task_id == "recent-chat"
    assert work.fresh is False


def test_profile_shaped_evidence_is_exempt_from_the_window() -> None:
    # all_apps (no workspace) is the profile-shaped kind. Exempting it keeps
    # cold-start profile memories from reflecting only the last three months.
    now = datetime(2026, 9, 9, tzinfo=UTC)
    work = classify(
        "old-profile",
        at=now - timedelta(days=400),
        imported_at=now,
        workspace=None,
        length=40,
        now=now,
    )
    assert work is not None
    assert work.all_apps is True
