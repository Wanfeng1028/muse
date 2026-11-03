"""A4-10: the CursorStore contract, stated once and obeyed by every impl.

The point of a repository contract is that the MySQL implementation (A4-03 /
A1-07) can be dropped in later without the scanner changing. So these tests
describe what *any* store must do, not what the in-memory one happens to do.
`InMemoryCursorStore` is only the reference implementation used to prove the
contract is satisfiable; when the MySQL store lands it must pass this same
file unchanged.

The load-bearing rule is the batch one (gate 6): the scanner is allowed one
cursor lookup *per page*, never one per file. A per-file lookup is the N+1
query the architecture forbids, and it is exactly what a slow "metadata-first"
scanner would quietly regress into. So the contract counts lookups.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.scanner.classifier import StoredFileCursor
from one_memory.memory_server.scanner.service import (
    CursorStore,
    InMemoryCursorStore,
    ScanMetrics,
    scan_once,
)


def _cursor(key: str, *, size: int = 10, checkpoint: int = 0) -> StoredFileCursor:
    return StoredFileCursor(
        file_key=key,
        file_identity=f"{key}-inode",
        observed_size=size,
        observed_modified_ns=1_000,
        checkpoint=checkpoint,
        read_to_end=True,
        anchor=None,
    )


@pytest.fixture()
def store() -> CursorStore:
    """The impl under test. Swap in the MySQL store to re-check it later."""
    return InMemoryCursorStore()


def test_get_many_returns_only_found_keys_without_placeholders(store: CursorStore) -> None:
    """A miss is an absent key, never a None the caller must guard against.

    If a missing cursor came back as None, every call site would need a
    defensive branch, and one missed branch would turn "no cursor" into
    "empty cursor" and skip a file that should have been read.
    """
    store.put_many({"present": _cursor("present")})

    found = store.get_many(["present", "absent"])

    assert set(found) == {"present"}
    assert found["present"].file_key == "present"
    assert "absent" not in found
    assert all(value is not None for value in found.values())


def test_get_many_on_empty_store_returns_empty_mapping(store: CursorStore) -> None:
    assert store.get_many(["a", "b"]) == {}


def test_put_many_persists_for_later_lookups(store: CursorStore) -> None:
    """What the scanner relies on: cursors written this cycle are read next cycle."""
    store.put_many({"k1": _cursor("k1"), "k2": _cursor("k2", size=99)})

    found = store.get_many(["k1", "k2"])

    assert found["k1"].observed_size == 10
    assert found["k2"].observed_size == 99


def test_put_many_overwrites_and_merges(store: CursorStore) -> None:
    """Re-running a scan rewrites cursors; it must not duplicate or append them."""
    store.put_many({"k": _cursor("k", checkpoint=0)})
    store.put_many({"k": _cursor("k", checkpoint=42), "other": _cursor("other")})

    found = store.get_many(["k", "other"])

    assert found["k"].checkpoint == 42
    assert set(found) == {"k", "other"}


def test_get_many_is_one_lookup_regardless_of_key_count(store: CursorStore) -> None:
    """Gate 6 measured on the store itself: batching is a property of the
    repository, not of the caller. Twenty keys must not cost twenty queries."""
    keys = [f"k{index}" for index in range(20)]
    store.put_many({key: _cursor(key) for key in keys})

    counter = getattr(store, "batch_lookups", None)
    if counter is None:
        pytest.skip("this impl does not expose a lookup counter")

    start = store.batch_lookups
    store.get_many(keys)

    assert store.batch_lookups - start == 1


def test_put_many_is_not_counted_as_a_lookup(store: CursorStore) -> None:
    """Writes are not reads. Counting them would hide a real N+1 behind a
    number that looks fine."""
    counter = getattr(store, "batch_lookups", None)
    if counter is None:
        pytest.skip("this impl does not expose a lookup counter")

    start = store.batch_lookups
    store.put_many({"k": _cursor("k")})

    assert store.batch_lookups == start


def test_base_class_refuses_to_silently_do_nothing() -> None:
    """A new impl must fail loudly. An inherited no-op store would look healthy
    while every scan re-opened every file."""
    with pytest.raises(NotImplementedError):
        CursorStore().get_many(["k"])
    with pytest.raises(NotImplementedError):
        CursorStore().put_many({"k": _cursor("k")})


def test_scan_once_uses_one_lookup_per_page_not_per_file(tmp_path, store: CursorStore) -> None:
    """The contract applied end to end: lookups track pages, not files.

    This is the assertion that catches a regression where someone moves the
    `get_many` call inside the per-file loop "to simplify".
    """
    for index in range(12):
        (tmp_path / f"f{index}.jsonl").write_text(f'{{"i":{index}}}\n', encoding="utf-8")

    metrics = ScanMetrics()
    scan_once(tmp_path, store=store, metrics=metrics, page_size=5)

    assert metrics.metadata_enumerated == 12
    assert metrics.cursor_batch_lookups == 3  # pages of 5, 5, 2
    assert metrics.cursor_batch_lookups < metrics.metadata_enumerated


def test_scan_once_writes_cursors_back_through_put_many(tmp_path, store: CursorStore) -> None:
    """A scan is only incremental if it leaves cursors behind. A store that
    accepted writes but never returned them would silently re-read forever."""
    (tmp_path / "f.jsonl").write_text('{"i":0}\n', encoding="utf-8")

    first = scan_once(tmp_path, store=store)
    assert first.metrics.changed_files == 1

    second = scan_once(tmp_path, store=store)
    assert second.metrics.files_opened == 0
    assert second.metrics.unchanged_files == 1
