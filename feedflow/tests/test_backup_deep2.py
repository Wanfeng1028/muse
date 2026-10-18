from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from feedflow.backup import _KEEP, _PREFIX, backup, restore


def _count_backups(directory: Path) -> int:
    return sum(1 for p in directory.glob(f"{_PREFIX}*.db") if p.is_file())


def _backup_names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.glob(f"{_PREFIX}*.db") if p.is_file())


def test_keep_boundary_three_stage(tmp_db, tmp_path):
    backup_dir = tmp_path / "bk"

    for _ in range(6):
        backup(str(tmp_db), str(backup_dir))
        time.sleep(0.01)

    names_6 = _backup_names(backup_dir)
    assert _count_backups(backup_dir) == 6
    assert len(names_6) == 6

    backup(str(tmp_db), str(backup_dir))
    time.sleep(0.01)

    names_7 = _backup_names(backup_dir)
    assert _count_backups(backup_dir) == _KEEP == 7
    assert len(names_7) == 7
    # 第 7 次没有触发删除，之前的 6 个仍在
    assert set(names_6).issubset(set(names_7))

    oldest = names_7[0]

    backup(str(tmp_db), str(backup_dir))

    names_8 = _backup_names(backup_dir)
    assert _count_backups(backup_dir) == _KEEP == 7
    assert len(names_8) == 7
    assert oldest not in names_8
    # 最新一份仍在
    assert names_8[-1] == sorted(
        p.name for p in backup_dir.glob(f"{_PREFIX}*.db") if p.is_file()
    )[-1]


def test_restore_rejects_tampered_backup(tmp_db, tmp_path):
    backup_dir = tmp_path / "bk"
    bak = backup(str(tmp_db), str(backup_dir))

    # 尾部追加垃圾不影响 sqlite schema 读取，故用截断方式篡改，
    # 破坏文件结构以触发 sqlite3.DatabaseError → ValueError。
    data = Path(bak).read_bytes()
    with open(bak, "wb") as fh:
        fh.write(data[: len(data) // 2])

    target = tmp_path / "restored.db"
    with pytest.raises(ValueError):
        restore(bak, str(target))


def test_restore_accepts_plain_sqlite_without_feedflow_schema(tmp_db, tmp_path):
    plain = tmp_path / "plain.db"
    conn = sqlite3.connect(str(plain))
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    finally:
        conn.close()

    target = tmp_path / "out.db"
    restore(str(plain), str(target))

    assert target.is_file()
    check = sqlite3.connect(str(target))
    try:
        rows = check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        check.close()
    assert ("t",) in rows


def test_restore_creates_deep_parent_dirs(tmp_db, tmp_path):
    backup_dir = tmp_path / "bk"
    bak = backup(str(tmp_db), str(backup_dir))

    deep = tmp_path / "a" / "b" / "c.db"
    assert not deep.parent.exists()

    restore(bak, str(deep))

    assert deep.parent.is_dir()
    assert deep.is_file()


def test_restore_cleans_wal_and_shm_residue(tmp_db, tmp_path):
    backup_dir = tmp_path / "bk"
    bak = backup(str(tmp_db), str(backup_dir))

    target = tmp_path / "t.db"
    wal = Path(str(target) + "-wal")
    shm = Path(str(target) + "-shm")
    wal.write_bytes(b"")
    shm.write_bytes(b"")
    assert wal.exists()
    assert shm.exists()

    restore(bak, str(target))

    assert not wal.exists()
    assert not shm.exists()
    assert target.is_file()

    conn = sqlite3.connect(str(target))
    try:
        conn.execute("SELECT 1").fetchall()
    finally:
        conn.close()


def test_restore_missing_backup_raises_file_not_found(tmp_path):
    missing = tmp_path / "nope.db"
    target = tmp_path / "target.db"

    with pytest.raises(FileNotFoundError):
        restore(str(missing), str(target))


def test_backup_creates_deep_output_dir(tmp_db, tmp_path):
    deep_dir = tmp_path / "x" / "y" / "z"
    assert not deep_dir.exists()

    result = backup(str(tmp_db), str(deep_dir))

    assert deep_dir.is_dir()
    assert Path(result).is_file()
    assert Path(result).parent == deep_dir


def test_backup_nonexistent_source_creates_empty_db(tmp_db, tmp_path):
    missing_src = tmp_path / "not_here.db"
    assert not missing_src.exists()

    backup_dir = tmp_path / "bk"

    result = backup(str(missing_src), str(backup_dir))

    # 记录行为：sqlite3.connect 对不存在的路径会创建空库文件
    assert missing_src.is_file()
    assert Path(result).is_file()
