"""What one checkout of the main database can do, and what it leaves for the next.

A read connection opened `mode=ro` protects only the main file: ATTACH brings
in another one, writable. A function, collation, TEMP table or pragma set on a
pooled connection outlives the checkout that set it. And the registry of
databases kept every file a process ever opened.
"""

import gc
import re
import sqlite3
import threading
import time
from pathlib import Path

import pytest

import one_memory
from one_memory import database_access
from one_memory.database_access import close_main_databases, main_database


@pytest.fixture(autouse=True)
def _closed_afterwards():
    yield
    close_main_databases()


def _database(tmp_path: Path, name: str = "one-memory.sqlite3") -> Path:
    path = tmp_path / name
    with main_database(path).write() as db, db:
        db.execute("CREATE TABLE notes (body TEXT)")
    return path


@pytest.mark.parametrize("kind", ["read", "write"])
def test_no_checkout_can_attach_another_database(tmp_path, kind):
    path = _database(tmp_path)
    other = tmp_path / "other.sqlite3"
    checkout = getattr(main_database(path), kind)
    with checkout() as db, pytest.raises(sqlite3.Error):
        db.execute("ATTACH DATABASE ? AS other", (str(other),))
        db.execute("CREATE TABLE other.stolen (x)")
    assert not other.exists()


@pytest.mark.parametrize("handed_back_before", [False, True])
def test_a_reader_cannot_write_even_temporary_tables(tmp_path, handed_back_before):
    path = _database(tmp_path)
    database = main_database(path)
    if handed_back_before:
        with database.read() as db:
            first = id(db)
    with database.read() as db:
        assert not handed_back_before or id(db) == first, "must be the pooled one again"
        with pytest.raises(sqlite3.OperationalError):
            db.execute("CREATE TEMP TABLE scratch (x)")


def test_the_writer_may_still_use_temporary_tables_within_its_checkout(tmp_path):
    path = _database(tmp_path)
    with main_database(path).write() as db:
        db.execute("CREATE TEMP TABLE scratch (x)")
        db.execute("INSERT INTO scratch VALUES (1)")
        assert db.execute("SELECT x FROM scratch").fetchone() == (1,)


def _leave_function(db: sqlite3.Connection) -> None:
    database_access.register_function(db, "left_behind", 0, lambda: 1)


def _use_function(db: sqlite3.Connection) -> None:
    db.execute("SELECT left_behind()").fetchone()


def _leave_collation(db: sqlite3.Connection) -> None:
    database_access.register_collation(db, "left_behind", lambda a, b: 0)


def _use_collation(db: sqlite3.Connection) -> None:
    db.execute("SELECT 'a' < 'b' COLLATE left_behind").fetchone()


def _leave_temp_table(db: sqlite3.Connection) -> None:
    db.execute("CREATE TEMP TABLE left_behind (x)")


def _use_temp_table(db: sqlite3.Connection) -> None:
    db.execute("SELECT * FROM temp.left_behind").fetchall()


LEFTOVERS = {
    "function": (_leave_function, _use_function, ("read", "write")),
    "collation": (_leave_collation, _use_collation, ("read", "write")),
    "temp table": (_leave_temp_table, _use_temp_table, ("write",)),
}


@pytest.mark.parametrize(
    ("kind", "leftover"),
    [(kind, name) for name, (_, _, kinds) in LEFTOVERS.items() for kind in kinds],
)
def test_what_a_checkout_registers_does_not_reach_the_next(tmp_path, kind, leftover):
    leave, use, _ = LEFTOVERS[leftover]
    path = _database(tmp_path)
    database = main_database(path)
    with getattr(database, kind)() as db:
        leave(db)
        use(db)
    with getattr(database, kind)() as db, pytest.raises(sqlite3.OperationalError):
        use(db)


def test_a_function_registered_twice_is_the_later_one_and_both_go(tmp_path):
    path = _database(tmp_path)
    database = main_database(path)
    with database.read() as db:
        database_access.register_function(db, "twice", 0, lambda: 1)
        database_access.register_function(db, "twice", 0, lambda: 2)
        assert db.execute("SELECT twice()").fetchone() == (2,)
    with database.read() as db, pytest.raises(sqlite3.OperationalError):
        db.execute("SELECT twice()").fetchone()


