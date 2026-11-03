"""备份/恢复工具（同步，零第三方依赖）。

仅依赖标准库 sqlite3/shutil 与项目内 ledger.logging。
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ledger.logging import get_logger

logger = get_logger("backup")


class BackupError(Exception):
    """备份/恢复过程中的错误。"""


def integrity_check(db_path: str) -> None:
    """对 SQLite 数据库执行 PRAGMA integrity_check。"""
    path = Path(db_path)
    if not path.exists():
        raise BackupError(f"数据库文件不存在: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        raise BackupError(f"数据库文件损坏或不是 SQLite 库: {db_path}: {exc}") from exc
    try:
        cur = conn.execute("PRAGMA integrity_check")
        row = cur.fetchone()
        first = row[0] if row else ""
        if first != "ok":
            raise BackupError(f"完整性检查失败: {db_path}: {first}")
    except sqlite3.Error as exc:
        raise BackupError(f"完整性检查失败: {db_path}: {exc}") from exc
    finally:
        conn.close()


def _prune_backups(backup_dir: Path, keep: int) -> int:
    """按文件名排序保留最新 keep 个 ledger-*.db，返回删除数量。"""
    if keep < 0:
        keep = 0
    files = sorted(backup_dir.glob("ledger-*.db"))
    to_delete = files[:-keep] if keep > 0 else files
    for f in to_delete:
        try:
            f.unlink()
        except OSError:
            logger.warning("删除旧备份失败: %s", f)
    return len(to_delete)


def _unique_target(bdir: Path, stem: str) -> Path:
    """同秒多次备份时加 -N 后缀避免文件名碰撞。"""
    target = bdir / f"{stem}.db"
    n = 1
    while target.exists():
        target = bdir / f"{stem}-{n}.db"
        n += 1
    return target


def backup_db(db_path: str, backup_dir: str, keep: int = 7) -> str:
    """备份数据库，返回备份文件路径。"""
    integrity_check(db_path)

    bdir = Path(backup_dir)
    bdir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = _unique_target(bdir, f"ledger-{ts}")

    logger.info("开始备份: %s -> %s", db_path, target)
    try:
        shutil.copy2(db_path, target)
    except OSError as exc:
        # 磁盘满/权限不足：清理半成品，不留坏备份
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
        raise BackupError(f"备份写入失败: {target}: {exc}") from exc
    logger.info("备份完成: %s", target)

    removed = _prune_backups(bdir, keep)
    if removed:
        logger.info("修剪备份: 删除 %d 个旧文件", removed)

    return str(target)


def restore_db(db_path: str, backup_file: str, backup_dir: str) -> str:
    """从备份恢复数据库，返回恢复后的 db_path。"""
    bfile = Path(backup_file)
    if not bfile.exists():
        raise BackupError(f"备份文件不存在: {backup_file}")

    integrity_check(backup_file)

    if Path(db_path).exists():
        snapshot = backup_db(db_path, backup_dir, keep=30)
        logger.info("恢复前安全快照: %s", snapshot)

    logger.info("开始恢复: %s -> %s", backup_file, db_path)
    shutil.copy2(backup_file, db_path)

    integrity_check(db_path)
    logger.info("恢复完成: %s", db_path)
    return db_path
