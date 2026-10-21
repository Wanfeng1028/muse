import hashlib
import sqlite3
import time
from contextlib import closing

import pytest

from one_memory.database_access import close_main_databases, main_database
from one_memory.home_summary import read_home_summary
from one_memory.memory_governance import MemoryStatus
from one_memory.memory_library import read_memory_library
from one_memory.source_read_access import SourceReadAccess
from tests.test_memory_library import NOW, grant, put
from tests.test_memory_library import database as database  # noqa: F401

NEWER = "2026-09-19T02:00:00+00:00"


def assert_aligned(database, *, count, latest, sources=(), user_id="local"):
    home = read_home_summary(database, user_id=user_id)
    library = read_memory_library(database, user_id=user_id, status=MemoryStatus.CONFIRMED)
    assert home.memory_count == library.total == count
    if latest is None:
        assert home.latest is None and library.items == []
        return home
    assert home.latest is not None
    memory = library.items[0]
    assert home.latest.memory_id == memory.memory_id == latest
    assert home.latest.content == memory.content[:320]
    assert home.latest.truncated == (len(memory.content) > 320)
    assert home.latest.updated_at == memory.updated_at
    assert home.latest.revision == memory.revision
    with closing(sqlite3.connect(database)) as db:
        evidence_sources = {
            row[0]
            for evidence_id in memory.evidence_ids
            for row in db.execute(
                "SELECT source_id FROM evidence WHERE evidence_id=? AND user_id=?",
                (evidence_id, user_id),
            )
        }
    assert home.latest.source_ids == tuple(sorted(evidence_sources)) == sources
    return home


@pytest.mark.parametrize("bad_link", ["missing-evidence", "other-e"])
@pytest.mark.parametrize("mixed", [False, True])
def test_bad_active_link_excludes_whole_latest_memory(database, bad_link, mixed):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE evidence SET source_id='foreign-only' WHERE evidence_id='other-e'")
        put(db, "valid")
        put(db, "invalid", time=NEWER, links=("e1", bad_link) if mixed else (bad_link,))
    assert_aligned(database, count=1, latest="valid", sources=("cursor",))


@pytest.mark.parametrize("bad_link", ["missing-evidence", "other-e"])
def test_bad_inactive_link_does_not_hide_memory_or_enter_source_set(database, bad_link):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE evidence SET source_id='foreign-only' WHERE evidence_id='other-e'")
        put(db, "latest", links=("e3", "e2", "e1", bad_link), content="x" * 321)
        db.execute("UPDATE governed_memory_evidence SET active=0 WHERE evidence_id=?", (bad_link,))
    assert_aligned(database, count=1, latest="latest", sources=("cursor", "workbuddy"))


def test_other_user_memory_and_grant_are_isolated(database):
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "local")
        put(db, "foreign", user="other", time=NEWER, links=("other-e",))
        grant(db, "cursor", user="other")
    assert_aligned(database, count=1, latest="local", sources=("cursor",))
    assert_aligned(database, count=0, latest=None, user_id="other")
    with closing(sqlite3.connect(database)) as db, db:
        grant(db, "cursor", user="other", revoked=None)
    assert_aligned(database, count=1, latest="foreign", sources=("cursor",), user_id="other")


def test_mixed_revocation_matches_source_read_access_and_inactive_citations(database):
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "valid")
        put(db, "mixed", time=NEWER, links=("e1", "e2", "e3"))
    before = read_memory_library(database, status=MemoryStatus.CONFIRMED)
    assert_aligned(database, count=2, latest="mixed", sources=("cursor", "workbuddy"))
    with closing(sqlite3.connect(database)) as db, db:
        grant(db, "workbuddy")
    assert [item.memory_id for item in SourceReadAccess(database).memories(before.items)] == [
        "valid"
    ]
    assert_aligned(database, count=1, latest="valid", sources=("cursor",))
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("UPDATE governed_memory_evidence SET active=0 WHERE evidence_id='e2'")
    assert_aligned(database, count=2, latest="mixed", sources=("cursor",))


def test_empty_library_invalid_only_and_no_active_citations_are_distinct(database):
    assert_aligned(database, count=0, latest=None)
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "invalid", links=("missing-evidence",))
    assert_aligned(database, count=0, latest=None)
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "no-links", time=NEWER, links=())
        put(db, "inactive-only", links=("other-e",))
        db.execute("UPDATE governed_memory_evidence SET active=0 WHERE memory_id='inactive-only'")
    assert_aligned(database, count=2, latest="no-links", sources=())


def test_full_confirmed_corpus_count_and_stable_latest_ignore_invalid_newer_rows(database):
    with closing(sqlite3.connect(database)) as db, db:
        for index in reversed(range(1001)):
            put(db, f"valid-{index:04d}")
        for index in range(503):
            put(db, f"bad-{index:04d}", time=NEWER, links=("e1", "missing-evidence"))
        put(db, "superseded", status="superseded", time=NEWER)
        put(db, "deleted", status="deleted", deleted=NOW, time=NEWER)
        put(db, "tombstone", deleted=NOW, time=NEWER)
    assert_aligned(database, count=1001, latest="valid-0000", sources=("cursor",))


