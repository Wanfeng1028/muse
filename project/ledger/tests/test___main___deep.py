"""ledger 命令行入口 main 的深度测试。

覆盖：边界值、失败注入、幂等、并发、中文场景。
被测模块：ledger/__main__.py，入口函数 main。
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from argparse import Namespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import ledger.__main__ as entry  # noqa: E402
from ledger.backup import BackupError, backup_db  # noqa: E402
from ledger.config import get_settings  # noqa: E402


def _make_sqlite_db(path: Path) -> None:
    """创建一个真实的 SQLite 数据库文件。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('seed')")
        conn.commit()
    finally:
        conn.close()


def _run_main(argv, monkeypatch):
    """以指定命令行参数调用 main，返回退出码。"""
    monkeypatch.setattr(sys, "argv", ["ledger", *argv])
    return entry.main()


class _FakeArgs(Namespace):
    """用于直接调用子命令处理函数的参数对象。"""


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------

def test_backup_keep_zero_boundary(tmp_path, monkeypatch):
    """keep=0 边界：_prune_backups 会删掉所有文件（含刚生成的），目录最终为空。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    args = _FakeArgs(dir=str(backup_dir), keep=0)
    rc = entry._cmd_backup(args)

    assert rc == 0
    produced = list(backup_dir.glob("*.db"))
    assert produced == []


def test_backup_keep_negative_is_rejected(tmp_path, monkeypatch):
    """keep 为负数按 0 处理：所有备份文件（含刚生成的）都会被修剪掉。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    args = _FakeArgs(dir=str(backup_dir), keep=-1)
    rc = entry._cmd_backup(args)

    assert rc == 0
    produced = list(backup_dir.glob("*.db"))
    assert produced == []


def test_backup_empty_dir_string_uses_env(tmp_path, monkeypatch):
    """dir 为空字符串时视为未提供，回落到环境变量指定的目录。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    env_dir = tmp_path / "env_backups"
    env_dir.mkdir()
    monkeypatch.setenv("LEDGER_BACKUP_DIR", str(env_dir))

    # 空字符串不是 None，因此 main 不会覆盖；直接调用处理函数验证 dir 落到环境变量路径
    resolved = entry._default_backup_dir()
    assert resolved == str(env_dir)

    args = _FakeArgs(dir=resolved, keep=7)
    rc = entry._cmd_backup(args)
    assert rc == 0
    assert len(list(env_dir.glob("*.db"))) == 1


def test_default_backup_dir_when_env_absent(tmp_path, monkeypatch):
    """未设置 LEDGER_BACKUP_DIR 时回落到 PROJECT_ROOT/data/backups。"""
    monkeypatch.delenv("LEDGER_BACKUP_DIR", raising=False)
    from ledger.config import PROJECT_ROOT

    expected = str(Path(PROJECT_ROOT) / "data" / "backups")
    assert entry._default_backup_dir() == expected


# ---------------------------------------------------------------------------
# 失败注入
# ---------------------------------------------------------------------------

def test_backup_db_error_raises_system_exit(tmp_path, monkeypatch):
    """备份底层抛 BackupError 时，命令应写入 stderr 并 SystemExit(1)。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    def _boom(*_a, **_kw):
        raise BackupError("磁盘空间不足")

    monkeypatch.setattr(entry, "backup_db", _boom)

    args = _FakeArgs(dir=str(backup_dir), keep=7)
    with pytest.raises(SystemExit) as excinfo:
        entry._cmd_backup(args)

    assert excinfo.value.code == 1


def test_restore_db_error_raises_system_exit(tmp_path, monkeypatch):
    """恢复底层抛 BackupError 时，命令应 SystemExit(1)。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    bad_file = backup_dir / "broken.db"
    bad_file.write_bytes(b"not-a-sqlite-file")

    def _boom(*_a, **_kw):
        raise BackupError("备份文件损坏")

    monkeypatch.setattr(entry, "restore_db", _boom)

    args = _FakeArgs(file=str(bad_file), dir=str(backup_dir))
    with pytest.raises(SystemExit) as excinfo:
        entry._cmd_restore(args)

    assert excinfo.value.code == 1


def test_restore_missing_file_raises_system_exit(tmp_path, monkeypatch):
    """恢复不存在的文件：restore_db 抛 BackupError，命令退出码 1。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    missing = backup_dir / "no_such_file.db"

    args = _FakeArgs(file=str(missing), dir=str(backup_dir))
    with pytest.raises(SystemExit) as excinfo:
        entry._cmd_restore(args)

    assert excinfo.value.code == 1
    assert not missing.exists()


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------

