"""应用配置：从环境变量读取设置，提供全局单例。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 包目录为 src/ledger，向上两级即项目根目录
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# 默认值
DEFAULT_DB = "data/ledger.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8100


DEFAULT_LOG_LEVEL = "INFO"
ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class Settings:
    """应用设置。db_path 为绝对路径字符串。"""

    db_path: str
    host: str
    port: int
    log_level: str
    base_currency: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """读取环境变量并构造 Settings（带缓存）。"""
    raw_db = os.environ.get("LEDGER_DB", DEFAULT_DB)
    host = os.environ.get("LEDGER_HOST", DEFAULT_HOST)

    port_raw = os.environ.get("LEDGER_PORT", str(DEFAULT_PORT))
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        raise ValueError(f"LEDGER_PORT 非法: {port_raw!r}，必须为整数")

    raw_level = os.environ.get("LEDGER_LOG_LEVEL", DEFAULT_LOG_LEVEL)
    log_level = raw_level.upper()
    if log_level not in ALLOWED_LOG_LEVELS:
        raise ValueError(f"LEDGER_LOG_LEVEL 非法: {raw_level!r}，允许 DEBUG/INFO/WARNING/ERROR/CRITICAL")

    raw_ccy = os.environ.get("LEDGER_BASE_CURRENCY", "CNY")
    base_currency = raw_ccy.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", base_currency):
        raise ValueError(f"LEDGER_BASE_CURRENCY 非法: {raw_ccy!r}，必须为 ISO 4217 三字母大写代码")

    # 相对路径拼到项目根目录，绝对路径原样使用
    db_path = Path(raw_db)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    return Settings(
        db_path=str(db_path),
        host=host,
        port=port,
        log_level=log_level,
        base_currency=base_currency,
    )
