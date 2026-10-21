"""A4-04/A4-11: the composed scanner, judged by the numbers D54 demands.

D54's acceptance is behavioural, not structural: many unchanged files must cost
zero opens, zero reads, zero hashes. So these tests assert the five measured
quantities rather than asserting that the right functions got called.

A second-run test is the real proof. Most scanner bugs pass on a first scan,
because a first scan has no cursors and therefore opens everything.
"""

from __future__ import annotations

from pathlib import Path

from one_memory.memory_server.scanner.service import (
    InMemoryCursorStore,
    ScanMetrics,
    scan_once,
)


def _populate(root: Path, count: int, lines: int = 2) -> None:
    for index in range(count):
        body = "".join(f'{{"i":{index},"l":{line}}}\n' for line in range(lines))
        (root / f"f{index}.jsonl").write_text(body, encoding="utf-8")


def test_first_scan_opens_everything(tmp_path: Path) -> None:
    """Baseline: with no cursors there is nothing to skip. Establishes the
    instrument can observe opens at all."""
    _populate(tmp_path, count=5)
    outcome = scan_once(tmp_path, store=InMemoryCursorStore())
    assert outcome.metrics.files_opened == 5
    assert outcome.metrics.records_read == 10


def test_second_scan_with_no_changes_opens_nothing(tmp_path: Path) -> None:
    """The D54 guarantee: unchanged files are never opened again."""
    _populate(tmp_path, count=20)
    store = InMemoryCursorStore()
    first = scan_once(tmp_path, store=store)
    assert first.metrics.files_opened == 20

    second_metrics = ScanMetrics()
    second = scan_once(tmp_path, store=store, metrics=second_metrics)
    assert second.metrics.changed_files == 0
    assert second.metrics.files_opened == 0
    assert second.metrics.bytes_read == 0
    assert second.metrics.unchanged_files == 20


def test_only_the_appended_file_is_read(tmp_path: Path) -> None:
    """An append costs one open, not a rescan of the tree."""
    _populate(tmp_path, count=10)
    store = InMemoryCursorStore()
    scan_once(tmp_path, store=store)

    (tmp_path / "f3.jsonl").write_text(
        (tmp_path / "f3.jsonl").read_text(encoding="utf-8") + '{"i":99}\n',
        encoding="utf-8",
    )
    outcome = scan_once(tmp_path, store=store, metrics=ScanMetrics())
    assert outcome.metrics.files_opened == 1
    assert outcome.metrics.changed_files == 1
    assert '{"i":99}' in outcome.records


def test_cursor_lookups_are_batched_not_per_file(tmp_path: Path) -> None:
    """One lookup per page, not per file. Per-file is the N+1 that is banned."""
    _populate(tmp_path, count=50)
    store = InMemoryCursorStore()
    scan_once(tmp_path, store=store)
    store.batch_lookups = 0

    outcome = scan_once(tmp_path, store=store, metrics=ScanMetrics(), page_size=500)
    # 50 files in a single page must not produce 50 lookups.
    assert outcome.metrics.cursor_batch_lookups == 1
    assert outcome.metrics.metadata_enumerated == 50


def test_metrics_are_reported_per_change_kind(tmp_path: Path) -> None:
    _populate(tmp_path, count=3)
    store = InMemoryCursorStore()
    scan_once(tmp_path, store=store)
    outcome = scan_once(tmp_path, store=store, metrics=ScanMetrics())
    assert outcome.metrics.by_kind.get("unchanged") == 3


def test_truncation_forces_a_reread_rather_than_a_skip(tmp_path: Path) -> None:
    """A shrunken file is opened; skipping it would miss whatever replaced it."""
    _populate(tmp_path, count=3)
    store = InMemoryCursorStore()
    scan_once(tmp_path, store=store)

    (tmp_path / "f1.jsonl").write_text('{"only":1}\n', encoding="utf-8")
    outcome = scan_once(tmp_path, store=store, metrics=ScanMetrics())
    assert outcome.metrics.by_kind.get("truncated") == 1
    assert outcome.metrics.files_opened == 1
    assert '{"only":1}' in outcome.records


def test_empty_root_scans_cleanly(tmp_path: Path) -> None:
    outcome = scan_once(tmp_path, store=InMemoryCursorStore())
    assert outcome.metrics.metadata_enumerated == 0
    assert outcome.metrics.files_opened == 0
    assert outcome.records == []


def test_repeated_scans_stay_stable(tmp_path: Path) -> None:
    """Steady state must not accumulate work or re-read anything."""
    _populate(tmp_path, count=8)
    store = InMemoryCursorStore()
    scan_once(tmp_path, store=store)
    for _ in range(3):
        outcome = scan_once(tmp_path, store=store, metrics=ScanMetrics())
        assert outcome.metrics.files_opened == 0
        assert outcome.metrics.bytes_read == 0
