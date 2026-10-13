"""调度模块：使用 APScheduler 后台调度器周期抓取到期的源。"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from . import fetcher, store

# 全局调度器单例
_scheduler: BackgroundScheduler | None = None


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


def start_scheduler(app):
    """启动后台调度器：每 60 秒检查一次到期源并抓取。

    :param app: Flask 应用实例，从 app.config["FEEDFLOW"] 读取配置。
    """
    global _scheduler

    cfg = app.config["FEEDFLOW"]
    db_path = cfg["db_path"]
    default_interval = cfg["fetch_interval"]
    user_agent = cfg["user_agent"]

    def tick():
        """单次调度心跳：查询到期源并逐个抓取。"""
        try:
            due = store.due_feeds(db_path, _utcnow_iso(), default_interval)
            for feed in due:
                try:
                    result = fetcher.fetch_feed(db_path, feed, user_agent)
                    print(
                        f"[feedflow] 抓取 {feed.get('title') or feed.get('feed_url')} "
                        f"-> status={result['status']} added={result['added']}"
                        + (f" error={result['error']}" if result.get("error") else "")
                    )
                except Exception as exc:  # noqa: BLE001
                    # 故意宽捕获：单个源失败不应影响其他源，调度器不能因异常而崩溃。
                    print(f"[feedflow] 抓取源 {feed.get('id')} 异常: {exc}")
        except Exception as exc:  # noqa: BLE001
            # 故意宽捕获：调度心跳中的任何异常都不能让后台调度器崩溃。
            print(f"[feedflow] 调度 tick 异常: {exc}")

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        tick,
        "interval",
        seconds=60,
        id="fetch_tick",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    _scheduler = scheduler
    return scheduler


def shutdown_scheduler():
    """关闭全局后台调度器并将其置空。"""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown()
        except Exception as exc:  # noqa: BLE001
            print(f"[feedflow] 关闭调度器异常（忽略）: {exc}")
        _scheduler = None
