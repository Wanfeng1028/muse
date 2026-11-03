"""Backup -> destroy -> restore, reconciled row for row.

A backup is only a backup if it restores. This walks the whole product-level
loop on a temporary database: seed real Evidence, take a backup, destroy the
live file, restore from the backup, then compare every user table's rows.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from one_memory.database_access import close_main_databases, main_database
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_server.contracts import BatchIdentity, WriteRequest
from one_memory.memory_server.durable_queue import DurableWriteQueue


def _seed(path: Path, count: int = 25) -> None:
    store = EvidenceStore(path)
    for index in range(count):
        store.put(
            EvidenceInput(
                source_id="cursor",
                conversation_id=f"conversation-{index % 5}",
                message_id=f"m{index}",
                role="user" if index % 2 else "assistant",
                written_by=WrittenBy.PERSON if index % 2 else WrittenBy.AGENT,
                verbatim=f"第 {index} 句原始内容，用于恢复对账。",
                created_at=datetime.now(UTC),
                origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
            )
        )
    close_main_databases()


def _dump(path: Path) -> dict[str, list[tuple]]:
    """Every user table's rows, so a restore can be compared, not assumed."""
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}


def test_restoring_a_backup_reproduces_every_row_after_the_live_file_is_destroyed(
    tmp_path,
) -> None:
    path = tmp_path / "one-memory.sqlite3"
    _seed(path)
    backup = tmp_path / "backups" / "before.sqlite3"

    database = main_database(path)
    database.back_up(backup)
    before = _dump(path)
    close_main_databases()

    # Destroy the live database the way a failed disk or truncate would.
    path.write_bytes(b"not a database anymore")
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)

    reopened = main_database(path)
    reopened.restore_from(backup)
    close_main_databases()

    after = _dump(path)
    assert after == before
    assert after["evidence"], "the restored database has no evidence to compare"


def test_restore_preserves_reconcile_references_after_payload_reaping(tmp_path) -> None:
    """The queue's Evidence references must survive backup/restore.

    `memory_write_job_evidence` is the discovery half of the crash reconcile.
    If it were not copied, a restored completed job would look like an orphan
    and could be submitted again, risking a duplicate HY call.
    """
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    evidence = store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="conversation",
            message_id="m1",
            role="user",
            written_by=WrittenBy.PERSON,
            verbatim="restore reference",
            created_at=datetime.now(UTC),
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    queue = DurableWriteQueue(path)
    record = queue.submit(
        WriteRequest(
            internal_session_id="conversation",
            batch_identity=BatchIdentity(
                internal_session_id="conversation", first_round=1, last_round=1
            ),
            evidence_ids=[evidence.evidence_id],
            idempotency_key="restore-reference",
        )
    )
    queue.settle(record.job_id, state="completed")
    assert queue.clear_terminal_payloads() == 1
    backup = tmp_path / "backups" / "references.sqlite3"
    main_database(path).back_up(backup)
    close_main_databases()

    path.write_bytes(b"destroyed")
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    main_database(path).restore_from(backup)
    close_main_databases()

    restored = DurableWriteQueue(path)
    assert restored.unsubmitted_evidence_ids() == ()


def test_a_published_backup_is_verified_restorable(tmp_path) -> None:
    """A backup must be openable and intact, not merely written.

    "A backup is only a backup if it has been restored." `back_up` now runs
    `quick_check` on the copy before publishing it, so the file left at the
    target is a database a restore can actually consume.
    """
    path = tmp_path / "one-memory.sqlite3"
    _seed(path)
    backup = tmp_path / "backups" / "verified.sqlite3"

    main_database(path).back_up(backup)

    with sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] > 0


def test_back_up_verifies_the_copy_before_publishing(tmp_path) -> None:
    """The copy must pass `quick_check` before it becomes `target`.

    Corruption is introduced in the source page data, so the copy `back_up`
    makes is itself unopenable and only the verification can refuse it. This is
    the "a backup is only a backup if it can be opened" rule, enforced at the
    moment of writing rather than discovered at restore time.
    """
    path = tmp_path / "one-memory.sqlite3"
    _seed(path, count=200)

    # Corrupt the schema so the database is genuinely invalid: point a table at
    # a bogus root page. `quick_check` on the copy must then report corruption.
    with sqlite3.connect(path) as connection, connection:
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute("UPDATE sqlite_master SET rootpage=999999 WHERE name='evidence'")
    close_main_databases()
    target = tmp_path / "backups" / "corrupt.sqlite3"

    with pytest.raises(sqlite3.DatabaseError):
        main_database(path).back_up(target)
    assert not target.exists(), "a copy that fails its check must not be published"


def test_a_damaged_backup_is_refused_and_leaves_the_live_database_alone(tmp_path) -> None:
    """Fail closed: a bad backup must not become a worse live database."""
    path = tmp_path / "one-memory.sqlite3"
    _seed(path, count=5)
    damaged = tmp_path / "backups" / "damaged.sqlite3"
    damaged.parent.mkdir(parents=True, exist_ok=True)
    damaged.write_bytes(b"not a sqlite database")

    database = main_database(path)
    with pytest.raises(sqlite3.DatabaseError):
        database.restore_from(damaged)
    close_main_databases()

    assert _dump(path)["evidence"], "the live database was lost refusing a bad backup"


