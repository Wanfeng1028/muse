import sqlite3

from one_memory.imports.jobs import ImportJobStore, ImportStatus
from one_memory.imports.storage import SCHEMA, EvidenceStore


def test_evidence_store_adds_source_ordinal_to_previous_schema(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA.replace("    source_ordinal TEXT,\n", ""))
    connection.close()

    EvidenceStore(database)

    connection = sqlite3.connect(database)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(evidence)")}
    connection.close()
    assert "source_ordinal" in columns


def test_import_store_migrates_previous_job_and_error_schema(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    connection = sqlite3.connect(database)
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
        INSERT INTO import_jobs (
            job_id, user_id, source_id, status, created_at, updated_at
        ) VALUES (
            'legacy', 'local', 'fixture', 'failed',
            '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00'
        );
        INSERT INTO import_errors (
            job_id, conversation_id, reason, created_at
        ) VALUES (
            'legacy', 'conversation', 'invalid_json',
            '2026-09-01T00:00:00+00:00'
        );
        """
    )
    connection.close()

    store = ImportJobStore(database)

    job = store.require("legacy")
    assert job.phase is None
    assert job.discovered_targets == 0
    assert job.merged == 0
    assert store.list_issues("legacy")[0].reason == "invalid_json"
    connection = sqlite3.connect(database)
    cursor_columns = {row[1] for row in connection.execute("PRAGMA table_info(source_cursors)")}
    connection.close()
    assert "checkpoint_anchor" in cursor_columns


def test_old_active_job_index_lets_a_sync_sit_beside_paused_history(tmp_path) -> None:
    """A catch-up left open used to be the only active job a source could have.

    Reopening the store has to replace that index. Otherwise a paused history
    import still swallows the sync insert, and the new turn is never recorded.
    """
    database = tmp_path / "one-memory.sqlite3"
    store = ImportJobStore(database)
    history = store.create(user_id="local", source_id="fixture", operation="history")
    store.transition(history.job_id, ImportStatus.PAUSED)
    connection = sqlite3.connect(database)
    connection.execute("DROP INDEX one_active_import_per_source")
    connection.execute(
        """
        CREATE UNIQUE INDEX one_active_import_per_source
        ON import_jobs(user_id, source_id)
        WHERE status IN ('pending', 'running', 'paused', 'interrupted', 'failed')
        """
    )
    connection.close()

    reopened = ImportJobStore(database)
    sync = reopened.create(user_id="local", source_id="fixture", operation="sync")

    assert sync.job_id != history.job_id
    assert sync.operation == "sync"
    assert reopened.require(history.job_id).status is ImportStatus.PAUSED


def test_a_never_published_snapshot_failure_opens_a_new_history_job(tmp_path) -> None:
    """Cursor's open database failed the snapshot, then every retry was incomplete.

    The failed row keeps the history slot, and the same job id cannot capture
    again. Startup has to cancel that row and open a new pending job. History
    no longer reads through a snapshot, so a leftover snapshot directory does
    not keep the row; a different failure still stays where it is.
    """
    database = tmp_path / "one-memory.sqlite3"
    snapshots = tmp_path / "import-snapshots"
    store = ImportJobStore(database)
    stuck = _fail(
        store,
        "cursor",
        ("snapshot_sqlite_unavailable", "snapshot_incomplete"),
    )
    limited = _fail(store, "codex", ("snapshot_file_limit",))
    published = _fail(store, "claude-code", ("snapshot_incomplete",))
    (snapshots / published.job_id).mkdir(parents=True)

    opened = store.replace_never_published_snapshot_failures()

    assert store.require(stuck.job_id).status is ImportStatus.CANCELLED
    assert sorted(job.source_id for job in opened) == ["claude-code", "cursor"]
    assert stuck.job_id not in {job.job_id for job in opened}
    assert all(job.status is ImportStatus.PENDING for job in opened)
    assert all(job.operation == "history" for job in opened)
    assert store.require(limited.job_id).status is ImportStatus.FAILED
    assert store.require(published.job_id).status is ImportStatus.CANCELLED


def _fail(store: ImportJobStore, source_id: str, reasons: tuple[str, ...]):
    job = store.create(user_id="local", source_id=source_id, operation="history")
    running, token = store.claim(job.job_id)
    for reason in reasons:
        store.record_error(running.job_id, runner_token=token, reason_code=reason, cursor=None)
    return store.finish_owned(running.job_id, runner_token=token, target=ImportStatus.FAILED)
