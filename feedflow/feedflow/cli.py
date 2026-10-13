"""feedflow 命令行入口。

支持子命令：
    serve        启动 Web 服务
    fetch        对到期的源抓取一次后退出
    import-opml  从 OPML 文件导入订阅源
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import config as config_module
from . import db as db_module
from . import fetcher, store
from . import opml as opml_module


def _cmd_serve(args: argparse.Namespace) -> int:
    """启动 Web 服务。"""
    from . import create_app

    cfg = config_module.load()
    app = create_app()
    host = args.host or cfg["host"]
    port = args.port or cfg["port"]
    # 关闭 reloader，避免调度器被重复启动
    app.run(host=host, port=port, use_reloader=False)
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    """对到期的源抓取一次。"""
    cfg = config_module.load()
    db_path = args.db or cfg["db_path"]
    fetch_interval = cfg["fetch_interval"]
    user_agent = cfg["user_agent"]
    db_module.init_db(db_path)

    now_iso = datetime.now(UTC).isoformat()
    due = store.due_feeds(db_path, now_iso, fetch_interval)

    if not due:
        print("没有到期的源。")
        return 0

    total_added = 0
    for feed in due:
        try:
            result = fetcher.fetch_feed(db_path, feed, user_agent)
        except Exception as exc:  # noqa: BLE001
            # 单源失败不影响其他源，故意宽捕获
            result = {"added": 0, "status": "error", "error": str(exc)[:300]}

        added = int(result.get("added", 0))
        status = result.get("status", "error")
        error = result.get("error", "")
        total_added += added

        name = feed.get("title") or feed.get("feed_url") or "未命名源"
        line = f"{name}: +{added}篇 ({status})"
        if status != "ok" and error:
            line += f" - {error}"
        print(line)

    print(f"合计新增 {total_added} 篇。")
    return 0


def _cmd_import_opml(args: argparse.Namespace) -> int:
    """从 OPML 文件导入订阅源。"""
    cfg = config_module.load()
    db_path = args.db or cfg["db_path"]
    db_module.init_db(db_path)

    path = Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 1

    try:
        xml_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        xml_text = path.read_text(encoding="utf-8", errors="replace")

    result = opml_module.import_opml(db_path, xml_text)
    print(f"imported={result.get('imported', 0)} skipped={result.get('skipped', 0)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="feedflow",
        description="FeedFlow · 自托管 RSS 阅读器",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="数据库路径（默认取自配置）",
    )

    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="启动 Web 服务")
    p_serve.add_argument("--host", default=None, help="监听地址（默认取自配置）")
    p_serve.add_argument("--port", type=int, default=None, help="监听端口（默认取自配置）")
    p_serve.set_defaults(func=_cmd_serve)

    p_fetch = sub.add_parser("fetch", help="对到期源抓取一次")
    p_fetch.set_defaults(func=_cmd_fetch)

    p_import = sub.add_parser("import-opml", help="导入 OPML 文件")
    p_import.add_argument("file", help="OPML 文件路径")
    p_import.set_defaults(func=_cmd_import_opml)

    return parser


def main(argv=None) -> int:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
