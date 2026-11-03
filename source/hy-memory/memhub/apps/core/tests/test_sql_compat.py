"""The shared compatibility layer, especially `rowcount`.

`rowcount` is where the migration bites hardest: `rowcount == 1` is how claim
tests decide a winner, so a wrong value silently elects the wrong caller.
Deriving it from fetched rows would report 0 for every INSERT — an INSERT
returns no rows — and that bug is invisible on a SELECT-only test suite.
"""

from __future__ import annotations

from one_memory.memory_server.sql_compat import _AsyncResult, is_mysql, rowcount


def test_rowcount_comes_from_the_cursor_not_from_rows() -> None:
    """An INSERT fetches no rows but still affected one."""
    result = _AsyncResult(([], 1))

    assert result.rowcount == 1
    assert result.fetchall() == []
    assert result.fetchone() is None


def test_a_skipped_insert_reports_zero() -> None:
    """`INSERT IGNORE` that skipped the row must report 0, not 1."""
    assert _AsyncResult(([], 0)).rowcount == 0


def test_rowcount_helper_reads_the_attribute() -> None:
    class Fake:
        rowcount = 3

    assert rowcount(Fake(), mysql=False) == 3
    assert rowcount(object(), mysql=False) == 0


def test_is_mysql_is_false_for_a_plain_object() -> None:
    """Asked of the store, so an unrelated object is simply not MySQL."""
    assert is_mysql(object()) is False
