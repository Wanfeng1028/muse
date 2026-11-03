import sqlite3
from pathlib import Path

from feedflow import db as db_mod
from feedflow.login_lockout import LoginLockout


def test_failures_persist_across_instances(tmp_path: Path):
    # Setup a shared in‑memory style DB backed by a file in tmp_path
    db_path = tmp_path / "test.db"
    clock = [1000.0]
    time_fn = lambda: clock[0]

    # Instance A: two failures
    a = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    key = "1.2.3.4"
    res1 = a.record_failure(key)
    res2 = a.record_failure(key)
    assert res1 == (False, 0.0)
    assert res2 == (False, 0.0)

    # Instance B (new instance, same DB and clock)
    b = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    res3 = b.record_failure(key)
    assert res3 == (True, 900.0)
    assert b.is_locked(key)


def test_lock_persists_across_instances(tmp_path: Path):
    db_path = tmp_path / "test.db"
    clock = [1000.0]
    time_fn = lambda: clock[0]

    a = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    key = "1.2.3.4"
    # Three failures lock the key
    a.record_failure(key)
    a.record_failure(key)
    a.record_failure(key)
    assert a.is_locked(key)
    locked_res = a.record_failure(key)   # Should return (True, 900.0)
    assert locked_res == (True, 900.0)

    # New instance B sees the lock
    b = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    assert b.is_locked(key)
    retry = b.retry_after(key)
    assert 0 <= retry <= 900


def test_success_clears_persisted_lock(tmp_path: Path):
    db_path = tmp_path / "test.db"
    clock = [1000.0]
    time_fn = lambda: clock[0]

    a = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    key = "1.2.3.4"
    a.record_failure(key)
    a.record_failure(key)
    a.record_failure(key)
    assert a.is_locked(key)

    # Success clears the lock
    a.record_success(key)

    # New instance B sees the cleared state
    b = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    assert not b.is_locked(key)
    assert b.retry_after(key) == 0.0


def test_expired_lock_does_not_persist(tmp_path: Path):
    db_path = tmp_path / "test.db"
    clock = [1000.0]
    time_fn = lambda: clock[0]

    a = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    key = "1.2.3.4"
    a.record_failure(key)
    a.record_failure(key)
    a.record_failure(key)               # locked
    assert a.is_locked(key)

    # Advance clock past the lock period
    clock[0] += 900.0 + 1.0

    b = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    assert not b.is_locked(key)

    # One more failure should be recorded fresh
    res = b.record_failure(key)
    assert res == (False, 0.0)


def test_window_expiry_resets_count_across_instances(tmp_path: Path):
    db_path = tmp_path / "test.db"
    clock = [1000.0]
    time_fn = lambda: clock[0]

    a = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    key = "1.2.3.4"
    a.record_failure(key)               # 1st failure
    a.record_failure(key)               # 2nd failure
    assert not a.is_locked(key)

    # Advance beyond the window
    clock[0] += 901.0

    b = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900,
                     time_fn=time_fn, db_path=db_path)
    # One failure should be recorded fresh (no lock)
    res = b.record_failure(key)
    assert res == (False, 0.0)
    assert not b.is_locked(key)


def test_migration_creates_login_lockouts_table(tmp_path: Path):
    db_path = tmp_path / "migration_test.db"
    # Initialise the DB – this runs migrations
    db_mod.init_db(db_path)

    # Verify via raw SQLite that the expected table exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Check migration version
    cursor.execute("PRAGMA user_version")
    actual_version = cursor.fetchone()[0]
    expected_version = len(db_mod.MIGRATIONS)
    assert actual_version == expected_version

    # Check login_lockouts table
    cursor.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='login_lockouts'"
    )
    table_exists = cursor.fetchone()[0] == 1
    assert table_exists

    conn.close()
