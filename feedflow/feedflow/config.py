"""配置模块：从环境变量加载运行配置。"""

import os
from pathlib import Path

# 项目根目录（即含 requirements.txt 的目录）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DB = "data/feedflow.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8300
DEFAULT_FETCH_INTERVAL = 30
DEFAULT_USER_AGENT = "FeedFlow/0.1"


def _parse_int(value, default):
    """把环境变量转成 int，非法则回退默认值。"""
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def load() -> dict:
    """读取环境变量并返回配置字典。

    返回键：db_path / host / port / fetch_interval / user_agent
    """
    db_env = os.environ.get("FEEDFLOW_DB", DEFAULT_DB)
    db_path = Path(db_env)
    if not db_path.is_absolute():
        # 相对路径相对项目根目录
        db_path = PROJECT_ROOT / db_path

    host = os.environ.get("FEEDFLOW_HOST", DEFAULT_HOST)

    port = _parse_int(os.environ.get("FEEDFLOW_PORT"), DEFAULT_PORT)

    fetch_interval = _parse_int(
        os.environ.get("FEEDFLOW_FETCH_INTERVAL"), DEFAULT_FETCH_INTERVAL
    )

    user_agent = os.environ.get("FEEDFLOW_USER_AGENT", DEFAULT_USER_AGENT)

    return {
        "db_path": str(db_path),
        "host": host,
        "port": port,
        "fetch_interval": fetch_interval,
        "user_agent": user_agent,
    }
