"""配置模块：从环境变量加载运行配置。"""

import os
from pathlib import Path

# 项目根目录（即含 requirements.txt 的目录）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB = "data/feedflow.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8300
DEFAULT_FETCH_INTERVAL = 30
DEFAULT_FETCH_TIMEOUT = 20
DEFAULT_FETCH_RETRIES = 3
DEFAULT_USER_AGENT = "FeedFlow/0.1"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_BACKUP_DIR = "data/backups"
DEFAULT_DIGEST_N = 20
DEFAULT_EXTRACT_TIMEOUT = 15
DEFAULT_FEVER_API_KEY = ""



def _parse_int(value, default):
    """把环境变量转成 int，非法则回退默认值。"""
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _resolve_path(value):
    """把可能是相对路径的值解析为基于项目根目录的绝对路径。"""
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def load() -> dict:
    """读取环境变量并返回配置字典。

    返回键：db_path / host / port / fetch_interval / fetch_timeout /
    fetch_retries / user_agent / log_level / backup_dir / digest_n /
    extract_timeout / fever_api_key
    """

    db_path = _resolve_path(os.environ.get("FEEDFLOW_DB", DEFAULT_DB))

    host = os.environ.get("FEEDFLOW_HOST", DEFAULT_HOST)

    port = _parse_int(os.environ.get("FEEDFLOW_PORT"), DEFAULT_PORT)

    fetch_interval = _parse_int(
        os.environ.get("FEEDFLOW_FETCH_INTERVAL"), DEFAULT_FETCH_INTERVAL
    )

    fetch_timeout = _parse_int(
        os.environ.get("FEEDFLOW_FETCH_TIMEOUT"), DEFAULT_FETCH_TIMEOUT
    )

    fetch_retries = _parse_int(
        os.environ.get("FEEDFLOW_FETCH_RETRIES"), DEFAULT_FETCH_RETRIES
    )

    user_agent = os.environ.get("FEEDFLOW_USER_AGENT", DEFAULT_USER_AGENT)

    log_level = os.environ.get("FEEDFLOW_LOG_LEVEL", DEFAULT_LOG_LEVEL)

    backup_dir = _resolve_path(
        os.environ.get("FEEDFLOW_BACKUP_DIR", DEFAULT_BACKUP_DIR)
    )

    digest_n = _parse_int(os.environ.get("FEEDFLOW_DIGEST_N"), DEFAULT_DIGEST_N)

    extract_timeout = _parse_int(
        os.environ.get("FEEDFLOW_EXTRACT_TIMEOUT"), DEFAULT_EXTRACT_TIMEOUT
    )

    fever_api_key = (os.environ.get("FEEDFLOW_FEVER_API_KEY") or "").strip()

    return {

        "db_path": str(db_path),
        "host": host,
        "port": port,
        "fetch_interval": fetch_interval,
        "fetch_timeout": fetch_timeout,
        "fetch_retries": fetch_retries,
        "user_agent": user_agent,
        "log_level": log_level,
        "backup_dir": str(backup_dir),
        "digest_n": digest_n,
        "extract_timeout": extract_timeout,
        "fever_api_key": fever_api_key,
    }



def _fail(reason):
    """校验失败时 fail fast：打印中文原因并退出。"""
    raise SystemExit(f"配置校验失败：{reason}")


def validate(cfg: dict) -> None:
    """校验配置合法性，非法时 fail fast。

    校验项：
    - db 父目录可写
    - port 在 1-65535
    - fetch_interval > 0
    - fetch_timeout > 0
    - fetch_retries >= 0

    缺失的新增键用默认值回填（兼容手写 cfg 的测试）。
    """
    cfg.setdefault("fetch_timeout", DEFAULT_FETCH_TIMEOUT)
    cfg.setdefault("fetch_retries", DEFAULT_FETCH_RETRIES)
    cfg.setdefault("log_level", DEFAULT_LOG_LEVEL)
    cfg.setdefault("backup_dir", DEFAULT_BACKUP_DIR)
    cfg.setdefault("digest_n", DEFAULT_DIGEST_N)
    cfg.setdefault("extract_timeout", DEFAULT_EXTRACT_TIMEOUT)
    cfg.setdefault("fever_api_key", DEFAULT_FEVER_API_KEY)

    # 校验 port 范围
    port = cfg.get("port")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        _fail(f"FEEDFLOW_PORT 必须在 1-65535 之间，当前为 {port!r}")

    # 校验抓取间隔
    fetch_interval = cfg.get("fetch_interval")
    if not isinstance(fetch_interval, int) or fetch_interval <= 0:
        _fail(f"FEEDFLOW_FETCH_INTERVAL 必须大于 0，当前为 {fetch_interval!r}")

    # 校验抓取超时
    fetch_timeout = cfg.get("fetch_timeout")
    if not isinstance(fetch_timeout, int) or fetch_timeout <= 0:
        _fail(f"FEEDFLOW_FETCH_TIMEOUT 必须大于 0，当前为 {fetch_timeout!r}")

    # 校验重试次数
    fetch_retries = cfg.get("fetch_retries")
    if not isinstance(fetch_retries, int) or fetch_retries < 0:
        _fail(f"FEEDFLOW_FETCH_RETRIES 必须大于等于 0，当前为 {fetch_retries!r}")

    # 校验摘要条数
    digest_n = cfg.get("digest_n")
    if not isinstance(digest_n, int) or digest_n < 1:
        _fail(f"FEEDFLOW_DIGEST_N 必须大于等于 1，当前为 {digest_n!r}")

    # 校验正文提取超时
    extract_timeout = cfg.get("extract_timeout")
    if not isinstance(extract_timeout, int) or extract_timeout <= 0:
        _fail(f"FEEDFLOW_EXTRACT_TIMEOUT 必须大于 0，当前为 {extract_timeout!r}")


    # 校验数据库父目录可写
    db_path = cfg.get("db_path")
    if not db_path:
        _fail("FEEDFLOW_DB 不能为空")

    db_parent = Path(db_path).parent
    try:
        db_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(f"数据库父目录无法创建：{db_parent}（{exc}）")

    if not os.access(str(db_parent), os.W_OK):
        _fail(f"数据库父目录不可写：{db_parent}")
