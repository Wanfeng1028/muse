"""A2: which store is in force, and honest reporting of it."""

from __future__ import annotations

import pytest

from one_memory.memory_server.store_binding import (
    ENGINE_ENV,
    MYSQL,
    MYSQL_ENABLED,
    SQLITE,
    degradation_note,
    mysql_available,
    resolve_engine,
    status_line,
    store_for,
)


def test_d56_mysql_kill_switch_stays_off_until_cleanup_is_authorized() -> None:
    """D56 is a decision, not a comment: re-enabling MySQL must be a red test.

    C8 verified that flipping the *implementation branch* is caught. This
    guard is narrower and complements it: the module-level authority itself
    must remain disabled while the code/tests/dependency deletion is still
    waiting for Captain approval. A future accidental toggle therefore fails
    in the default suite, before any MySQL driver is imported.
    """
    assert MYSQL_ENABLED is False
    assert resolve_engine({ENGINE_ENV: MYSQL}).engine == SQLITE


def test_sqlite_is_the_default() -> None:
    """MySQL cannot be default until the bundled server can start."""
    binding = resolve_engine({})
    assert binding.engine == SQLITE
    assert binding.fell_back is False


def test_requesting_mysql_stays_on_sqlite_under_d56() -> None:
    binding = resolve_engine({ENGINE_ENV: MYSQL, "ONE_MEMORY_DATA_DIR": "/nonexistent-om"})
    assert binding.engine == SQLITE
    assert binding.fell_back is True
    assert "D56" in binding.reason


def test_an_unrecognised_engine_falls_back_not_crashes() -> None:
    binding = resolve_engine({ENGINE_ENV: "postgres"})
    assert binding.engine == SQLITE
    assert binding.fell_back is True


def test_explicit_sqlite_is_not_a_fallback() -> None:
    binding = resolve_engine({ENGINE_ENV: SQLITE})
    assert binding.engine == SQLITE
    assert binding.fell_back is False


def test_engine_name_is_case_insensitive() -> None:
    assert resolve_engine({ENGINE_ENV: "SQLite"}).engine == SQLITE


def test_mysql_availability_is_checked_not_assumed() -> None:
    """A claimed MySQL with no server fails at first query, far from the cause."""
    assert mysql_available({"ONE_MEMORY_DATA_DIR": "/nonexistent-om"}) is False


def test_status_line_names_the_engine() -> None:
    assert status_line({}).startswith(f"store: {SQLITE}")


def test_status_line_admits_a_fallback() -> None:
    """A status line that says 'mysql' while running SQLite is a lie."""
    line = status_line({ENGINE_ENV: MYSQL, "ONE_MEMORY_DATA_DIR": "/nonexistent-om"})
    assert "fell back" in line
    assert SQLITE in line


@pytest.mark.parametrize("value", ["", "   ", SQLITE])
def test_blank_engine_means_the_default(value: str) -> None:
    assert resolve_engine({ENGINE_ENV: value}).engine == SQLITE


def test_store_for_returns_sqlite_by_default(tmp_path) -> None:
    """The accessor must work today, on the engine that is actually in force."""
    store = store_for(tmp_path / "one-memory.sqlite3", {})
    assert store is not None


def test_store_for_is_the_same_object_for_one_path(tmp_path) -> None:
    """One accessor, one store per path: two shapes coexisting is the drift
    the port exists to prevent."""
    path = tmp_path / "one-memory.sqlite3"
    assert store_for(path, {}) is store_for(path, {})


def test_mysql_path_is_disabled_under_d56(monkeypatch) -> None:
    """D56: the database is SQLite; MySQL must NOT run alongside it.

    The objective forbids two engines at once, so even with the env set to
    `mysql` the accessor returns the SQLite store, rather than silently
    starting a second engine.
    """
    from one_memory.database_access import MainDatabase

    monkeypatch.setattr(
        "one_memory.memory_server.store_binding.mysql_available", lambda env=None: True
    )

    store = store_for("/unused.sqlite3", {ENGINE_ENV: MYSQL})

    assert isinstance(store, MainDatabase), "MySQL is disabled under D56"
    binding = resolve_engine({ENGINE_ENV: MYSQL})
    assert binding.engine == SQLITE and binding.fell_back


def test_store_for_has_no_reachable_mysql_branch(monkeypatch) -> None:
    """D56: no switch should be able to start a second engine.

    The previous facade round-trip test pinned a branch that remained
    reachable if `MYSQL_ENABLED` were flipped. The objective forbids a second
    engine, so the branch is removed outright; this guard makes a future
    re-introduction fail in the default suite.
    """
    monkeypatch.setattr(
        "one_memory.memory_server.store_binding.mysql_available", lambda env=None: True
    )
    monkeypatch.setattr(
        "one_memory.memory_server.store_binding.MYSQL_ENABLED",
        True,
        raising=False,
    )

    store = store_for("/unused.sqlite3", {ENGINE_ENV: MYSQL})

    assert store.__class__.__name__ == "MainDatabase"
    assert not hasattr(store, "connect"), "MySQL facade must not be constructed"


def test_degradation_note_is_empty_when_nothing_fell_back() -> None:
    assert degradation_note({}) == ""


def test_degradation_note_says_which_engine_is_actually_in_force() -> None:
    """A silent downgrade is the failure mode: the user asked for MySQL and
    'it works' is not the same as 'it is what you asked for'."""
    note = degradation_note({ENGINE_ENV: MYSQL})
    assert note, "requesting MySQL without a server must be reported"
    assert SQLITE in note
    assert "not the one requested" in note
