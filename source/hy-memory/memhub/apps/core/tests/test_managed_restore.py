import asyncio
import sqlite3
from datetime import UTC, datetime

import pytest

from one_memory.database_access import main_database
from one_memory.managed_restore import RestoreRejected, restore_managed_backup
from one_memory.memory_server.migration_runner import SqliteMigrationStore
from one_memory.memory_server.migrations import Migration


def _one_memory_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE governed_memories (memory_id TEXT PRIMARY KEY)")
    store = SqliteMigrationStore(path)
    asyncio.run(store.record(Migration(34, "synthetic", lambda _: None)))
    return path


def _real_shaped_database(path):
    """A database shaped like a normal Core one: no migration ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE governed_memories (memory_id TEXT PRIMARY KEY)")
    return path


def test_restore_rejects_a_source_outside_the_managed_backup_directory(tmp_path) -> None:
    outside = _one_memory_database(tmp_path / "outside.sqlite3")

    with pytest.raises(RestoreRejected, match="backup_restore_source_outside_home"):
        restore_managed_backup(data_dir=tmp_path / "home", source=str(outside))


def test_restore_rejects_a_symlinked_source(tmp_path) -> None:
    home = tmp_path / "home"
    source = _one_memory_database(tmp_path / "real.sqlite3")
    backups = home / "backups"
    backups.mkdir(parents=True)
    link = backups / "linked.sqlite3"
    link.symlink_to(source)

    with pytest.raises(RestoreRejected, match="backup_restore_source_outside_home"):
        restore_managed_backup(data_dir=home, source=str(link))


def test_restore_rejects_a_non_one_memory_database(tmp_path) -> None:
    home = tmp_path / "home"
    source = home / "backups" / "foreign.sqlite3"
    source.parent.mkdir(parents=True)
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")

    with pytest.raises(RestoreRejected, match="backup_restore_source_invalid"):
        restore_managed_backup(data_dir=home, source=str(source))


def test_restore_keeps_a_protective_backup_and_replaces_the_live_database(tmp_path) -> None:
    home = tmp_path / "home"
    live = _one_memory_database(home / "one-memory.sqlite3")
    with sqlite3.connect(live) as connection:
        connection.execute("INSERT INTO evidence VALUES ('old')")
    backup = _one_memory_database(home / "backups" / "known-good.sqlite3")
    with sqlite3.connect(backup) as connection:
        connection.execute("INSERT INTO evidence VALUES ('restored')")

    result = restore_managed_backup(
        data_dir=home,
        source=str(backup),
        now=datetime(2026, 9, 29, tzinfo=UTC),
    )

    assert result.source_schema_version == 34
    assert result.previous_backup_path.exists()
    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("restored",)]
    with sqlite3.connect(result.previous_backup_path) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("old",)]


def test_restore_refuses_while_the_database_has_an_active_checkout(tmp_path) -> None:
    home = tmp_path / "home"
    live = _one_memory_database(home / "one-memory.sqlite3")
    backup = _one_memory_database(home / "backups" / "known-good.sqlite3")
    database = main_database(live)

    with database.write(), pytest.raises(RestoreRejected, match="backup_restore_replace_failed"):
        restore_managed_backup(data_dir=home, source=str(backup))


def test_restore_reads_rows_committed_in_the_source_wal(tmp_path) -> None:
    """`immutable=1` would ignore the WAL and silently restore stale rows."""
    home = tmp_path / "home"
    live = _one_memory_database(home / "one-memory.sqlite3")
    backup = _one_memory_database(home / "backups" / "wal.sqlite3")
    connection = sqlite3.connect(backup)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO evidence VALUES ('from-wal')")
        connection.commit()
    finally:
        connection.close()

    restore_managed_backup(data_dir=home, source=str(backup))

    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("from-wal",)]


def test_restore_replaces_an_old_live_wal_with_the_restored_rows(tmp_path) -> None:
    """The live WAL must belong to the old file after the atomic replace."""
    home = tmp_path / "home"
    live = _one_memory_database(home / "one-memory.sqlite3")
    with sqlite3.connect(live) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("INSERT INTO evidence VALUES ('old-only-in-live-wal')")
        connection.commit()
    backup = _one_memory_database(home / "backups" / "known-good.sqlite3")
    with sqlite3.connect(backup) as connection:
        connection.execute("INSERT INTO evidence VALUES ('restored')")

    restore_managed_backup(data_dir=home, source=str(backup))

    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("restored",)]


def test_restore_refuses_a_backup_from_a_newer_schema(tmp_path) -> None:
    """A future schema must fail closed instead of replacing the live database."""
    home = tmp_path / "home"
    live = _one_memory_database(home / "one-memory.sqlite3")
    with sqlite3.connect(live) as connection:
        connection.execute("INSERT INTO evidence VALUES ('live')")
    backup = home / "backups" / "too-new.sqlite3"
    backup.parent.mkdir(parents=True)
    with sqlite3.connect(backup) as connection:
        connection.execute("CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE governed_memories (memory_id TEXT PRIMARY KEY)")
    asyncio.run(SqliteMigrationStore(backup).record(Migration(999, "future", lambda _: None)))

    with pytest.raises(RestoreRejected, match="backup_restore_source_too_new"):
        restore_managed_backup(data_dir=home, source=str(backup))

    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("live",)]


def test_restore_accepts_a_real_core_database_without_a_migration_ledger(tmp_path) -> None:
    """A normally-created Core database has no `schema_migrations` table.

    The package smoke for H25 exposed this: `EvidenceStore`/Core bootstrap
    creates the business tables but no ledger, so requiring the ledger made
    every legitimate backup fail as `source_invalid`.
    """
    home = tmp_path / "home"
    live = _real_shaped_database(home / "one-memory.sqlite3")
    with sqlite3.connect(live) as connection:
        connection.execute("INSERT INTO evidence VALUES ('live')")
    backup = _real_shaped_database(home / "backups" / "real.sqlite3")
    with sqlite3.connect(backup) as connection:
        connection.execute("INSERT INTO evidence VALUES ('restored')")

    result = restore_managed_backup(data_dir=home, source=str(backup))

    assert result.source_schema_version == 0
    with sqlite3.connect(live) as connection:
        assert connection.execute("SELECT evidence_id FROM evidence").fetchall() == [("restored",)]
