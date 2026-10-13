"""数据库热备份与恢复。

- backup：使用 sqlite3 的在线备份接口，把运行中的库热备到目标目录，并只保留最近 7 份。
- restore：校验备份文件合法性后覆盖目标库，并清理 WAL/SHM 残留。
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .logging import get_logger

log = get_logger(__name__)

# 备份文件保留数量
_KEEP = 7
# 备份文件名前缀
_PREFIX = "feedflow-"


def backup(db_path: str, backup_dir: str) -> str:
    """对数据库做热备份。

    参数：
        db_path：源数据库路径。
        backup_dir：备份输出目录，不存在则创建。

    返回：
        新生成的备份文件路径。
    """
    src = Path(db_path)
    out_dir = Path(backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    target = out_dir / f"{_PREFIX}{stamp}.db"

    # 使用 sqlite3 在线备份接口，避免直接拷贝导致的不一致
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(target))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    log.info("数据库已备份：%s -> %s", src, target)

    # 只保留最近 _KEEP 个备份，按文件名（含时间戳）升序删除旧的
    existing = sorted(
        p for p in out_dir.glob(f"{_PREFIX}*.db") if p.is_file()
    )
    if len(existing) > _KEEP:
        for old in existing[: len(existing) - _KEEP]:
            try:
                old.unlink()
                log.info("已清理旧备份：%s", old)
            except OSError as exc:  # 清理失败不影响本次备份
                log.warning("清理旧备份失败：%s - %s", old, exc)

    return str(target)


def restore(backup_path: str, db_path: str) -> None:
    """用备份文件覆盖目标数据库。

    参数：
        backup_path：备份文件路径。
        db_path：要恢复到的目标数据库路径。
    """
    src = Path(backup_path)
    dst = Path(db_path)

    if not src.is_file():
        raise FileNotFoundError(f"备份文件不存在：{src}")

    # 校验备份文件是合法 sqlite 库：查 sqlite_master 会强制读取库 schema，
    # 非法文件在此抛 sqlite3.DatabaseError（SELECT 1 不读 schema，验不出）。
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"备份文件不是合法的 SQLite 数据库：{src}") from exc
    finally:
        conn.close()

    # 确保目标目录存在
    dst.parent.mkdir(parents=True, exist_ok=True)

    # 覆盖拷贝
    shutil.copyfile(str(src), str(dst))

    # 清理目标的 WAL/SHM 残留，避免旧日志与新库不一致
    for suffix in ("-wal", "-shm"):
        residue = Path(str(dst) + suffix)
        if residue.exists():
            try:
                residue.unlink()
                log.info("已删除残留文件：%s", residue)
            except OSError as exc:  # 残留清理失败仅告警
                log.warning("删除残留文件失败：%s - %s", residue, exc)

    log.info("数据库已恢复：%s -> %s", src, dst)
