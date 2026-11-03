"""A0-04: the baseline probe itself must be trustworthy.

The measurement is only useful if the instrument works, so these tests cover
the probe rather than today's numbers: a probe that silently reports zero on a
real database would make every later "MySQL is not slower" claim worthless.

Numbers are deliberately NOT asserted. The corpus grows and shrinks with use,
and pinning a count here would break on the next import for no reason. What is
pinned is that the probe opens read-only, reports real tables, and times the
shapes the scanner actually issues.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from one_memory.memory_server.baseline_probe import (
    WEIGHT_TABLES,
    measure,
    open_readonly,
)


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    path = tmp_path / "probe.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE evidence (evidence_id TEXT, source_id TEXT)")
        connection.execute("CREATE TABLE memory_tasks (task_id TEXT, status TEXT)")
        connection.executemany(
            "INSERT INTO evidence VALUES (?, ?)",
            [(f"e{i}", "cursor" if i % 2 else "codex") for i in range(500)],
        )
        connection.executemany(
            "INSERT INTO memory_tasks VALUES (?, ?)",
            [(f"t{i}", "pending" if i % 3 else "completed") for i in range(30)],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def test_probe_reads_a_real_database(seeded_db: Path) -> None:
    report = measure(str(seeded_db))
    assert report["available"] is True
    assert report["counts"]["evidence"] == 500
    assert report["counts"]["memory_tasks"] == 30


def test_probe_reports_absence_instead_of_zero(tmp_path: Path) -> None:
    """A missing database must not look like an empty one.

    Zero rows and "no database" are different facts. Collapsing them would let
    a broken path masquerade as a clean, tiny corpus.
    """
    report = measure(str(tmp_path / "nope.db"))
    assert report["available"] is False
    assert report["reason"] == "missing"
    assert "counts" not in report


def test_probe_never_writes(seeded_db: Path) -> None:
    """Measuring must not change what is measured.

    The probe exists to be run against the user's live database, so a write
    path (or an implicit WAL/journal create) would be a data-integrity bug,
    not just untidiness.
    """
    before = seeded_db.stat().st_mtime_ns
    connection = open_readonly(str(seeded_db))
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE leaked (x TEXT)")
    finally:
        connection.close()
    assert seeded_db.stat().st_mtime_ns == before


def test_opened_connection_is_query_only(seeded_db: Path) -> None:
    connection = open_readonly(str(seeded_db))
    try:
        mode = connection.execute("PRAGMA query_only").fetchone()[0]
        assert mode == 1
    finally:
        connection.close()


def test_probe_times_the_shapes_the_scanner_uses(seeded_db: Path) -> None:
    """The timed queries must succeed against a minimal schema.

    `evidence_by_source` is the interesting one: it is the shape the current
    scan issues per source and the reason A4 mandates a metadata-first gate
    instead of a per-file walk.
    """
    report = measure(str(seeded_db))
    timings = report["timings_ms"]
    assert "evidence_by_source" in timings
    assert timings["evidence_by_source"]["rows"] == 2
    assert timings["evidence_by_source"]["elapsed_ms"] >= 0


def test_unknown_tables_are_reported_not_raised(seeded_db: Path) -> None:
    """A table renamed during the migration must degrade one row, not crash.

    The probe runs before and after A1; failing hard on a renamed table would
    make the "after" measurement impossible to take.
    """
    report = measure(str(seeded_db))
    assert report["counts"]["change_outbox"].startswith("error:")
    assert len(report["counts"]) == len(WEIGHT_TABLES)
