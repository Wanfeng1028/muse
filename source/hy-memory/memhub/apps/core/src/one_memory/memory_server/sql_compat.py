"""The small compatibility layer for running one statement on either engine.

Extracted because the same three questions come up at every migrated call site
and answering them inline means every module grows its own slightly different
version — which is how a migration ends up unmaintainable.

The three questions:

1. **Is this the MySQL store?** Answered by asking the store, not a global.
2. **How do I run a statement?** On SQLite, `execute` is synchronous. On MySQL,
   the facade hands back a connection whose `execute` is async, so statements
   run on the facade's loop while the caller stays synchronous.
3. **How do I read the affected-row count?** `rowcount` exists on both, but
   MySQL's meaning differs for `INSERT IGNORE` (0 when the row was ignored).

Placeholders (`?` vs `%s`) are deliberately NOT translated here. Silently
rewriting SQL would hide which dialect a string was written for, and would fail
the moment a literal contained a question mark. Call sites keep two named
constants instead; that is more text but it is honest about the difference.
"""

from __future__ import annotations

import asyncio
from typing import Any


def is_mysql(store: Any) -> bool:
    """Whether the bound store is the MySQL one.

    Asked of the store rather than read from a global, because during the
    migration both engines can be in play in one process and a global would
    make the answer depend on whichever was resolved last.
    """
    from one_memory.memory_server.sync_facade import SyncStoreFacade

    return isinstance(store, SyncStoreFacade)


def execute(
    connection: Any,
    mysql: bool,
    sql: str,
    params: tuple[Any, ...] = (),
) -> Any:
    """Run one statement, returning something with `fetch*`/`rowcount`."""
    if mysql:
        return _AsyncResult(_run_on_loop(connection, sql, params))
    return connection.execute(sql, params)


def execute_script(connection: Any, mysql: bool, script: str) -> None:
    """Run a multi-statement script.

    Exists because `executescript` is a sqlite3 convenience with no MySQL
    counterpart: it commits any pending transaction first, then runs everything.
    On MySQL the script is split and each statement sent separately, which is
    what the driver requires — it will not accept several statements in one call.

    Splitting must therefore be done with the migration's own splitter so the
    two engines agree on where statements end.
    """
    if mysql:
        from one_memory.memory_server.migrations import _split_statements

        for statement in _split_statements(script):
            execute(connection, True, statement)
        return
    connection.executescript(script)


def _run_on_loop(connection: Any, sql: str, params: tuple[Any, ...]) -> Any:
    async def _query() -> Any:
        async with connection.cursor() as cursor:
            await cursor.execute(sql, params)
            # `rowcount` must be read here: it describes the statement just run
            # and is invalidated by the next one (and by fetching).
            affected = cursor.rowcount
            try:
                rows = await cursor.fetchall()
            except Exception:
                rows = None
            return rows, affected

    loop = getattr(connection, "_loop", None)
    if loop is None:
        raise RuntimeError("MySQL connection has no event loop to run the statement on")
    return asyncio.run_coroutine_threadsafe(_query(), loop).result(timeout=30)


class _AsyncResult:
    """The surface call sites use: `fetchone`, `fetchall`, `rowcount`."""

    def __init__(self, result: Any) -> None:
        rows, affected = result
        self._rows = rows or []
        #: Taken from the cursor, not from `len(rows)`: an INSERT fetches no
        #: rows, so deriving it from the result would report 0 for a statement
        #: that changed one row — and `rowcount == 1` is exactly how claim
        #: tests decide a winner.
        self.rowcount = affected

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> Any:
        return self._rows


def rowcount(result: Any, mysql: bool) -> int:
    """Affected rows, comparable across engines for the `== 1` claim test."""
    return int(getattr(result, "rowcount", 0) or 0)


def row_to_dict(row: Any, columns: tuple[str, ...], mysql: bool) -> dict[str, Any]:
    """A mapping for a row, from either a `sqlite3.Row` or a MySQL tuple.

    SQLite rows answer to `row["name"]`; MySQL returns a bare tuple with no
    names. The caller supplies the column order — which the SELECT should state
    explicitly, since `SELECT *` would make the order implicit and fragile.

    Timestamps stay as whatever the engine returned: a caller that needs a
    `datetime` handles the string/`datetime` difference itself (see
    `onboarding._as_datetime`), because only it knows the field's type.
    """
    if isinstance(row, dict):
        return dict(row)
    if not mysql:
        try:
            return dict(row)
        except (TypeError, ValueError):
            pass
    values = tuple(row)
    return dict(zip(columns, values, strict=False))