def test_a_second_backup_never_replaces_an_earlier_one(tmp_path) -> None:
    """The whole point of a backup is rolling back to *that* point.

    `back_up()` promises an earlier backup is never replaced. Without the
    exclusive reserve, `os.replace` silently overwrites it, and an upgrade
    rollback then lands somewhere nobody chose.
    """
    path = tmp_path / "one-memory.sqlite3"
    _seed(path, count=5)
    target = tmp_path / "backups" / "one.sqlite3"

    database = main_database(path)
    database.back_up(target)
    first_bytes = target.read_bytes()
    close_main_databases()

    # More Evidence, then attempt the same target again.
    _seed(path, count=20)
    with pytest.raises(FileExistsError):
        main_database(path).back_up(target)
    close_main_databases()

    assert target.read_bytes() == first_bytes, "the earlier backup was replaced"


def test_a_backup_refuses_a_symlink_target(tmp_path) -> None:
    """A symlinked target would write wherever it points, not where we checked."""
    path = tmp_path / "one-memory.sqlite3"
    _seed(path, count=3)
    elsewhere = tmp_path / "elsewhere.sqlite3"
    # Inside the data dir, so the refusal cannot be credited to the directory
    # check alone: the symlink itself must be rejected.
    target = tmp_path / "backups" / "linked.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(elsewhere)
    try:
        with pytest.raises((FileExistsError, OSError)):
            main_database(path).back_up(target)
    finally:
        close_main_databases()

    assert not elsewhere.exists(), "the backup followed the symlink"


def test_a_truncated_live_database_fails_loudly_then_restores(tmp_path) -> None:
    """Corruption must be visible: never a silent empty answer.

    A truncated file that returns "no rows" is worse than an error, because
    the caller cannot tell an empty library from a broken one. This asserts
    the read raises, then that the backup still restores every row.
    """
    path = tmp_path / "one-memory.sqlite3"
    _seed(path, count=12)
    backup = tmp_path / "backups" / "before.sqlite3"

    database = main_database(path)
    database.back_up(backup)
    before = _dump(path)
    close_main_databases()

    # Truncate mid-file: the header survives, the pages do not.
    truncated = path.read_bytes()[: len(path.read_bytes()) // 2]
    path.write_bytes(truncated)
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)

    with pytest.raises(sqlite3.DatabaseError), main_database(path).read() as connection:
        connection.execute("SELECT COUNT(*) FROM evidence").fetchone()
    close_main_databases()

    reopened = main_database(path)
    reopened.restore_from(backup)
    close_main_databases()

    assert _dump(path) == before


def test_restore_with_identity_requirement_refuses_a_foreign_database(tmp_path) -> None:
    """Product-callable fail-closed restore (C8 P1 BLOCK).

    A valid SQLite file that is not a One Memory database must not replace the
    live one. The caller passes the marker table; the source lacks it, so the
    restore is refused and the live rows are untouched.
    """
    path = tmp_path / "one-memory.sqlite3"
    _seed(path)
    before = _dump(path)
    close_main_databases()
    foreign = tmp_path / "other.sqlite3"
    with sqlite3.connect(foreign) as connection, connection:
        connection.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER)")
        connection.execute("INSERT INTO counter VALUES (1, 0)")

    with pytest.raises(sqlite3.DatabaseError, match="not a One Memory database"):
        main_database(path).restore_from(foreign, required_tables=frozenset({"evidence"}))

    assert _dump(path) == before


def test_restore_with_identity_requirement_accepts_a_real_backup(tmp_path) -> None:
    """The identity requirement must not reject a genuine One Memory backup."""
    path = tmp_path / "one-memory.sqlite3"
    _seed(path)
    backup = tmp_path / "backups" / "real.sqlite3"
    database = main_database(path)
    database.back_up(backup)
    before = _dump(path)
    close_main_databases()

    reopened = main_database(path)
    reopened.restore_from(backup, required_tables=frozenset({"evidence"}))
    close_main_databases()

    assert _dump(path) == before


def test_failed_restore_replace_keeps_the_committed_live_wal(tmp_path, monkeypatch) -> None:
    """A failed restore must leave the live database exactly as it was.

    The live database is in WAL mode. A failed publish must not remove the
    sidecars or strand the committed row in a deleted WAL; the failure must be
    the only observable effect.
    """
    path = tmp_path / "one-memory.sqlite3"
    backup = tmp_path / "backups" / "before.sqlite3"
    _seed(path, count=5)
    database = main_database(path)
    database.back_up(backup)
    with database.write() as connection, connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(evidence)").fetchall()]
        values = {
            "evidence_id": "'wal-row'",
            "idempotency_key": "'wal-row-idempotency'",
            "verbatim": "'committed only in WAL'",
            "content_hash": "'wal-row-hash'",
        }
        select_columns = ", ".join(values.get(column, column) for column in columns)
        connection.execute(
            f"INSERT INTO evidence ({', '.join(columns)}) "
            f"SELECT {select_columns} FROM evidence LIMIT 1"
        )
    assert Path(f"{path}-wal").exists()

    real_replace = __import__("os").replace

    def fail_the_restore_replace(source, target):
        if Path(target) == path and str(source).endswith(".partial"):
            raise OSError("simulated replace failure")
        return real_replace(source, target)

    monkeypatch.setattr("one_memory.database_access.os.replace", fail_the_restore_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        database.restore_from(backup)

    # Re-open as a fresh process would: SQLite must still see the committed
    # row, so the failed restore cannot have removed the only copy.
    close_main_databases()
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_id = 'wal-row'"
            ).fetchone()[0]
            == 1
        )


