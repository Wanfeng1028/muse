"""A4-08: bounded, fair directory enumeration.

Discovery only produces `FileMetadata`. It never opens a file, and it never
decides anything — that is the classifier's job. Keeping them apart is what
makes the "unchanged files are never opened" guarantee testable: if discovery
read contents, the guarantee could not be asserted anywhere.

Two constraints shape it:

**Bounded.** A large tree cannot be materialised in memory at once, so
enumeration is a generator with a page size. Callers pull what they can afford.

**Fair and resumable.** Roots are served round-robin via a persistent cursor so
one enormous root cannot starve the others, and a scan interrupted mid-way can
resume instead of restarting from the top.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from one_memory.memory_server.scanner.classifier import FileMetadata

#: Default number of files yielded before returning control to the caller.
DEFAULT_PAGE_SIZE = 500


def _identity(stat_result: os.stat_result) -> str:
    """Stable identity for change detection.

    `st_dev:st_ino` survives renames within a filesystem and changes on
    replacement, which is exactly the distinction the classifier needs.
    """
    return f"{stat_result.st_dev}:{stat_result.st_ino}"


def scan_root(
    root: Path,
    *,
    recursive: bool = True,
    on_error: object | None = None,
) -> Iterator[FileMetadata]:
    """Yield metadata for files under `root`, using stat only.

    Uses `os.scandir` because `DirEntry.stat()` is already cached on many
    platforms, so the metadata gate stays cheap. Directories are walked but
    never yielded.
    """
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            if callable(on_error):
                on_error(current, error)
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        pending.append(Path(entry.path))
                    continue
                stat_result = entry.stat(follow_symlinks=False)
            except OSError as error:
                if callable(on_error):
                    on_error(Path(entry.path), error)
                continue
            yield FileMetadata(
                file_key=_file_key(Path(entry.path), root),
                path=entry.path,
                file_identity=_identity(stat_result),
                size=stat_result.st_size,
                modified_ns=stat_result.st_mtime_ns,
            )


def _file_key(path: Path, root: Path) -> str:
    """Path relative to the root, as the cursor's join key.

    Relative rather than absolute so a moved-but-otherwise-identical root keeps
    its cursors instead of re-importing everything.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


@dataclass
class DiscoveryCursor:
    """Per-root progress, so a long scan can resume."""

    #: Root path -> last `file_key` handed out for it.
    #:
    #: Kept as a **keyset** rather than a count. "Skip the first N entries"
    #: silently breaks when a file is added or removed mid-scan, because N no
    #: longer refers to the same entry — and a long scan is exactly when that
    #: happens. Resuming from a key is stable under concurrent change.
    last_key_by_root: dict[str, str] = field(default_factory=dict)
    #: Root path -> directory key currently being paged through.
    last_dir_by_root: dict[str, str] = field(default_factory=dict)
    #: Root path -> whether that root has been fully enumerated.
    done_by_root: dict[str, bool] = field(default_factory=dict)


def resume_keyset(cursor: DiscoveryCursor, root: Path) -> str | None:
    """The key to resume from, or None when starting fresh."""
    return cursor.last_key_by_root.get(str(root))


def mark_done(cursor: DiscoveryCursor, root: Path) -> None:
    cursor.done_by_root[str(root)] = True


def is_done(cursor: DiscoveryCursor, root: Path) -> bool:
    return cursor.done_by_root.get(str(root), False)


