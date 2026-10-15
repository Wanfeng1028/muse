# 入口函数名: main
"""ledger 命令行入口：serve / backup / restore 子命令。"""

import argparse
import os
import sys
from pathlib import Path

from ledger.backup import BackupError, backup_db, restore_db
from ledger.config import PROJECT_ROOT
from ledger.main import main as _serve_main


def _default_backup_dir() -> str:
    env = os.environ.get("LEDGER_BACKUP_DIR")
    if env:
        return env
    return str(Path(PROJECT_ROOT) / "data" / "backups")


def _cmd_serve(_args: argparse.Namespace) -> int:
    _serve_main()
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    from ledger.config import get_settings

    settings = get_settings()
    try:
        path = backup_db(settings.db_path, args.dir, keep=args.keep)
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(f"备份完成: {path}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    from ledger.config import get_settings

    settings = get_settings()
    try:
        db_path = restore_db(settings.db_path, args.file, args.dir)
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    print(f"恢复完成: {db_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ledger")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="启动服务（默认）")

    p_backup = sub.add_parser("backup", help="备份数据库")
    p_backup.add_argument("--dir", default=None)
    p_backup.add_argument("--keep", type=int, default=7)

    p_restore = sub.add_parser("restore", help="从备份恢复")
    p_restore.add_argument("file")
    p_restore.add_argument("--dir", default=None)

    args = parser.parse_args()

    if args.command in ("backup", "restore") and args.dir is None:
        args.dir = _default_backup_dir()

    if args.command is None or args.command == "serve":
        return _cmd_serve(args)
    if args.command == "backup":
        return _cmd_backup(args)
    if args.command == "restore":
        return _cmd_restore(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