def test_failed_restore_replace_keeps_live_sidecars_at_the_failure_point(
    tmp_path, monkeypatch
) -> None:
    """The old sidecars must not be cleaned before a failed publish attempt.

    Filesystem state is noisy: `restore_from` closes idle connections first,
    and SQLite may remove its own sidecars. To test the actual ordering, record
    whether cleanup was attempted before the injected `os.replace` failure.
    The old "cleanup, then replace" order calls the cleanup hook first; the
    current implementation calls replace first and therefore must not.
    """
    path = tmp_path / "one-memory.sqlite3"
    backup = tmp_path / "backups" / "before.sqlite3"
    _seed(path, count=5)
    database = main_database(path)
    database.back_up(backup)
    cleanup_calls: list[Path] = []

    def record_cleanup(candidate: Path) -> None:
        cleanup_calls.append(candidate)

    monkeypatch.setattr(
        "one_memory.database_access._remove_stale_sidecar",
        record_cleanup,
    )
    real_replace = __import__("os").replace

    def fail_the_restore_replace(source, target):
        if Path(target) == path and str(source).endswith(".partial"):
            raise OSError("simulated replace failure at the publish point")
        return real_replace(source, target)

    monkeypatch.setattr("one_memory.database_access.os.replace", fail_the_restore_replace)
    with pytest.raises(OSError, match="failure at the publish point"):
        database.restore_from(backup)

    assert cleanup_calls == [], (
        "sidecar cleanup ran before the publish attempt; a failed replace can "
        "therefore strand committed WAL rows"
    )


def test_restore_succeeds_when_the_published_main_file_cannot_clean_old_wal(
    tmp_path, monkeypatch
) -> None:
    """Once the verified main file is published, stale sidecar cleanup is best-effort.

    `os.replace` is the restore's commit point. A failure to remove the old
    `-wal` afterwards means only that a stale sidecar remains; raising would
    report a failed restore even though the live database is the restored copy.
    The restore must return success and the new copy must be readable.
    """
    path = tmp_path / "one-memory.sqlite3"
    backup = tmp_path / "backups" / "before.sqlite3"
    _seed(path, count=5)
    database = main_database(path)
    database.back_up(backup)

    real_unlink = Path.unlink

    def fail_wal_unlink(self, *args, **kwargs):
        if str(self).endswith("-wal"):
            raise OSError("simulated wal unlink failure")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_wal_unlink)
    database.restore_from(backup)
    monkeypatch.setattr(Path, "unlink", real_unlink)

    assert Path(f"{path}-wal").exists(), "the unremovable stale sidecar disappeared"
    close_main_databases()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 5


def test_restore_still_fails_when_directory_fsync_cannot_confirm_publication(
    tmp_path, monkeypatch
) -> None:
    """Directory fsync is the durability boundary, not best-effort cleanup."""
    path = tmp_path / "one-memory.sqlite3"
    backup = tmp_path / "backups" / "before.sqlite3"
    _seed(path, count=5)
    database = main_database(path)
    database.back_up(backup)

    real_fsync = __import__("os").fsync
    calls = {"n": 0}

    def fail_second_fsync(descriptor):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr("one_memory.database_access.os.fsync", fail_second_fsync)
    with pytest.raises(OSError, match="directory fsync failure"):
        database.restore_from(backup)

    close_main_databases()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 5


def test_backup_keeps_the_published_copy_when_directory_fsync_fails(tmp_path, monkeypatch) -> None:
    """A published backup is the rollback point; a durability error must not erase it.

    `os.replace` publishes the verified copy before the directory fsync. If that
    fsync fails, the caller must be told, but deleting the published file makes
    the failure worse: the upgrade then proceeds with no rollback copy. Keep the
    verified file, report the durability error, and let the next attempt use a
    fresh target.
    """
    path = tmp_path / "one-memory.sqlite3"
    target = tmp_path / "backups" / "before.sqlite3"
    _seed(path, count=5)
    database = main_database(path)

    real_fsync = __import__("os").fsync
    calls = {"n": 0}

    def fail_directory_fsync(descriptor):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated backup directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr("one_memory.database_access.os.fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="backup directory fsync failure"):
        database.back_up(target)

    assert target.exists(), "the published rollback copy was deleted"
    with sqlite3.connect(f"{target.as_uri()}?mode=ro&immutable=1", uri=True) as connection:
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 5
