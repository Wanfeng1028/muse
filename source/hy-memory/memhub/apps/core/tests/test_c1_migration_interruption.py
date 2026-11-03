"""A half-applied schema migration must resume, not corrupt or duplicate.

SQLite commits each `ALTER TABLE ADD COLUMN` as its own statement, so a crash
between two of them leaves a database with some columns present and others
missing. The migration is written to be idempotent per column; this pins that:
opening a store whose schema is deliberately mid-migration finishes the job,
keeps every existing row, and lets the import continue incrementally. It also
checks the legacy `import_errors` -> `import_issues` copy does not run twice.
"""

import sqlite3
from pathlib import Path

from one_memory.imports.jobs import ImportJobStore, ImportStatus


def _legacy_database(path: Path) -> None:
    """A pre-migration database in the real old shape.

    Mirrors the previous schema the store is known to upgrade from: jobs lack
    `phase`/`operation`/`discovered_targets`/`merged`, cursors
    lack `checkpoint_anchor`/`read_to_end`, and errors live in `import_errors`.
    """
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE import_jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                status TEXT NOT NULL,
                runner_token TEXT,
                heartbeat_at TEXT,
                checkpoint TEXT,
                discovered INTEGER NOT NULL DEFAULT 0,
                emitted INTEGER NOT NULL DEFAULT 0,
                stored INTEGER NOT NULL DEFAULT 0,
                revised INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                errors INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE import_errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                conversation_id TEXT,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO import_jobs
                (job_id, user_id, source_id, status, discovered, emitted, stored,
                 errors, created_at, updated_at)
            VALUES ('legacy-job', 'local', 'codex', 'completed', 3, 3, 3, 0,
                    '2026-09-20T00:00:00+00:00', '2026-09-20T00:00:01+00:00');
            INSERT INTO import_errors (job_id, conversation_id, reason, created_at)
            VALUES ('legacy-job', 'c1', 'bad record', '2026-09-20T00:00:00+00:00');
            """
        )


def test_a_half_migrated_database_resumes_without_data_loss(tmp_path):
    database = tmp_path / "one-memory.sqlite3"
    _legacy_database(database)

    # Opening the store runs the migration. It must not raise on the old shape.
    store = ImportJobStore(database)
    job = store.require("legacy-job")
    assert job.status is ImportStatus.COMPLETED
    assert job.stored == 3, "migration must not lose the legacy row's counters"

    # The legacy error was copied exactly once.
    with sqlite3.connect(database) as connection:
        issues = connection.execute(
            "SELECT COUNT(*) FROM import_issues WHERE job_id='legacy-job'"
        ).fetchone()[0]
        assert issues == 1, f"the legacy error copy must be idempotent, got {issues}"
        job_columns = {row[1] for row in connection.execute("PRAGMA table_info(import_jobs)")}
        cursor_columns = {row[1] for row in connection.execute("PRAGMA table_info(source_cursors)")}
    assert "operation" in job_columns
    assert "checkpoint_anchor" in cursor_columns and "read_to_end" in cursor_columns


def test_reopening_a_partially_migrated_database_is_idempotent(tmp_path):
    """A crash mid-migration leaves some columns; reopening finishes the rest.

    This is the literal interruption case: the jobs table already has `operation`
    (added before a crash) but still lacks
    `discovered_targets`/`merged`; the cursor table lacks both new columns. The
    store must add only what is missing, keep the legacy error copy, and not
    duplicate it on subsequent opens.
    """
    database = tmp_path / "one-memory.sqlite3"
    _legacy_database(database)

    # Simulate a crash *after* the jobs table was migrated but before the cursor
    # columns were: add the operation column by hand and stop there.
    with sqlite3.connect(database) as connection:
        connection.execute(
            "ALTER TABLE import_jobs ADD COLUMN operation TEXT NOT NULL DEFAULT 'history'"
        )
        mid_job_columns = {row[1] for row in connection.execute("PRAGMA table_info(import_jobs)")}
    assert "operation" in mid_job_columns
    assert "discovered_targets" not in mid_job_columns, "the fixture must be mid-migration"

    # Reopening completes the migration without error or duplication.
    ImportJobStore(database)
    with sqlite3.connect(database) as connection:
        finished_columns = {row[1] for row in connection.execute("PRAGMA table_info(import_jobs)")}
        issues = connection.execute(
            "SELECT COUNT(*) FROM import_issues WHERE job_id='legacy-job'"
        ).fetchone()[0]
    assert {"discovered_targets", "merged", "phase"} <= finished_columns, (
        f"reopening must add the columns the crash skipped, got {finished_columns}"
    )
    assert issues == 1, f"repeated migrations must not duplicate the legacy copy, got {issues}"

    # A further reopen adds nothing more.
    ImportJobStore(database)
    with sqlite3.connect(database) as connection:
        again = connection.execute(
            "SELECT COUNT(*) FROM import_issues WHERE job_id='legacy-job'"
        ).fetchone()[0]
    assert again == 1, f"repeated migrations must not duplicate the legacy copy: 1 -> {again}"
