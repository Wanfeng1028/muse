"""调度模块：使用 APScheduler 后台调度器周期抓取到期的源。"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler

from . import fetcher, store
from .db import get_conn
from .logging import get_logger

# 全局调度器单例
_scheduler: BackgroundScheduler | None = None

# 补跑判定阈值（秒）：上次 tick 距今超过该值即立即补跑一次
_CATCHUP_THRESHOLD_SECONDS = 90

_log = get_logger(__name__)


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> datetime | None:
    """解析 ISO8601 字符串为 datetime，失败返回 None。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _job_state_get(db_path: str, key: str) -> str:
    """读取 job_state 表中指定 key 的 value，不存在返回空串。"""
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT value FROM job_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return ""
    # sqlite3.Row 或 tuple 均兼容
    try:
        return row["value"] or ""
    except (TypeError, IndexError):
        return row[0] or ""


def _job_state_set(db_path: str, key: str, value: str) -> None:
    """写入/更新 job_state 表中指定 key 的 value。"""
    now = _utcnow_iso()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO job_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
        conn.commit()


def _run_tick(db_path: str, default_interval: int, user_agent: str,
              fetch_timeout, fetch_retries, catchup: bool = False) -> None:
    """执行一次调度心跳：查询到期源并逐个抓取。

    :param db_path: SQLite 数据库路径。
    :param default_interval: 默认抓取间隔（秒），传给 store.due_feeds。
    :param user_agent: 抓取时使用的 User-Agent。
    :param fetch_timeout: 单次抓取超时（秒），传给 fetcher.fetch_feed。
    :param fetch_retries: 抓取失败重试次数，传给 fetcher.fetch_feed。
    :param catchup: 是否为启动补跑（仅用于日志区分）。
    """
    try:
        _job_state_set(db_path, "last_tick_at", _utcnow_iso())
        due = store.due_feeds(db_path, _utcnow_iso(), default_interval)
    except Exception as exc:  # noqa: BLE001
        # 故意宽捕获：调度心跳中的任何异常都不能让后台调度器崩溃。
        _log.error("调度 tick 前置阶段异常: %s", exc, extra={"catchup": catchup})
        return

    success = 0
    failed = 0
    _log.info(
        "调度 tick 开始: due=%d catchup=%s",
        len(due),
        catchup,
        extra={"due": len(due), "catchup": catchup},
    )

    for feed in due:
        feed_id = feed.get("id")
        try:
            result = fetcher.fetch_feed(
                db_path,
                feed,
                user_agent,
                timeout=fetch_timeout,
                retries=fetch_retries,
            )
            status = result.get("status")
            added = result.get("added")
            error = result.get("error")
            if error:
                failed += 1
            else:
                success += 1
            _log.info(
                "抓取源完成: feed_id=%s status=%s added=%s error=%s",
                feed_id,
                status,
                added,
                error,
                extra={
                    "feed_id": feed_id,
                    "status": status,
                    "added": added,
                    "error": error,
                },
            )
        except Exception as exc:  # noqa: BLE001
            # 故意宽捕获：单个源失败不应影响其他源，调度器不能因异常而崩溃。
            failed += 1
            _log.error(
                "抓取源异常: feed_id=%s error=%s",
                feed_id,
                exc,
                extra={"feed_id": feed_id, "error": str(exc)},
            )

    try:
        _job_state_set(db_path, "last_success_at", _utcnow_iso())
    except Exception as exc:  # noqa: BLE001
        _log.error("写入 last_success_at 失败: %s", exc, extra={"catchup": catchup})

    _log.info(
        "调度 tick 结束: due=%d success=%d failed=%d catchup=%s",
        len(due),
        success,
        failed,
        catchup,
        extra={
            "due": len(due),
            "success": success,
            "failed": failed,
            "catchup": catchup,
        },
    )


def start_scheduler(app):
    """启动后台调度器：每 60 秒检查一次到期源并抓取。

    启动时若上次 tick 距今超过 90 秒，会立即同步执行一次补跑（catchup）。

    :param app: Flask 应用实例，从 app.config["FEEDFLOW"] 读取配置。
    """
    global _scheduler

    cfg = app.config["FEEDFLOW"]
    db_path = cfg["db_path"]
    default_interval = cfg["fetch_interval"]
    user_agent = cfg["user_agent"]
    fetch_timeout = cfg.get("fetch_timeout")
    fetch_retries = cfg.get("fetch_retries")

    def tick():
        """APScheduler 定时任务入口：执行一次心跳。"""
        _run_tick(
            db_path,
            default_interval,
            user_agent,
            fetch_timeout,
            fetch_retries,
            catchup=False,
        )

    # 启动补跑：上次 tick 距今超过阈值则立即同步执行一次
    try:
        last_tick_raw = _job_state_get(db_path, "last_tick_at")
        last_tick_dt = _parse_iso(last_tick_raw)
        now = datetime.now(UTC)
        if last_tick_dt is None:
            # 从未 tick 过，视为需要补跑
            _log.info(
                "调度启动补跑: catchup=true reason=no_previous_tick",
                extra={"catchup": True},
            )
            _run_tick(
                db_path,
                default_interval,
                user_agent,
                fetch_timeout,
                fetch_retries,
                catchup=True,
            )
        else:
            delta = (now - last_tick_dt).total_seconds()
            if delta > _CATCHUP_THRESHOLD_SECONDS:
                _log.info(
                    "调度启动补跑: catchup=true elapsed=%.1fs",
                    delta,
                    extra={"catchup": True, "elapsed": delta},
                )
                _run_tick(
                    db_path,
                    default_interval,
                    user_agent,
                    fetch_timeout,
                    fetch_retries,
                    catchup=True,
                )
    except Exception as exc:  # noqa: BLE001
        # 补跑失败不影响调度器启动。
        _log.error("启动补跑异常: %s", exc, extra={"catchup": True})

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        tick,
        "interval",
        seconds=60,
        id="fetch_tick",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
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
            _log.error("关闭调度器异常（忽略）: %s", exc)
        _scheduler = None