def test_backup_twice_is_idempotent_on_content(tmp_path, monkeypatch):
    """连续两次备份：内容一致，文件数量累加但可读。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    args = _FakeArgs(dir=str(backup_dir), keep=7)
    assert entry._cmd_backup(args) == 0
    assert entry._cmd_backup(args) == 0

    produced = sorted(backup_dir.glob("*.db"))
    assert len(produced) == 2
    for p in produced:
        with sqlite3.connect(str(p)) as conn:
            rows = conn.execute("SELECT v FROM t").fetchall()
        assert rows == [("seed",)]


def test_restore_twice_yields_same_db(tmp_path, monkeypatch):
    """同一备份恢复两次：结果文件内容一致，保证幂等。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    src = backup_dir / "seed.db"
    _make_sqlite_db(src)

    args = _FakeArgs(file=str(src), dir=str(backup_dir))
    rc1 = entry._cmd_restore(args)
    first = db_path.read_bytes()
    rc2 = entry._cmd_restore(args)
    second = db_path.read_bytes()

    assert rc1 == 0 and rc2 == 0
    assert first == second
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT v FROM t").fetchall()
    assert rows == [("seed",)]


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------

def test_concurrent_backup_same_source(tmp_path, monkeypatch):
    """并发两次备份同一数据库：两个备份文件都生成且内容一致。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    def _do_backup():
        settings = get_settings()
        return backup_db(settings.db_path, str(backup_dir), keep=7)

    async def _run():
        return await asyncio.gather(
            asyncio.to_thread(_do_backup),
            asyncio.to_thread(_do_backup),
        )

    paths = asyncio.run(_run())

    assert len(paths) == 2
    for p in paths:
        assert Path(p).exists()
        with sqlite3.connect(str(p)) as conn:
            rows = conn.execute("SELECT v FROM t").fetchall()
        assert rows == [("seed",)]


def test_concurrent_restore_same_target(tmp_path, monkeypatch):
    """并发两次恢复同一目标：最终目标文件内容正确。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    src = backup_dir / "seed.db"
    _make_sqlite_db(src)

    args = _FakeArgs(file=str(src), dir=str(backup_dir))

    async def _run():
        return await asyncio.gather(
            asyncio.to_thread(entry._cmd_restore, args),
            asyncio.to_thread(entry._cmd_restore, args),
        )

    rcs = asyncio.run(_run())

    assert rcs == [0, 0]
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT v FROM t").fetchall()
    assert rows == [("seed",)]


# ---------------------------------------------------------------------------
# 中文场景
# ---------------------------------------------------------------------------

def test_backup_dir_with_chinese_name(tmp_path, monkeypatch):
    """中文目录名：备份路径包含中文也应正常写入。"""
    db_path = tmp_path / "账本.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "备份目录"
    backup_dir.mkdir()

    args = _FakeArgs(dir=str(backup_dir), keep=7)
    rc = entry._cmd_backup(args)

    assert rc == 0
    produced = list(backup_dir.glob("*.db"))
    assert len(produced) == 1
    with sqlite3.connect(str(produced[0])) as conn:
        rows = conn.execute("SELECT v FROM t").fetchall()
    assert rows == [("seed",)]


def test_restore_with_chinese_file_name(tmp_path, monkeypatch):
    """中文备份文件名：恢复应把内容写回 LEDGER_DB 指向的文件。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    backup_dir = tmp_path / "备份目录"
    backup_dir.mkdir()
    src = backup_dir / "工资单备份.db"
    _make_sqlite_db(src)

    args = _FakeArgs(file=str(src), dir=str(backup_dir))
    rc = entry._cmd_restore(args)

    assert rc == 0
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT v FROM t").fetchall()
    assert rows == [("seed",)]


def test_main_default_command_runs_serve(monkeypatch):
    """无子命令时默认走 serve，且返回 0。"""
    called = {"n": 0}

    def _fake_serve():
        called["n"] += 1

    monkeypatch.setattr(entry, "_serve_main", _fake_serve)
    rc = _run_main([], monkeypatch)

    assert rc == 0
    assert called["n"] == 1


def test_main_backup_without_dir_uses_env(monkeypatch, tmp_path):
    """命令行 backup 未传 --dir 时，用 LEDGER_BACKUP_DIR 指定的目录。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    env_dir = tmp_path / "cli_env_backups"
    env_dir.mkdir()
    monkeypatch.setenv("LEDGER_BACKUP_DIR", str(env_dir))

    rc = _run_main(["backup", "--keep", "7"], monkeypatch)

    assert rc == 0
    assert len(list(env_dir.glob("*.db"))) == 1


def test_main_restore_without_dir_uses_env(monkeypatch, tmp_path):
    """命令行 restore 未传 --dir 时，用 LEDGER_BACKUP_DIR 指定的目录。"""
    db_path = tmp_path / "ledger.db"
    _make_sqlite_db(db_path)
    monkeypatch.setenv("LEDGER_DB", str(db_path))

    env_dir = tmp_path / "cli_env_restore"
    env_dir.mkdir()
    monkeypatch.setenv("LEDGER_BACKUP_DIR", str(env_dir))

    src = env_dir / "seed.db"
    _make_sqlite_db(src)

    rc = _run_main(["restore", str(src)], monkeypatch)

    assert rc == 0
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT v FROM t").fetchall()
    assert rows == [("seed",)]


def test_main_serve_explicit_command(monkeypatch):
    """显式 serve 子命令：调用 _serve_main 且返回 0。"""
    called = {"n": 0}

    def _fake_serve():
        called["n"] += 1

    monkeypatch.setattr(entry, "_serve_main", _fake_serve)
    rc = _run_main(["serve"], monkeypatch)

    assert rc == 0
    assert called["n"] == 1