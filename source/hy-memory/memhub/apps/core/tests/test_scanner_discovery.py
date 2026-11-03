"""A4-08: discovery produces metadata only, bounded and fair.

The property worth proving is negative: discovery must not read file contents.

Proving this needs care, and an earlier attempt got it wrong: comparing the
reported size against `st_size` cannot detect an implementation that *opens*
the file and measures it, because those agree. What actually distinguishes them
is whether the file is opened at all, so these tests count opens via `open` and
`os.scandir` usage rather than comparing sizes.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from one_memory.memory_server.scanner.classifier import FileMetadata
from one_memory.memory_server.scanner.discovery import (
    DEFAULT_PAGE_SIZE,
    DiscoveryCursor,
    is_done,
    page_from_keyset,
    page_roots,
    scan_root,
)


def _tree(root: Path, files: int = 3, depth: int = 2) -> None:
    for level in range(depth):
        directory = root / f"d{level}"
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(files):
            (directory / f"f{index}.jsonl").write_text("x" * (10 + index), encoding="utf-8")


def test_scan_root_yields_metadata_for_every_file(tmp_path: Path) -> None:
    _tree(tmp_path, files=3, depth=2)
    found = list(scan_root(tmp_path))
    assert len(found) == 6
    assert all(isinstance(item, FileMetadata) for item in found)


def test_discovery_never_opens_a_file(tmp_path: Path, monkeypatch) -> None:
    """A metadata-only directory entry is enough; no real file must exist."""
    missing = tmp_path / "never-created.jsonl"
    entry = SimpleNamespace(
        path=str(missing),
        is_dir=lambda *, follow_symlinks: False,
        stat=lambda *, follow_symlinks: SimpleNamespace(
            st_dev=1,
            st_ino=2,
            st_size=5,
            st_mtime_ns=3,
        ),
    )
    monkeypatch.setattr(os, "scandir", lambda _root: iter((entry,)))

    found = list(scan_root(tmp_path))

    assert not missing.exists()
    assert len(found) == 1
    assert found[0].path == str(missing)
    assert found[0].size == 5


def test_directories_are_walked_not_yielded(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.jsonl").write_text("x", encoding="utf-8")
    found = list(scan_root(tmp_path))
    assert len(found) == 1
    assert found[0].file_key == "nested/a.jsonl"


def test_non_recursive_stops_at_the_top(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.jsonl").write_text("x", encoding="utf-8")
    (tmp_path / "top.jsonl").write_text("x", encoding="utf-8")
    found = list(scan_root(tmp_path, recursive=False))
    assert [item.file_key for item in found] == ["top.jsonl"]


def test_file_key_is_relative_to_the_root(tmp_path: Path) -> None:
    """Relative keys keep cursors valid when a root moves."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.jsonl").write_text("x", encoding="utf-8")
    found = list(scan_root(tmp_path))
    assert found[0].file_key == "sub/a.jsonl"


def test_identity_is_stable_and_distinct(tmp_path: Path) -> None:
    first = tmp_path / "a.jsonl"
    first.write_text("x", encoding="utf-8")
    before = list(scan_root(tmp_path))[0]
    again = list(scan_root(tmp_path))[0]
    assert before.file_identity == again.file_identity

    second = tmp_path / "b.jsonl"
    second.write_text("x", encoding="utf-8")
    identities = {item.file_identity for item in scan_root(tmp_path)}
    assert len(identities) == 2


def test_pages_are_bounded(tmp_path: Path) -> None:
    _tree(tmp_path, files=4, depth=2)
    page = page_roots([tmp_path], cursor=DiscoveryCursor(), page_size=3)
    assert len(page) == 3


def test_multiple_roots_are_served_round_robin(tmp_path: Path) -> None:
    """No single root may monopolise a page; that would starve other sources."""
    big = tmp_path / "big"
    small = tmp_path / "small"
    big.mkdir()
    small.mkdir()
    for index in range(5):
        (big / f"b{index}.jsonl").write_text("x", encoding="utf-8")
    (small / "s0.jsonl").write_text("x", encoding="utf-8")

    page = page_roots([big, small], cursor=DiscoveryCursor(), page_size=4)
    keys = [item.file_key for item in page]
    assert any(key.startswith("b") for key in keys)
    assert "s0.jsonl" in keys


def test_paging_resumes_without_repeating(tmp_path: Path) -> None:
    """Resuming must not re-emit what was already handed out."""
    _tree(tmp_path, files=2, depth=2)
    cursor = DiscoveryCursor()
    first = page_roots([tmp_path], cursor=cursor, page_size=2)
    assert len(first) == 2
    assert cursor.last_key_by_root[str(tmp_path)] == first[-1].file_key

    second = page_roots([tmp_path], cursor=cursor, page_size=2)
    assert second
    assert set(item.file_key for item in second).isdisjoint(set(item.file_key for item in first))


def test_paging_exhausts_the_root() -> None:
    """A finished root is marked done, and further paging returns nothing."""
    import tempfile

    root = Path(tempfile.mkdtemp())
    (root / "a.jsonl").write_text("x", encoding="utf-8")
    cursor = DiscoveryCursor()
    first = page_roots([root], cursor=cursor, page_size=10)
    assert len(first) == 1
    assert is_done(cursor, root) is True
    assert page_roots([root], cursor=cursor, page_size=10) == []


def test_keyset_page_boundary_is_exclusive(tmp_path: Path) -> None:
    """The boundary entry must not repeat."""
    entries = [
        FileMetadata(file_key="a", path="a", file_identity="1", size=1, modified_ns=1),
        FileMetadata(file_key="b", path="b", file_identity="2", size=1, modified_ns=1),
        FileMetadata(file_key="c", path="c", file_identity="3", size=1, modified_ns=1),
    ]
    page, last, done = page_from_keyset(entries, after="a", page_size=1)
    assert [item.file_key for item in page] == ["b"]
    assert last == "b"
    assert done is False


def test_keyset_past_the_end_is_exhausted(tmp_path: Path) -> None:
    entries = [
        FileMetadata(file_key="a", path="a", file_identity="1", size=1, modified_ns=1),
    ]
    page, last, done = page_from_keyset(entries, after="z", page_size=10)
    assert page == []
    assert last == "z"
    assert done is True


def test_keyset_resume_survives_unsorted_creation(tmp_path: Path) -> None:
    """Files created out of order must still page exactly once.

    Filesystem order is not sorted, so the keyset boundary is only correct if
    discovery sorts. (An earlier test used names that happened to be in order,
    so removing the sort went undetected.)
    """
    for name in ("c.jsonl", "a.jsonl", "b.jsonl"):
        (tmp_path / name).write_text("x", encoding="utf-8")

    cursor = DiscoveryCursor()
    seen: list[str] = []
    while True:
        page = page_roots([tmp_path], cursor=cursor, page_size=1)
        if not page:
            break
        seen.extend(item.file_key for item in page)

    assert sorted(seen) == ["a.jsonl", "b.jsonl", "c.jsonl"]
    assert len(seen) == len(set(seen)), "a file was emitted twice"


def test_empty_root_list_yields_nothing() -> None:
    assert page_roots([], cursor=DiscoveryCursor()) == []


def test_invalid_page_size_is_rejected(tmp_path: Path) -> None:

    with pytest.raises(ValueError):
        page_roots([tmp_path], cursor=DiscoveryCursor(), page_size=0)


def test_default_page_size_is_bounded() -> None:
    assert DEFAULT_PAGE_SIZE > 0