def test_summary_remains_readonly_and_does_not_repair_broken_links(database, monkeypatch):
    with closing(sqlite3.connect(database)) as db, db:
        put(db, "valid")
        put(db, "bad", time=NEWER, links=("missing-evidence",))
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    connect = sqlite3.connect
    opened, statements = [], []
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_TRANSACTION,
    }

    def open_readonly(database_uri, **kwargs):
        assert database_uri.endswith("?mode=ro") and kwargs["uri"] is True
        db = connect(database_uri, **kwargs)
        db.set_authorizer(
            # The access layer makes its readers query_only as well.
            lambda action, name, *_: (
                sqlite3.SQLITE_OK
                if action in allowed or (action == sqlite3.SQLITE_PRAGMA and name == "query_only")
                else sqlite3.SQLITE_DENY
            )
        )
        db.set_trace_callback(statements.append)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", open_readonly)
    summary = read_home_summary(database)
    assert summary.memory_count == 1 and summary.latest.memory_id == "valid"
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert len(opened) == 1
    assert len([sql for sql in statements if sql.lstrip().startswith("SELECT")]) == 4
    assert all(
        sql.lstrip().startswith(("BEGIN", "SELECT", "PRAGMA query_only = ON")) for sql in statements
    )
    # Pooled: handed back rather than held, and closed with the pool.
    assert main_database(database).stats().readers_in_use == 0
    close_main_databases()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_totals_skip_per_row_freshness_and_page_rows_stay_fresh(database, monkeypatch):
    """App-facing totals must not run the per-row freshness UDF.

    The homepage and memory-page totals scale with the whole library when the
    freshness predicate is in the COUNT; at 2500 rows that alone can burn the
    whole five-second budget. Totals now count with the cheap permission
    filters only (small drift allowed, shown as a plain number). The rows that
    are actually displayed are still checked row by row, and host-facing reads
    keep the full filtering unchanged.
    """
    with closing(sqlite3.connect(database)) as db, db:
        for index in range(2500):
            put(db, f"valid-{index:04d}")
        # One memory whose evidence has been rewritten: the freshness UDF
        # would hide it. The total may drift by it; the page rows must not
        # include it.
        put(db, "stale", time=NEWER, links=("e1",))
        db.execute(
            "UPDATE evidence SET verbatim='rewritten' WHERE evidence_id='e1' "
            "AND evidence_id NOT IN (SELECT evidence_id FROM governed_memory_evidence "
            "WHERE memory_id!='stale')"
        )

    started = time.monotonic()
    home = read_home_summary(database)
    elapsed = time.monotonic() - started
    # Total counts the cheap way: 2500 confirmed memories, plus the stale one
    # whose proof no longer matches (drift allowed by product decision).
    assert home.memory_count in (2500, 2501), home.memory_count
    assert elapsed < 2, f"homepage took {elapsed:.2f}s"


def test_interrupted_read_does_not_poison_the_pooled_connection(database, monkeypatch):
    """One timed-out home request must not turn every later request into a 503.

    The read bounds itself with a progress handler built from a deadline. The
    handler must be cleared when the read gives up, or the pooled connection
    comes back still armed and every later request is interrupted from its
    first statement -- the 503 storm.
    """
    calls = {"n": 0}

    with closing(sqlite3.connect(database)) as db, db:
        put(db, "one")

    # A read that raises must still clear the handler it installed.
    def first_read_fails(db):
        calls["n"] += 1
        raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr("one_memory.home_summary.register_memory_freshness", first_read_fails)
    with pytest.raises(sqlite3.OperationalError):
        read_home_summary(database)
    # The finally must have cleared the poisoned handler before handback.
    monkeypatch.undo()
    close_main_databases()

    # The next request lands on the pool; it must succeed.
    assert read_home_summary(database).memory_count == 1
    assert calls["n"] == 1


def test_count_latest_and_source_set_share_snapshot_during_link_change(database, monkeypatch):
    connect = sqlite3.connect
    with closing(connect(database)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        put(db, "older")
        put(db, "latest", time=NEWER, links=("e1", "e2"))
    changes, transactions = [], []

    class ConcurrentConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            cursor = super().execute(sql, parameters)
            if sql.lstrip().startswith("SELECT"):
                transactions.append(self.in_transaction)
            if "COUNT(*)" in sql and not changes:
                with closing(connect(database)) as writer, writer:
                    writer.execute(
                        "INSERT INTO governed_memory_evidence VALUES ('latest','other-e',1)"
                    )
                    writer.execute("UPDATE evidence SET source_id='changed' WHERE evidence_id='e2'")
                changes.append(True)
            return cursor

    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: connect(*args, **kwargs, factory=ConcurrentConnection),
    )
    home = read_home_summary(database)
    assert home.memory_count == 2
    assert home.latest.memory_id == "latest"
    assert home.latest.source_ids == ("cursor", "workbuddy")
    assert changes == [True] and transactions == [True, True, True, True]
    monkeypatch.setattr(sqlite3, "connect", connect)
    assert_aligned(database, count=1, latest="older", sources=("cursor",))
