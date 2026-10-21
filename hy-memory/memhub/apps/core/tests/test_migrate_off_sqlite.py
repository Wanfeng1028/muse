"""A1-06: the migration is only done when reconciliation agrees.

A copy that loses rows looks identical to one that succeeds, so these tests
centre on reconciliation rather than on the copy itself.
"""

from __future__ import annotations

from one_memory.memory_server.migrate_off_sqlite import (
    TABLE_ORDER,
    MigrationProgress,
    Preflight,
    TableCounts,
    may_cutover,
    migration_plan,
    preflight_verdict,
    reconcile,
    resume_from,
)


def _ok_preflight() -> Preflight:
    return Preflight(sqlite_bytes=100, free_bytes=1000, target_empty=True, target_schema_version=0)


def test_preflight_refuses_a_non_empty_target() -> None:
    """Copying into a populated schema would merge two datasets."""
    state = Preflight(
        sqlite_bytes=100, free_bytes=1000, target_empty=False, target_schema_version=0
    )
    allowed, reason = preflight_verdict(state)
    assert allowed is False
    assert "not empty" in reason


def test_preflight_refuses_running_twice() -> None:
    """A second run would duplicate data, not fix anything."""
    state = Preflight(sqlite_bytes=100, free_bytes=1000, target_empty=True, target_schema_version=1)
    allowed, _ = preflight_verdict(state)
    assert allowed is False


def test_preflight_requires_headroom_beyond_the_file_size() -> None:
    state = Preflight(sqlite_bytes=100, free_bytes=150, target_empty=True, target_schema_version=0)
    allowed, _ = preflight_verdict(state)
    assert allowed is False


def test_preflight_passes_with_room_to_spare() -> None:
    allowed, reason = preflight_verdict(_ok_preflight())
    assert allowed is True
    assert reason == ""


def test_snapshot_precedes_copy_and_reconcile_precedes_cutover() -> None:
    steps = migration_plan()
    assert steps.index("snapshot") < steps.index("copy")
    assert steps.index("reconcile") < steps.index("cutover")


def test_equal_counts_and_digests_reconcile() -> None:
    counts = [TableCounts("evidence", 10, 10, "abc", "abc")]
    verdicts, agree = reconcile(counts)
    assert agree is True
    assert verdicts[0].ok is True


def test_a_row_count_mismatch_is_reported_per_table() -> None:
    counts = [TableCounts("evidence", 10, 9, "abc", "abc")]
    verdicts, agree = reconcile(counts)
    assert agree is False
    assert "row count differs" in verdicts[0].reason


def test_equal_counts_with_different_content_is_caught() -> None:
    """This is the case a count-only check passes while data was lost."""
    counts = [TableCounts("evidence", 10, 10, "abc", "xyz")]
    verdicts, agree = reconcile(counts)
    assert agree is False
    assert "digest differs" in verdicts[0].reason


def test_one_bad_table_fails_the_whole_reconciliation() -> None:
    counts = [
        TableCounts("evidence", 5, 5, "a", "a"),
        TableCounts("source_cursors", 5, 4, "b", "b"),
    ]
    _verdicts, agree = reconcile(counts)
    assert agree is False


def test_cutover_is_gated_on_reconciliation() -> None:
    assert may_cutover([TableCounts("evidence", 1, 1, "a", "a")]) is True
    assert may_cutover([TableCounts("evidence", 1, 0, "a", "a")]) is False


def test_copy_order_puts_parents_before_children() -> None:
    """A child row cannot be verified against a parent not yet copied."""
    assert TABLE_ORDER.index("evidence") < TABLE_ORDER.index("evidence_origins")
    assert TABLE_ORDER.index("governed_memories") < TABLE_ORDER.index("governed_memory_evidence")


def test_progress_resumes_from_the_first_incomplete_table() -> None:
    progress = MigrationProgress()
    progress.mark("evidence")
    remaining = resume_from(progress)
    assert "evidence" not in remaining
    assert remaining[0] == "evidence_origins"


def test_a_fresh_progress_copies_everything() -> None:
    assert resume_from(MigrationProgress()) == TABLE_ORDER
