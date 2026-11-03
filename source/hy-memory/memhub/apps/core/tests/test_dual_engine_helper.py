"""Tests for the dual-engine harness itself.

The harness exists so a migrated module is proven on **both** engines. Its
single most important property is that a missing MySQL is a *failure*, not a
skip — a skip would let the suite go green while the MySQL half never ran,
which is the exact false green the harness was built to prevent.

These tests pin that property so it cannot be quietly relaxed later.
"""

from __future__ import annotations

import pytest

import tests.dual_engine as dual


def test_sqlite_engine_is_always_available(tmp_path) -> None:
    """SQLite is the engine in force today; it must never be the skipped one."""
    with dual.sqlite_engine(tmp_path / "probe.sqlite3") as handle:
        assert handle.kind == "sqlite"
        assert handle.available is True


def test_run_sqlite_round_trips_a_value(tmp_path) -> None:
    with dual.sqlite_engine(tmp_path / "q.sqlite3") as handle:
        dual.run_sqlite(handle, "CREATE TABLE t (v TEXT)")
        dual.run_sqlite(handle, "INSERT INTO t VALUES ('ok')")
        assert dual.run_sqlite(handle, "SELECT v FROM t") == [("ok",)]


def test_mysql_missing_raises_instead_of_skipping(monkeypatch) -> None:
    """A skip would downgrade 'verified on both' to 'verified on SQLite'."""
    monkeypatch.setattr(dual, "_mysql_reachable", lambda: False)

    with pytest.raises(RuntimeError, match="not reachable"), dual.mysql_engine():
        pass


def test_mysql_missing_can_be_opted_into_only_explicitly(monkeypatch) -> None:
    """`optional=True` must be a visible call-site decision, not a default."""
    monkeypatch.setattr(dual, "_mysql_reachable", lambda: False)

    with dual.mysql_engine(optional=True) as handle:
        assert handle.kind == "mysql"
        assert handle.available is False


def test_mysql_reachable_never_raises() -> None:
    """The probe is used by the harness; it must report, not throw."""
    assert isinstance(dual._mysql_reachable(), bool)
