"""备份/恢复测试。

CLI 入口函数名: ledger.__main__.main
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import ledger.__main__ as cli
from ledger.backup import BackupError, backup_db, integrity_check, restore_db
from ledger.config import get_settings
from ledger.migrations import run_migrations


async def _make_db(db_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        await run_migrations(engine)
    finally:
        await engine.dispose()


def _insert_account(db_path: Path, name: str = "cash") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO accounts (name, type, currency, opening_balance_cents, "
            "note, is_archived, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (name, "cash", "CNY", 0, "", 0),
        )
        conn.commit()
    finally:
        conn.close()


def _count_accounts(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_backup_creates_file_and_prunes(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    await _make_db(db_path)
    _insert_account(db_path)

    backup_dir = tmp_path / "backups"
    out = backup_db(str(db_path), str(backup_dir), keep=2)
    assert Path(out).exists()
    assert re.fullmatch(r"ledger-\d{8}-\d{6}(-\d+)?\.db", Path(out).name)

    # 再备份 3 次，keep=2 -> 只剩 2 个（同秒碰撞用 -N 后缀区分）
    for _ in range(3):
        backup_db(str(db_path), str(backup_dir), keep=2)

    remaining = sorted(Path(backup_dir).glob("ledger-*.db"))
    assert len(remaining) == 2


@pytest.mark.asyncio
async def test_restore_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    await _make_db(db_path)
    _insert_account(db_path, "cash")
    assert _count_accounts(db_path) == 1

    backup_dir = tmp_path / "backups"
    snap = backup_db(str(db_path), str(backup_dir))

    # 删除 account
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM accounts")
        conn.commit()
    finally:
        conn.close()
    assert _count_accounts(db_path) == 0

    restored = restore_db(str(db_path), snap, str(backup_dir))
    assert restored == str(db_path)
    assert _count_accounts(db_path) == 1
    integrity_check(str(db_path))


@pytest.mark.asyncio
async def test_restore_rejects_bad_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.db"
    await _make_db(db_path)
    _insert_account(db_path)
    original = db_path.read_bytes()

    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a sqlite database at all")

    backup_dir = tmp_path / "backups"
    with pytest.raises(BackupError):
        restore_db(str(db_path), str(bad), str(backup_dir))

    # 原库未被覆盖
    assert db_path.read_bytes() == original


@pytest.mark.asyncio
async def test_cli_backup_and_restore_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "ledger.db"
    await _make_db(db_path)
    _insert_account(db_path)

    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("LEDGER_DB", str(db_path))
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(
            sys, "argv", ["ledger", "backup", "--dir", str(backup_dir)]
        )
        rc = cli.main()
        assert rc == 0
        assert list(Path(backup_dir).glob("ledger-*.db"))

        monkeypatch.setattr(
            sys, "argv", ["ledger", "restore", "/不存在/xx.db"]
        )
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
        assert excinfo.value.code != 0
    finally:
        get_settings.cache_clear()
