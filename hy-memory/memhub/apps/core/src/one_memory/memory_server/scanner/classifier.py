"""A4-02/A4-04: the metadata gate, as a pure function.

This is the heart of D54. Every five minutes the scanner must decide, for a
large tree, which files changed — without opening any of them. So the decision
is a pure function of (filesystem metadata, stored cursor), with no I/O, which
is also what makes it testable in isolation.

The classification is deliberately conservative: anything ambiguous becomes
`REVALIDATE` and is re-read. Deciding `UNCHANGED` when we are not sure would
silently drop the user's words, which is a far worse failure than re-reading a
file that had not changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChangeKind(StrEnum):
    """Why a file needs attention, or why it does not."""

    #: Metadata matches the cursor exactly. Must never be opened.
    UNCHANGED = "unchanged"
    #: New bytes past a cursor that reached EOF. Only the tail is read.
    APPENDED = "appended"
    #: Size went backwards, or the anchor no longer matches what we read.
    TRUNCATED = "truncated"
    #: Same size, different identity (rotated, replaced, restored from backup).
    REPLACED = "replaced"
    #: mtime moved but size did not: an in-place edit we cannot place. Re-read.
    REVALIDATE = "revalidate"
    #: Never seen before.
    NEW = "new"


@dataclass(frozen=True)
class FileMetadata:
    """What one `DirEntry.stat()` gives us. Intentionally no file contents."""

    file_key: str
    #: Absolute path, so the reader can reopen the file without a second
    #: lookup. `file_key` stays relative so cursors survive a moved root.
    path: str
    #: `st_dev:st_ino`, or a stable equivalent on platforms without inodes.
    file_identity: str
    size: int
    modified_ns: int


@dataclass(frozen=True)
class StoredFileCursor:
    """What we recorded last time, from the MySQL cursor table."""

    file_key: str
    file_identity: str
    observed_size: int
    observed_modified_ns: int
    #: Byte/row offset we have already ingested.
    checkpoint: int
    #: True only when the last read reached EOF. Without this, an unchanged
    #: size would be indistinguishable from "wrote more bytes of the same size".
    read_to_end: bool
    #: HMAC of the bytes at the checkpoint boundary, or None if unanchored.
    anchor: str | None = None


def classify_file(
    metadata: FileMetadata,
    cursor: StoredFileCursor | None,
) -> ChangeKind:
    """Decide what to do with one file, using metadata only. No I/O.

    The ordering matters: identity is checked before size, because a rotated
    file can carry the same size as the one it replaced, and treating that as
    `UNCHANGED` would keep reading the new file from the old offset.
    """
    if cursor is None:
        return ChangeKind.NEW

    if metadata.file_identity != cursor.file_identity:
        return ChangeKind.REPLACED

    if metadata.size < cursor.observed_size:
        return ChangeKind.TRUNCATED

    if metadata.size > cursor.observed_size:
        return ChangeKind.APPENDED

    # Same size. Whether that is "nothing happened" depends on whether we had
    # actually reached the end last time; if not, there is unread data even
    # though the size is identical.
    if not cursor.read_to_end:
        return ChangeKind.APPENDED

    if metadata.modified_ns != cursor.observed_modified_ns:
        return ChangeKind.REVALIDATE

    return ChangeKind.UNCHANGED


def needs_open(kind: ChangeKind) -> bool:
    """Whether this classification may open the file.

    Kept as a function so the "UNCHANGED means zero open" guarantee has one
    definition the scanner, the metrics and the tests all share.
    """
    return kind is not ChangeKind.UNCHANGED
