"""A4-04/A4-11: compose the scanner and measure what the gate actually costs.

This wires classifier -> discovery -> incremental together, and counts the
things D54 says must be provable: how many metadata entries were enumerated,
how many cursor lookups were issued, how many files were opened, how many bytes
were read, and how many files actually changed.

Those five numbers are the acceptance criterion. "The scanner is fast" is not
falsifiable; "10,000 unchanged files cost 0 opens, 0 bytes, and 1 batch query"
is.

Cursor storage is injected (`CursorStore`), so this runs against an in-memory
dict in tests and against MySQL later without the scanning logic changing. That
is also why the store takes a *batch* of keys: a per-file lookup would be the
N+1 the architecture explicitly forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from one_memory.memory_server.scanner.classifier import (
    FileMetadata,
    StoredFileCursor,
    classify_file,
    needs_open,
)
from one_memory.memory_server.scanner.discovery import DEFAULT_PAGE_SIZE, scan_root
from one_memory.memory_server.scanner.incremental import read_incremental


class CursorStore:
    """Cursor access the scanner needs. Implemented over MySQL in A4-03."""

    def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        raise NotImplementedError

    def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        raise NotImplementedError


class InMemoryCursorStore(CursorStore):
    """Dict-backed store for tests and for measuring without MySQL."""

    def __init__(self) -> None:
        self._data: dict[str, StoredFileCursor] = {}
        #: Number of batch lookups issued. The point of the metric is to show
        #: it grows with pages, not with files.
        self.batch_lookups = 0

    def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        self.batch_lookups += 1
        return {key: self._data[key] for key in keys if key in self._data}

    def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        self._data.update(cursors)


@dataclass
class ScanMetrics:
    """The five numbers D54 requires, plus what actually changed."""

    metadata_enumerated: int = 0
    cursor_batch_lookups: int = 0
    files_opened: int = 0
    bytes_read: int = 0
    changed_files: int = 0
    unchanged_files: int = 0
    records_read: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)


@dataclass
class ScanOutcome:
    metrics: ScanMetrics
    records: list[str]


def scan_once(
    root: Path,
    *,
    store: CursorStore,
    metrics: ScanMetrics | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ScanOutcome:
    """Run one scan cycle over a root, reading only what changed."""
    metrics = metrics or ScanMetrics()
    records: list[str] = []
    pending_updates: dict[str, StoredFileCursor] = {}

    page: list[FileMetadata] = []
    for metadata in scan_root(root):
        page.append(metadata)
        if len(page) >= page_size:
            _process_page(page, store, metrics, records, pending_updates)
            page = []
    if page:
        _process_page(page, store, metrics, records, pending_updates)

    if pending_updates:
        store.put_many(pending_updates)
    return ScanOutcome(metrics=metrics, records=records)


def _process_page(
    page: list[FileMetadata],
    store: CursorStore,
    metrics: ScanMetrics,
    records: list[str],
    pending_updates: dict[str, StoredFileCursor],
) -> None:
    """Classify a whole page, then open only the files that warrant it.

    One `get_many` per page, never one per file: a per-file lookup is the N+1
    query the architecture forbids and the reason the gate would be pointless.
    """
    metrics.metadata_enumerated += len(page)
    cursors = store.get_many([item.file_key for item in page])
    metrics.cursor_batch_lookups += 1

    for metadata in page:
        cursor = cursors.get(metadata.file_key)
        kind = classify_file(metadata, cursor)
        metrics.by_kind[kind.value] = metrics.by_kind.get(kind.value, 0) + 1

        if not needs_open(kind):
            metrics.unchanged_files += 1
            continue

        metrics.changed_files += 1
        result = read_incremental(
            Path(metadata.path),
            change=kind,
            checkpoint=cursor.checkpoint if cursor else 0,
        )
        metrics.files_opened += 1
        metrics.bytes_read += sum(len(record) for record in result.records)
        metrics.records_read += len(result.records)
        records.extend(result.records)
        pending_updates[metadata.file_key] = StoredFileCursor(
            file_key=metadata.file_key,
            file_identity=metadata.file_identity,
            observed_size=metadata.size,
            observed_modified_ns=metadata.modified_ns,
            checkpoint=result.new_checkpoint,
            read_to_end=result.read_to_end,
        )
