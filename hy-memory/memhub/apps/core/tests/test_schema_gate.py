import sqlite3

import pytest

from one_memory.schema_gate import BUILD_SCHEMA_VERSION, SchemaTooNewError, guard_schema_version


def test_fresh_database_records_the_build_schema(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"

    assert guard_schema_version(path) == BUILD_SCHEMA_VERSION
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == (
            BUILD_SCHEMA_VERSION
        )


def test_future_schema_refuses_to_open(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT)"
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?,?,?)",
            (BUILD_SCHEMA_VERSION + 1, "future", "2026-09-29T00:00:00+00:00"),
        )

    with pytest.raises(SchemaTooNewError) as caught:
        guard_schema_version(path)

    assert caught.value.code == "database_schema_too_new"
    assert caught.value.found == BUILD_SCHEMA_VERSION + 1


def test_legacy_database_without_a_ledger_is_left_untouched(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE governed_memories (memory_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO evidence VALUES ('kept')")

    assert guard_schema_version(path) == 0
    with sqlite3.connect(path) as connection:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master")}
        assert "schema_migrations" not in tables
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("kept",)]
