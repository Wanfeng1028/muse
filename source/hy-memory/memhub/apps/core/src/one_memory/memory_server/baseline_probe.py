"""A0-04: measure the storage baseline.

The point is not a number for its own sake. docs/ARCHITECTURE.md A0-04 wants a
baseline so schema/query changes can be judged against something: if we cannot
say how large the corpus is, how wide the scan surface is, or how long a read
takes, then "this change did not make it slower" is unfalsifiable. Per D56 the
engine stays SQLite, so this baseline guards **in-place** changes (migrations,
indexes, contention fixes), not an engine swap.

Everything here is read-only. The database is opened `mode=ro` and the script
never writes, vacuums or deletes. Measuring must not be the thing that changes
what is being measured.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_DB = "~/.one-memory/one-memory.sqlite3"

#: Tables that carry the migration's weight. Counted individually because a
#: single "total rows" figure would hide which domain is actually large.
WEIGHT_TABLES = (
    "evidence",
    "evidence_origins",
    "evidence_versions",
    "memory_tasks",
    "memory_task_inputs",
    "memory_task_outputs",
    "import_jobs",
    "source_cursors",
    "governed_memories",
    "governed_memory_evidence",
    "change_outbox",
    "call_events",
)

#: Queries timed as a proxy for "what a scan/read costs today". These are the
#: shapes the scanner and the UI actually issue.
TIMED_QUERIES: tuple[tuple[str, str], ...] = (
    ("evidence_count", "SELECT COUNT(*) FROM evidence"),
    (
        "evidence_by_source",
        "SELECT source_id, COUNT(*) FROM evidence GROUP BY source_id",
    ),
    (
        "recent_evidence_page",
        "SELECT evidence_id FROM evidence ORDER BY rowid DESC LIMIT 100",
    ),
    ("memory_tasks_open", "SELECT COUNT(*) FROM memory_tasks WHERE status='pending'"),
    ("source_cursors_all", "SELECT COUNT(*) FROM source_cursors"),
)


def open_readonly(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _timed(connection: sqlite3.Connection, sql: str) -> dict[str, Any]:
    """Time one query, degrading to an error string like the counts do.

    The probe has to run against schemas from before and after A1, so a table
    that a later migration renames must cost one degraded row rather than
    aborting the whole measurement.
    """
    start = time.perf_counter()
    try:
        rows = connection.execute(sql).fetchall()
    except sqlite3.Error as error:
        return {"rows": 0, "elapsed_ms": 0.0, "error": str(error)}
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return {"rows": len(rows), "elapsed_ms": round(elapsed_ms, 3)}


def measure(db_path: str = DEFAULT_DB) -> dict[str, Any]:
    """Read-only baseline snapshot.

    Reports `unavailable` instead of raising when the database is absent, so
    the probe can run on a clean machine and still say something true.
    """
    path = Path(db_path).expanduser()
    if not path.exists():
        return {"available": False, "db_path": str(path), "reason": "missing"}

    connection = open_readonly(db_path)
    try:
        counts: dict[str, Any] = {}
        for table in WEIGHT_TABLES:
            try:
                counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error as error:  # a table renamed by later work
                counts[table] = f"error: {error}"

        timings = {name: _timed(connection, sql) for name, sql in TIMED_QUERIES}

        db_bytes = path.stat().st_size
        wal = path.with_name(f"{path.name}-wal")
        wal_bytes = wal.stat().st_size if wal.exists() else 0

        return {
            "available": True,
            "db_path": str(path),
            "db_bytes": db_bytes,
            "wal_bytes": wal_bytes,
            "counts": counts,
            "timings_ms": timings,
        }
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = measure(args.db)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if not report["available"]:
            print(f"baseline unavailable: {report['reason']} ({report['db_path']})")
            return 1
        print(f"db: {report['db_path']}")
        print(f"size: {report['db_bytes'] / 1e6:.1f} MB (wal {report['wal_bytes'] / 1e6:.1f} MB)")
        for table, count in report["counts"].items():
            print(f"  {table}: {count}")
        for name, timing in report["timings_ms"].items():
            print(f"  {name}: {timing['elapsed_ms']} ms ({timing['rows']} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
