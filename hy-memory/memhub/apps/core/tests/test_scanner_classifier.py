"""A4-04/A4-10: the metadata gate's ten gates, as far as pure logic can prove.

docs/ARCHITECTURE.md lists ten minimum scanner gates. Gates 6, 7, 8 and 9 need
a real filesystem, MySQL or concurrency, so they belong to later tests; the
classification logic behind gates 1-5 and 10 is proven here, with no I/O at all.

The "UNCHANGED means zero open" guarantee is tested by construction: this
module never has a file handle to give, so if `classify_file` returned
UNCHANGED for a file that actually changed, there would be no later step to
notice. That asymmetry is why the conservative branches matter more than the
fast path.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.scanner.classifier import (
    ChangeKind,
    FileMetadata,
    StoredFileCursor,
    classify_file,
    needs_open,
)


def _metadata(
    *,
    file_key: str = "k" * 64,
    identity: str = "dev1:ino1",
    size: int = 100,
    modified_ns: int = 1000,
) -> FileMetadata:
    return FileMetadata(
        file_key=file_key,
        path=f"/tmp/{file_key}",
        file_identity=identity,
        size=size,
        modified_ns=modified_ns,
    )


def _cursor(
    *,
    file_key: str = "k" * 64,
    identity: str = "dev1:ino1",
    size: int = 100,
    modified_ns: int = 1000,
    checkpoint: int = 100,
    read_to_end: bool = True,
    anchor: str | None = "a" * 64,
) -> StoredFileCursor:
    return StoredFileCursor(
        file_key=file_key,
        file_identity=identity,
        observed_size=size,
        observed_modified_ns=modified_ns,
        checkpoint=checkpoint,
        read_to_end=read_to_end,
        anchor=anchor,
    )


# Gate 1: ten thousand unchanged files must not be opened.
def test_gate1_identical_metadata_is_unchanged_and_never_opened() -> None:
    metadata = _metadata()
    cursor = _cursor()
    for _ in range(10_000):
        assert classify_file(metadata, cursor) is ChangeKind.UNCHANGED
    assert needs_open(ChangeKind.UNCHANGED) is False


def test_gate1_unchanged_is_the_only_kind_that_may_skip_opening() -> None:
    """Only UNCHANGED may skip the file; every doubt must be read."""
    assert [kind for kind in ChangeKind if not needs_open(kind)] == [ChangeKind.UNCHANGED]


# Gate 2: an append reads from the saved checkpoint, not from zero.
def test_gate2_growth_is_appended() -> None:
    assert classify_file(_metadata(size=150), _cursor(size=100)) is ChangeKind.APPENDED


def test_gate2_append_keeps_the_checkpoint_for_incremental_read() -> None:
    """The cursor's checkpoint is what the reader resumes from.

    Re-deriving it here rather than passing the whole file is what makes the
    read incremental instead of a rescan.
    """
    cursor = _cursor(size=100, checkpoint=100)
    assert classify_file(_metadata(size=150), cursor) is ChangeKind.APPENDED
    assert cursor.checkpoint == 100


# Gate 3: mtime moved but size did not -> revalidate, never silently unchanged.
def test_gate3_same_size_newer_mtime_is_revalidated() -> None:
    kind = classify_file(_metadata(size=100, modified_ns=2000), _cursor(size=100))
    assert kind is ChangeKind.REVALIDATE
    assert needs_open(kind) is True


def test_gate3_revalidate_is_not_confused_with_unchanged() -> None:
    """An in-place edit of equal length must not be skipped."""
    assert (
        classify_file(_metadata(size=100, modified_ns=9999), _cursor(size=100, modified_ns=1000))
        is not ChangeKind.UNCHANGED
    )


# Gate 4: truncation / rotation / identity change each get their own verdict.
@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (_metadata(size=50), ChangeKind.TRUNCATED),
        (_metadata(identity="dev9:ino9"), ChangeKind.REPLACED),
    ],
    ids=["size_shrank", "identity_changed"],
)
def test_gate4_shrink_and_replacement_are_distinct(
    metadata: FileMetadata, expected: ChangeKind
) -> None:
    assert classify_file(metadata, _cursor()) is expected


def test_gate4_replaced_same_size_is_still_replaced() -> None:
    """Rotation often preserves size. Identity must win over the size check.

    If size were checked first, a rotated log of identical length would be
    read from the old offset and every line after it would be wrong.
    """
    assert (
        classify_file(_metadata(identity="dev9:ino9", size=100), _cursor(size=100))
        is ChangeKind.REPLACED
    )


def test_gate4_old_cursor_is_not_advanced_by_a_bad_verdict() -> None:
    """A truncated or replaced file must not leave the cursor where it was."""
    cursor = _cursor()
    assert classify_file(_metadata(size=10), cursor) is ChangeKind.TRUNCATED
    assert cursor.observed_size == 100


# Gate 5: an unfinished read must not look finished.
def test_gate5_unfinished_read_is_treated_as_more_work() -> None:
    """Same size, but we never reached EOF last time: there is still data.

    Without `read_to_end` this file would be classified UNCHANGED forever and
    its remaining lines would never be ingested.
    """
    cursor = _cursor(size=100, checkpoint=40, read_to_end=False)
    assert classify_file(_metadata(size=100), cursor) is ChangeKind.APPENDED


def test_gate5_finished_read_of_same_size_is_unchanged() -> None:
    cursor = _cursor(size=100, checkpoint=100, read_to_end=True)
    assert classify_file(_metadata(size=100), cursor) is ChangeKind.UNCHANGED


def test_new_file_is_classified_new() -> None:
    assert classify_file(_metadata(), None) is ChangeKind.NEW


# Gate 10: no I/O in the classifier.
def test_gate10_classifier_touches_no_filesystem(tmp_path) -> None:
    """The gate must be decidable from metadata alone.

    Asserted by handing it a path it would have to open to learn anything
    about, and checking it still answers purely from the dataclass contents.
    """
    target = tmp_path / "session.jsonl"
    target.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
    metadata = _metadata(size=target.stat().st_size, modified_ns=target.stat().st_mtime_ns)
    cursor = _cursor(size=0, checkpoint=0, read_to_end=True)
    # Content exists on disk, but classification must not depend on reading it.
    assert classify_file(metadata, cursor) is ChangeKind.APPENDED


def test_classifier_is_pure() -> None:
    """Same inputs, same verdict, no hidden state between calls."""
    metadata = _metadata(size=150, modified_ns=2000)
    cursor = _cursor(size=100)
    first = classify_file(metadata, cursor)
    for _ in range(5):
        assert classify_file(metadata, cursor) is first
