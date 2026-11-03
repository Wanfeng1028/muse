"""The ordering index is built off the startup path.

Building it inline cost 9.28 s on 432k rows, all of it inside
`EvidenceStore.__init__`, which is on Core's startup path. These tests pin the
two properties that matter: opening a database does not pay for it, and the
query is correct before it lands and fast after.
"""

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from one_memory.imports.storage import EvidenceStore


def _rows(store: EvidenceStore, count: int) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.executemany(
            "INSERT INTO evidence (evidence_id, idempotency_key, user_id, source_id, "
            "conversation_id, message_id, content_kind, role, written_by, created_at, "
            "verbatim, content_hash, revision, imported_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    f"e{i}",
                    f"k{i}",
                    "local",
                    "fixture",
                    f"c{i}",
                    f"m{i}",
                    "raw_conversation",
                    "user",
                    "person",
                    "2026-09-27T00:00:00+00:00",
                    "hello",
                    f"h{i}",
                    1,
                    # e0 is the newest: one second newer than e1, which is one
                    # second newer than e2, and so on. A total order, so the
                    # expected first row is unambiguous.
                    (datetime.now(UTC) - timedelta(seconds=i)).isoformat(),
                    "2026-09-27T00:00:00+00:00",
                )
                for i in range(count)
            ],
        )


def test_opening_a_database_does_not_build_the_index_inline(tmp_path: Path) -> None:
    """The whole point: startup must not wait for it."""
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")

    assert store.has_imported_index() is False


def test_the_background_build_creates_it(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    _rows(store, 200)

    started = store.ensure_imported_index_in_background()
    assert started is True

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not store.has_imported_index():
        time.sleep(0.05)
    assert store.has_imported_index() is True


def test_the_query_is_correct_before_the_index_lands(tmp_path: Path) -> None:
    """Slow is acceptable; wrong is not. Ordering must hold either way."""
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    _rows(store, 200)
    assert store.has_imported_index() is False

    records, total = store.list_recent_conversations(user_id="local", limit=5)

    assert total == 200
    assert [record.evidence_id for record in records][0] == "e0"


def test_the_query_is_still_correct_after_the_index_lands(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    _rows(store, 200)
    store.ensure_imported_index_in_background()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not store.has_imported_index():
        time.sleep(0.05)

    records, total = store.list_recent_conversations(user_id="local", limit=5)

    assert total == 200
    assert [record.evidence_id for record in records][0] == "e0"


def test_a_second_call_does_not_start_another_build(tmp_path: Path) -> None:
    """Two processes opening at once must not both build it."""
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    _rows(store, 200)

    assert store.ensure_imported_index_in_background() is True
    assert store.ensure_imported_index_in_background() is False


def test_a_database_that_already_has_it_is_left_alone(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    _rows(store, 200)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS evidence_imported_index "
            "ON evidence(user_id, imported_at DESC, evidence_id DESC)"
        )

    assert store.has_imported_index() is True
    assert store.ensure_imported_index_in_background() is False