REGISTERS = re.compile(r"\.create_(function|collation|aggregate|window_function)\(")


def test_only_the_access_layer_registers_on_a_connection():
    # Anything registered straight on a pooled connection outlives the checkout;
    # the access layer's helpers record it so the connection is handed back
    # without it.
    source = Path(one_memory.__file__).parent
    assert [
        f"{path.relative_to(source)}:{n}"
        for path in sorted(source.rglob("*.py"))
        if path.name != "database_access.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if REGISTERS.search(line)
    ] == []


PRAGMAS = {
    "synchronous": "OFF",
    "cache_size": "7",
    "temp_store": "MEMORY",
    "recursive_triggers": "ON",
    "automatic_index": "OFF",
    "cell_size_check": "ON",
    "ignore_check_constraints": "ON",
    "reverse_unordered_selects": "ON",
    "trusted_schema": "OFF",
    "writable_schema": "ON",
    "legacy_alter_table": "ON",
}


@pytest.mark.parametrize("kind", ["read", "write"])
@pytest.mark.parametrize("pragma", sorted(PRAGMAS))
def test_a_pragma_one_checkout_sets_is_gone_for_the_next(tmp_path, kind, pragma):
    path = _database(tmp_path)
    database = main_database(path)
    with getattr(database, kind)() as db:
        (before,) = db.execute(f"PRAGMA {pragma}").fetchone()
        db.execute(f"PRAGMA {pragma} = {PRAGMAS[pragma]}")
        (changed,) = db.execute(f"PRAGMA {pragma}").fetchone()
        assert changed != before, "the scenario must actually change something"
    with getattr(database, kind)() as db:
        assert db.execute(f"PRAGMA {pragma}").fetchone() == (before,)


def _tracked(tmp_path: Path) -> int:
    """How many access points for this test's files the process still keeps."""
    gc.collect()
    registries = [database_access._databases, getattr(database_access, "_alive", {})]
    return len(
        {
            key
            for registry in registries
            for key in list(registry.keys())
            if key.is_relative_to(tmp_path.resolve())
        }
    )


def test_databases_no_longer_used_leave_the_registry(tmp_path):
    close_main_databases()
    kept = database_access._KEPT_OPEN
    for n in range(3 * kept):
        _database(tmp_path, f"db-{n}.sqlite3")
    assert _tracked(tmp_path) <= kept


def test_closing_them_all_empties_the_registry(tmp_path):
    for n in range(3):
        _database(tmp_path, f"db-{n}.sqlite3")
    close_main_databases()
    assert _tracked(tmp_path) == 0


def test_a_retired_database_still_in_use_is_not_opened_twice(tmp_path):
    held = _database(tmp_path, "held.sqlite3")
    database = main_database(held)
    inside, leave = threading.Event(), threading.Event()

    def hold() -> None:
        with database.write():
            inside.set()
            leave.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert inside.wait(5)
        for n in range(3 * database_access._KEPT_OPEN):
            _database(tmp_path, f"db-{n}.sqlite3")
        assert main_database(held) is database
    finally:
        leave.set()
        holder.join()


def test_handing_a_reader_back_does_not_wait_out_someone_holding_the_file(tmp_path):
    # Checking how a connection comes back must not itself wait for a lock:
    # one that never loaded the schema needs the file to answer even that.
    path = tmp_path / "one-memory.sqlite3"
    other = sqlite3.connect(path, isolation_level=None)
    try:
        other.execute("CREATE TABLE notes (body TEXT)")
        other.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        with main_database(path).read():
            pass
        assert time.monotonic() - started < 1.0
    finally:
        other.close()


def test_opening_the_writer_waits_no_longer_than_its_caller_allows(tmp_path):
    # A file not yet in WAL, held by someone else: switching it waits for
    # them. That wait is the caller's to set, like any other.
    path = tmp_path / "one-memory.sqlite3"
    other = sqlite3.connect(path, isolation_level=None)
    try:
        other.execute("CREATE TABLE notes (body TEXT)")
        other.execute("BEGIN EXCLUSIVE")
        started = time.monotonic()
        with (
            pytest.raises(sqlite3.OperationalError),
            main_database(path).write(busy_timeout_ms=300),
        ):
            pass
        assert time.monotonic() - started < 2.0
    finally:
        other.close()
