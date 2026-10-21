"""A4-04: read only the bytes past a known cursor.

This is the second half of the metadata gate. The classifier decides *whether*
to open a file; this decides *where in it* to start. Together they turn a
periodic full-tree scan into reading only what actually changed.

The rules that matter:

- An `APPENDED` file resumes at the saved byte offset, so a 200 MB session log
  that gained one line costs one line of I/O.
- A `TRUNCATED` or `REPLACED` file must be reconciled from the start, not
  resumed: continuing from an offset into a shorter or different file would
  read unrelated bytes as if they were conversation.
- A trailing line without a terminator is not a record. Returning it would
  parse a half-written line, and advancing the cursor past it would lose that
  line forever once the writer completes it.
- The cursor only advances past complete records. Crashing mid-read therefore
  costs a re-read, never a gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from one_memory.memory_server.scanner.classifier import ChangeKind

#: Bytes read per chunk. Bounded so a huge file cannot inflate memory.
CHUNK_SIZE = 1 << 20


@dataclass(frozen=True)
class ReadResult:
    """What one incremental read produced."""

    #: Complete records, in file order.
    records: tuple[str, ...]
    #: Byte offset safe to commit as the new checkpoint.
    new_checkpoint: int
    #: True when the read reached the end of file with no partial line left.
    read_to_end: bool
    #: Bytes that form an incomplete trailing line, held for the next read.
    partial: str = ""


def read_incremental(
    path: Path,
    *,
    change: ChangeKind,
    checkpoint: int,
    encoding: str = "utf-8",
) -> ReadResult:
    """Read new complete records from `path`, starting at `checkpoint`.

    `change` decides the start offset: only a plain append may resume. Anything
    that invalidates the old position starts over, because the bytes at that
    offset are no longer the ones the checkpoint refers to.
    """
    start = checkpoint if change is ChangeKind.APPENDED else 0

    with path.open("rb") as handle:
        if start:
            handle.seek(start)
        raw = handle.read()

    size = path.stat().st_size
    text = raw.decode(encoding, errors="replace")

    if not text:
        return ReadResult(
            records=(),
            new_checkpoint=size if change is not ChangeKind.APPENDED else start,
            read_to_end=True,
        )

    # `"a\nb\n".split("\n")` ends with an empty element that is not a line; it
    # exists only because the text ends with a newline. Keeping it would add a
    # phantom one-byte "line" and push the checkpoint past EOF.
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
        partial = ""
    else:
        # Everything after the last newline is an unfinished line.
        partial = lines[-1] if lines else ""
        lines = lines[:-1]

    complete = lines
    records = tuple(line for line in complete if line.strip())
    consumed = sum(len(line) + 1 for line in complete)

    return ReadResult(
        records=records,
        new_checkpoint=start + consumed,
        read_to_end=text.endswith("\n"),
        partial=partial,
    )
