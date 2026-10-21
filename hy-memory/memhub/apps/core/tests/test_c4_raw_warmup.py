from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from one_memory.context_v2_coordinator import warm_raw_read_path
from one_memory.imports.storage import SCHEMA as EVIDENCE_SCHEMA

try:
    from one_memory.imports.storage import SEARCH_SCHEMA
except ImportError:  # pragma: no cover - older schema module shape
    SEARCH_SCHEMA = ""


@pytest.fixture
def evidence_db(tmp_path):
    path = tmp_path / "warm.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(EVIDENCE_SCHEMA + SEARCH_SCHEMA)
        db.execute(
            """INSERT INTO evidence
            (evidence_id,idempotency_key,user_id,source_id,conversation_id,message_id,
             source_ordinal,content_kind,role,written_by,created_at,verbatim,content_hash,
             revision,imported_at,updated_at,ingest_seq)
            VALUES('raw-1','idem-1','local','codex','t','m','1','raw_conversation',
             'user','person','2026-09-28T00:00:00+00:00','warm body','h1',1,
             '2026-09-28T00:00:00+00:00','2026-09-28T00:00:00+00:00',1)"""
        )
    return path


def _tables(path) -> set[str]:
    with closing(sqlite3.connect(path)) as db:
        return {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }


def _evidence_count(path) -> int:
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT count(*) FROM evidence").fetchone()[0]


def test_warm_raw_read_path_is_side_effect_free(evidence_db):
    before_tables = _tables(evidence_db)
    before_rows = _evidence_count(evidence_db)
    assert warm_raw_read_path(evidence_db) is True
    assert _tables(evidence_db) == before_tables, "warm-up must not create tables"
    assert _evidence_count(evidence_db) == before_rows, "warm-up must not write Evidence"
    assert "call_events" not in _tables(evidence_db)


def test_warm_raw_read_path_tolerates_missing_fts_index(tmp_path):
    path = tmp_path / "no-fts.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE evidence (rowid INTEGER PRIMARY KEY, verbatim TEXT)")
        db.execute("INSERT INTO evidence(rowid, verbatim) VALUES (1, 'x')")
    assert warm_raw_read_path(path) is True


@pytest.mark.parametrize("case", ["missing", "corrupt", "directory", "tiny_timeout"])
def test_warm_raw_read_path_never_raises_or_blocks_startup(tmp_path, case):
    """C5's contract: a False/failed warm-up must not make Core fail to start."""
    if case == "missing":
        target = tmp_path / "missing.sqlite3"
        assert warm_raw_read_path(target) is False
    elif case == "corrupt":
        target = tmp_path / "corrupt.sqlite3"
        target.write_bytes(b"not a sqlite database")
        assert warm_raw_read_path(target) is False
    elif case == "directory":
        target = tmp_path / "adir"
        target.mkdir()
        assert warm_raw_read_path(target) is False
    else:
        target = tmp_path / "tiny.sqlite3"
        with closing(sqlite3.connect(target)):
            pass
        assert warm_raw_read_path(target, timeout_ms=1) is False
