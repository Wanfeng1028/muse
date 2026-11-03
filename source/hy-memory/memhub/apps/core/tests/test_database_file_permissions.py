import os
import stat
from pathlib import Path

from one_memory.database_access import MainDatabase


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_new_main_database_is_readable_by_its_owner_alone(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    database = MainDatabase(path)

    with database.write() as connection:
        connection.execute("CREATE TABLE note (body TEXT)")
        connection.execute("INSERT INTO note VALUES ('hello')")

    assert _mode(path) == 0o600


def test_the_wal_sidecars_are_not_left_world_readable(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    database = MainDatabase(path)

    with database.write() as connection:
        connection.execute("CREATE TABLE note (body TEXT)")
        connection.execute("INSERT INTO note VALUES ('hello')")

    # WAL mode is what creates these, so their presence is the point: a file
    # nobody chmods is born at the process umask, which is usually 0644.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            assert _mode(sidecar) == 0o600


def test_a_database_from_an_older_build_is_tightened_on_open(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    path.write_bytes(b"")
    os.chmod(path, 0o644)
    assert _mode(path) == 0o644

    database = MainDatabase(path)
    with database.write() as connection:
        connection.execute("CREATE TABLE note (body TEXT)")
        connection.execute("INSERT INTO note VALUES ('hello')")

    assert _mode(path) == 0o600
