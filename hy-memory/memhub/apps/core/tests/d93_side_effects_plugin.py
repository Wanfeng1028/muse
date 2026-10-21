"""D93 test 3: inventory every database write a Reader-bound read route makes.

Plan `读写隔离方案-20261009.html` section 5 (B) and section 8 row 3. The Reader
opens the library `mode=ro` + `query_only`, so any write a read route makes
today will fail there. Instead of a manual audit, run the existing route tests
with this plugin loaded; it records, per route, every INSERT / UPDATE / DELETE /
DDL that happens while that route is being served, with the one_memory frames
that issued it. Recording only, nothing is blocked, so one run lists them all.

    bash /private/tmp/wb-d76-pytest.sh -p tests.d93_side_effects_plugin \
        tests/test_home_summary.py tests/test_memory_library_api.py ...

The report goes to $ONE_MEMORY_D93_SIDE_EFFECTS (default
`d93-side-effects.json` in the pytest root) and a summary is printed at the end.
Writes outside a request (fixture setup, background tasks) are not counted.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import sqlite3
import traceback
from collections import defaultdict
from pathlib import Path

#: The routes the Reader takes over (plan section 5, B, reader_app.py row).
READER_ROUTES = {
    ("GET", "/api/v1/home-summary"),
    ("GET", "/api/v1/memory-library"),
    ("GET", "/api/v1/memories"),
    ("GET", "/api/v1/memories/{memory_id}"),
    ("GET", "/api/v1/memories/graph"),
    ("POST", "/api/v1/context/search"),
    ("GET", "/api/v1/context/search"),
    ("POST", "/api/v1/recall"),
    ("GET", "/api/v1/conversations/search"),
    ("POST", "/api/v1/conversations/search"),
    ("GET", "/api/v1/health"),
    ("GET", "/health"),
}

_WRITES = {
    sqlite3.SQLITE_INSERT: "INSERT",
    sqlite3.SQLITE_UPDATE: "UPDATE",
    sqlite3.SQLITE_DELETE: "DELETE",
    sqlite3.SQLITE_CREATE_TABLE: "CREATE TABLE",
    sqlite3.SQLITE_CREATE_INDEX: "CREATE INDEX",
    sqlite3.SQLITE_CREATE_TRIGGER: "CREATE TRIGGER",
    sqlite3.SQLITE_DROP_TABLE: "DROP TABLE",
    sqlite3.SQLITE_ALTER_TABLE: "ALTER TABLE",
}

_current: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "d93_route", default=None
)
_served: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
_found: dict[tuple, int] = defaultdict(int)


def _frames() -> tuple[str, ...]:
    """Last product frames; a leading `[test]` marks writes a test's stand-in made."""
    kept = []
    from_test = False
    for frame in traceback.extract_stack()[:-2]:
        name = frame.filename.replace(os.sep, "/")
        if "/apps/core/tests/" in name and not name.endswith("d93_side_effects_plugin.py"):
            from_test = True
        if "/one_memory/" in name and "/tests/" not in name:
            kept.append(f"{name.split('/one_memory/', 1)[1]}:{frame.lineno} {frame.name}")
    return (("[test]",) if from_test else ()) + tuple(kept[-4:])


#: Self-check: record every route, so a known write route (POST /api/v1/memories)
#: proves the recorder sees writes at all.
_ALL = os.environ.get("ONE_MEMORY_D93_ALL_ROUTES") == "1"


def _authorizer(action, arg1, arg2, db_name, _trigger):
    route = _current.get()
    if route is not None and (_ALL or route in READER_ROUTES) and action in _WRITES:
        table = arg1 if action != sqlite3.SQLITE_ALTER_TABLE else arg2
        if db_name != "temp" and not str(table).startswith("sqlite_"):
            _found[(route, _WRITES[action], str(table), _frames())] += 1
    return sqlite3.SQLITE_OK


_real_connect = sqlite3.connect


def _connect(*args, **kwargs):
    connection = _real_connect(*args, **kwargs)
    with contextlib.suppress(Exception):
        connection.set_authorizer(_authorizer)
    return connection


class _RouteTag:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        status = {"code": 0}

        async def sending(message):
            if message.get("type") == "http.response.start":
                status["code"] = message.get("status", 0)
            await send(message)

        holder: dict[str, tuple[str, str]] = {}
        token = _current.set(None)

        # The route template is only known after routing; resolve it up front
        # from the app's routes so writes made during the handler carry it.
        for route in getattr(self._root(scope), "routes", ()):
            match = getattr(route, "matches", None)
            if match is None:
                continue
            kind, _ = match(scope)
            if kind.name == "FULL":
                holder["route"] = (scope["method"], getattr(route, "path", scope["path"]))
                break
        key = holder.get("route", (scope["method"], scope["path"]))
        _current.set(key)
        try:
            await self.app(scope, receive, sending)
        finally:
            _current.reset(token)
            if key in READER_ROUTES:
                _served[key][status["code"]] += 1

    def _root(self, scope):
        return scope.get("app")


def pytest_configure(config):
    sqlite3.connect = _connect
    # Pooled connections are handed back through `_reset`, which clears any
    # authorizer; put ours back so the next checkout is still recorded.
    from one_memory import database_access

    real_reset = database_access._reset

    def _reset(connection, *, reading):
        clean = real_reset(connection, reading=reading)
        with contextlib.suppress(Exception):
            connection.set_authorizer(_authorizer)
        return clean

    database_access._reset = _reset
    from one_memory import api

    original = api.create_app

    def create_app(*args, **kwargs):
        application = original(*args, **kwargs)
        application.add_middleware(_RouteTag)
        return application

    api.create_app = create_app


def pytest_terminal_summary(terminalreporter):
    report = {
        "served": {
            f"{method} {path}": dict(codes) for (method, path), codes in sorted(_served.items())
        },
        "writes": [
            {
                "route": f"{route[0]} {route[1]}",
                "op": op,
                "table": table,
                "frames": list(frames),
                "count": count,
            }
            for (route, op, table, frames), count in sorted(_found.items(), key=str)
        ],
    }
    target = Path(
        os.environ.get("ONE_MEMORY_D93_SIDE_EFFECTS", str(Path.cwd() / "d93-side-effects.json"))
    )
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write = terminalreporter.write_line
    write(f"D93 side effects: {len(report['writes'])} write sites -> {target}")
    for name, codes in report["served"].items():
        write(f"  served {name}: {codes}")
    for item in report["writes"]:
        write(f"  {item['route']}: {item['op']} {item['table']} x{item['count']}")
        for frame in item["frames"]:
            write(f"      {frame}")
