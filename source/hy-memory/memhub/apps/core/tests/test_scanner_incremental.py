"""A4-04: reading only the tail, and refusing to resume when it is unsafe.

The dangerous failure here is not reading too much — it is resuming from an
offset that no longer means what it used to, which silently produces records
that were never said. So several tests assert where the read *starts*.
"""

from __future__ import annotations

from pathlib import Path

from one_memory.memory_server.scanner.classifier import ChangeKind
from one_memory.memory_server.scanner.incremental import read_incremental


def test_append_reads_only_the_new_tail(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    checkpoint = len('{"a":1}\n{"b":2}\n')
    target.write_text('{"a":1}\n{"b":2}\n{"c":3}\n', encoding="utf-8")

    result = read_incremental(target, change=ChangeKind.APPENDED, checkpoint=checkpoint)
    assert result.records == ('{"c":3}',)
    assert result.read_to_end is True


def test_append_does_not_restart_from_zero(tmp_path: Path) -> None:
    """Resuming is the whole point; restarting would re-read the entire file."""
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n{"b":2}\n{"c":3}\n', encoding="utf-8")
    checkpoint = len('{"a":1}\n{"b":2}\n')
    result = read_incremental(target, change=ChangeKind.APPENDED, checkpoint=checkpoint)
    assert result.records == ('{"c":3}',)
    assert result.new_checkpoint > checkpoint


def test_new_file_reads_from_the_start(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.NEW, checkpoint=0)
    assert result.records == ('{"a":1}',)


def test_truncated_file_is_reconciled_from_the_start(tmp_path: Path) -> None:
    """A shorter file invalidates the old offset; resuming would read garbage."""
    target = tmp_path / "s.jsonl"
    target.write_text('{"new":1}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.TRUNCATED, checkpoint=999)
    assert result.records == ('{"new":1}',)
    assert result.new_checkpoint == target.stat().st_size


def test_replaced_file_is_reconciled_from_the_start(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"rotated":1}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.REPLACED, checkpoint=40)
    assert result.records == ('{"rotated":1}',)


def test_revalidate_rereads_from_the_start(tmp_path: Path) -> None:
    """An in-place edit of equal length cannot be resumed safely."""
    target = tmp_path / "s.jsonl"
    target.write_text('{"edited":1}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.REVALIDATE, checkpoint=5)
    assert result.records == ('{"edited":1}',)


def test_incomplete_trailing_line_is_not_a_record(tmp_path: Path) -> None:
    """A half-written line must wait; parsing it would store a broken record."""
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n{"partial":', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.NEW, checkpoint=0)
    assert result.records == ('{"a":1}',)
    assert result.partial == '{"partial":'
    assert result.read_to_end is False


def test_cursor_does_not_advance_past_an_incomplete_line(tmp_path: Path) -> None:
    """Committing past a partial line would lose it once it is completed."""
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n{"partial":', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.NEW, checkpoint=0)
    committed = result.new_checkpoint

    target.write_text('{"a":1}\n{"partial":true}\n', encoding="utf-8")
    second = read_incremental(target, change=ChangeKind.APPENDED, checkpoint=committed)
    assert '{"partial":true}' in second.records


def test_completed_file_reports_read_to_end(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.NEW, checkpoint=0)
    assert result.read_to_end is True
    assert result.partial == ""


def test_no_new_bytes_yields_nothing(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n', encoding="utf-8")
    checkpoint = target.stat().st_size
    result = read_incremental(target, change=ChangeKind.APPENDED, checkpoint=checkpoint)
    assert result.records == ()


def test_blank_lines_are_dropped(tmp_path: Path) -> None:
    target = tmp_path / "s.jsonl"
    target.write_text('{"a":1}\n\n\n{"b":2}\n', encoding="utf-8")
    result = read_incremental(target, change=ChangeKind.NEW, checkpoint=0)
    assert result.records == ('{"a":1}', '{"b":2}')
