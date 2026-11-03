"""测试 backup 模块的备份与恢复。"""
import os
import sqlite3

import pytest

from feedflow import backup
from feedflow import db as db_mod


def _seed_db(db_path: str) -> None:
    """在库中建 feed + 文章各一条。"""
    from feedflow import store

    db_mod.init_db(db_path)
    conn = db_mod.get_conn(db_path)
    try:
        with db_mod.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description,"
                " interval_min, enabled, etag, modified, position, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("测试源", "http://example.com", "http://example.com/feed", "",
                 0, 1, "", "", 0, "2024-01-01T00:00:00+00:00"),
            )
            feed_id = cur.lastrowid
            conn.commit()
    finally:
        conn.close()
    store.insert_article(
        db_path, feed_id, "g-backup-1", "备份文章", "", "http://example.com/a1",
        "", "", "这是用于备份测试的文章内容。", "2024-01-01T00:00:00+00:00",
    )


def _count_articles(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        return int(row[0])
    finally:
        conn.close()


def test_backup_and_restore_roundtrip(tmp_db, tmp_path):
    """备份后文件存在；恢复到新路径后文章数一致。"""
    _seed_db(tmp_db)
    assert _count_articles(tmp_db) == 1

    backup_dir = str(tmp_path / "backups")
    made = backup.backup(tmp_db, backup_dir)
    assert os.path.isfile(made)
    assert os.path.getsize(made) > 0

    restore_path = str(tmp_path / "feedflow-restored.sqlite")
    backup.restore(made, restore_path)
    assert os.path.isfile(restore_path)
    assert _count_articles(restore_path) == 1


def test_backup_keeps_latest_7(tmp_db, tmp_path):
    """备份保留最近 7 个，旧的自动清理。"""
    _seed_db(tmp_db)
    backup_dir = str(tmp_path / "backups")
    import time

    for _ in range(9):
        backup.backup(tmp_db, backup_dir)
        time.sleep(0.02)
    files = [f for f in os.listdir(backup_dir) if f.endswith(".db")]
    assert len(files) == 7, f"应只保留 7 个备份，实际 {len(files)}"


def test_restore_non_sqlite_raises(tmp_path):
    """恢复一个非 sqlite 文件应抛出异常。"""
    bogus = tmp_path / "not-a-db.bin"
    bogus.write_bytes(b"this is definitely not a sqlite database file")
    target = str(tmp_path / "target.sqlite")

    with pytest.raises((ValueError, FileNotFoundError, sqlite3.Error)):
        backup.restore(str(bogus), target)
