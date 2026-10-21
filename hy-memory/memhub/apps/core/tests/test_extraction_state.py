"""Three extraction states: extracted, outside the window, or still queued.

Without the middle state, "not yet a memory" reads the same whether the system
has decided not to extract automatically or has simply not reached the item.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from one_memory.memory_queue import (
    ExtractionState,
    ExtractionWindowPreset,
    extraction_window_for,
    resolve_extraction_state,
)
from one_memory.memory_tasks import MemoryTaskStatus


def test_resolve_marks_completed_work_as_extracted() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=MemoryTaskStatus.COMPLETED,
            at=now - timedelta(days=10),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.EXTRACTED
    )


def test_resolve_marks_deferred_tasks_as_outside_window() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW,
            at=now - timedelta(days=200),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.OUTSIDE_WINDOW
    )


def test_resolve_marks_pending_inside_window_as_queued() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=MemoryTaskStatus.PENDING,
            at=now - timedelta(days=10),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.QUEUED
    )


def test_resolve_marks_permission_wait_as_queued() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=MemoryTaskStatus.WAITING_FOR_PERMISSION,
            at=now - timedelta(days=10),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.QUEUED
    )


def test_resolve_marks_unknown_as_queued_for_inquiry() -> None:
    """Unknown is not an extraction window decision.

    The task may already have reached HY; it is waiting for an outcome inquiry,
    not outside the extraction window. Falling through to the window check
    would tell the UI that an old unknown task was never going to be extracted.
    """
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=MemoryTaskStatus.UNKNOWN,
            at=now - timedelta(days=200),
            imported_at=now - timedelta(days=200),
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.QUEUED
    )


def test_resolve_without_a_task_uses_the_window() -> None:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    assert (
        resolve_extraction_state(
            task_status=None,
            at=now - timedelta(days=200),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.OUTSIDE_WINDOW
    )
    assert (
        resolve_extraction_state(
            task_status=None,
            at=now - timedelta(days=10),
            imported_at=now,
            workspace="/Users/me/project",
            now=now,
        )
        is ExtractionState.QUEUED
    )


def test_window_presets_match_the_product_choices() -> None:
    assert timedelta(days=90) == extraction_window_for(ExtractionWindowPreset.THREE_MONTHS)
    assert timedelta(days=180) == extraction_window_for(ExtractionWindowPreset.SIX_MONTHS)
    assert timedelta(days=365) == extraction_window_for(ExtractionWindowPreset.ONE_YEAR)
    assert extraction_window_for(ExtractionWindowPreset.ALL) is None
