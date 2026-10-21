"""The ordering index must actually carry `evidence_id`, not just look like it does.

C8's mutation audit (O-9) found a false guard: removing `evidence_id` from
`evidence_imported_index` left every related test green. The index exists for
`list_recent_conversations`' ORDER BY imported_at DESC, evidence_id DESC — without
the second column SQLite can still use it, so row counts and ordering in small
tests hide the difference. This asserts the shape directly and on the real DDL
path, so the mutation turns red.
"""

import sqlite3
import time

import pytest

from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.migrations import evidence_ddl

INDEX = "evidence_imported_index"


def _index_sql(dialect: str) -> str | None:
    ddl = evidence_ddl(dialect)
    for statement in ddl.split(";"):
        if INDEX in statement:
            return statement.strip()
    return None


@pytest.mark.parametrize("dialect", ["sqlite", "mysql"])
def test_the_ordering_index_includes_evidence_id(dialect):
    statement = _index_sql(dialect)
    assert statement is not None, f"{INDEX} must be declared for {dialect}"
    assert "evidence_id" in statement, (
        f"{INDEX} must carry evidence_id; without it the ORDER BY tie-break is lost"
    )
    assert "imported_at" in statement


def test_an_opened_database_has_the_full_index(tmp_path):
    """Asserted on a real database, not only on the DDL text."""
    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    # The index is built off the startup path on purpose (9.28s on 432k rows), so
    # it is not there the instant the store opens. Wait for the real lifecycle.
    assert store.ensure_imported_index_in_background() is True
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not store.has_imported_index():
        time.sleep(0.02)
    assert store.has_imported_index(), "the background build must finish"
    with sqlite3.connect(database) as connection:
        rows = list(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (INDEX,)
            )
        )
        duplicates = list(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE ?",
                (f"{INDEX}%",),
            )
        )
    assert rows, f"{INDEX} must exist after opening the store"
    assert len(duplicates) == 1, "the index must not be declared twice"
    assert "evidence_id" in (rows[0][0] or ""), "the created index must include evidence_id"


def test_the_index_is_used_for_the_imported_order(tmp_path):
    """Plan-level check: the query must reach for the index, not scan the table."""
    database = tmp_path / "core.sqlite3"
    store = EvidenceStore(database)
    store._build_imported_index()
    with sqlite3.connect(database) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT evidence_id FROM evidence "
            "WHERE user_id='local' ORDER BY imported_at DESC, evidence_id DESC"
        ).fetchall()
    joined = " ".join(row[-1] for row in plan)
    assert INDEX in joined, f"expected the ordering index in the plan, got: {joined}"
    assert "SCAN" not in joined.upper(), f"the query should not scan: {joined}"