def page_from_keyset(
    entries: list[FileMetadata],
    *,
    after: str | None,
    page_size: int,
) -> tuple[list[FileMetadata], str | None, bool]:
    """Take one keyset page from an entry list.

    Returns (page, last_key, reached_end). The page starts *strictly after*
    `after`, so a resume never re-emits the boundary entry — a caller that pages
    through sees each entry exactly once.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    if not entries:
        return [], after, True

    ordered = sorted(entries, key=lambda item: item.file_key)
    start = 0
    if after is not None:
        for index, item in enumerate(ordered):
            if item.file_key > after:
                start = index
                break
        else:
            # Everything is at or before the boundary: this root is exhausted.
            return [], after, True

    page = ordered[start : start + page_size]
    last_key = page[-1].file_key if page else after
    reached_end = start + len(page) >= len(ordered)
    return page, last_key, reached_end


def page_roots(
    roots: list[Path],
    *,
    cursor: DiscoveryCursor,
    page_size: int = DEFAULT_PAGE_SIZE,
    recursive: bool = True,
) -> list[FileMetadata]:
    """Yield up to `page_size` files, serving roots round-robin.

    Round-robin matters for fairness: scanning roots to completion in order
    means a huge first root delays every other root, and the user sees one
    source imported and nine untouched for a long time.

    Progress is a **keyset over directories**, not a consumed count. A count
    means "skip the first N entries", which silently breaks if a file is added
    or removed mid-scan, because N no longer refers to the same entry — and a
    long scan is exactly when that happens.

    Discovery yields in filesystem order, which is *not* sorted, so resuming
    cannot rely on position. Directories are therefore enumerated in sorted
    order and files within a directory are sorted by `file_key`; the cursor
    records the last directory and, within it, the last key emitted. That gives
    a stable keyset boundary without holding the whole tree in memory.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")

    page: list[FileMetadata] = []
    if not roots:
        return page

    walks: dict[str, Iterator[tuple[str, FileMetadata]]] = {}
    for root in roots:
        if is_done(cursor, root):
            continue
        walks[str(root)] = _walk_files(root, recursive=recursive)

    if not walks:
        return page

    # 轮转：每个 root 每次只贡献**一个**文件，避免大 root 独占整页。
    while len(page) < page_size:
        progressed = False
        for root in roots:
            if len(page) >= page_size:
                break
            key = str(root)
            walk = walks.get(key)
            if walk is None:
                continue
            if is_done(cursor, root):
                continue

            resume_dir = cursor.last_dir_by_root.get(key)
            resume_key = resume_keyset(cursor, root)

            taken: FileMetadata | None = None
            dir_of_taken = ""
            for dir_key, metadata in walk:
                # 跳过断点之前已发射的文件（按 file_key 比较，跨调用稳定）
                if resume_dir is not None:
                    if dir_key < resume_dir:
                        continue
                    if (
                        dir_key == resume_dir
                        and resume_key is not None
                        and metadata.file_key <= resume_key
                    ):
                        continue
                taken = metadata
                dir_of_taken = dir_key
                break

            if taken is None:
                mark_done(cursor, root)
                continue

            page.append(taken)
            cursor.last_dir_by_root[key] = dir_of_taken
            cursor.last_key_by_root[key] = taken.file_key
            progressed = True

        if not progressed:
            break

    return page


def _walk_files(
    root: Path,
    *,
    recursive: bool = True,
) -> Iterator[tuple[str, FileMetadata]]:
    """Yield (directory key, file metadata) one file at a time.

    One file per step (rather than a whole directory) so a keyset resume can
    advance file by file. Directories and files are both sorted, which makes the
    emitted order match `file_key` order — the keyset boundary is only correct
    if those agree.
    """
    pending: list[Path] = [root]
    seen: set[str] = set()
    while pending:
        current = pending.pop(0)
        dir_key = "" if current == root else _file_key(current, root)
        if dir_key in seen:
            continue
        seen.add(dir_key)
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue

        files: list[FileMetadata] = []
        subdirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        subdirs.append(Path(entry.path))
                    continue
                stat_result = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            files.append(
                FileMetadata(
                    file_key=_file_key(Path(entry.path), root),
                    path=entry.path,
                    file_identity=_identity(stat_result),
                    size=stat_result.st_size,
                    modified_ns=stat_result.st_mtime_ns,
                )
            )
        files.sort(key=lambda item: item.file_key)
        for metadata in files:
            yield dir_key, metadata
        # 子目录按 key 排序入队，保证整体顺序与 file_key 顺序一致
        pending.extend(sorted(subdirs, key=lambda p: _file_key(p, root)))
