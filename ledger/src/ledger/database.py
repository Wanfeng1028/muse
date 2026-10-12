# src/ledger/database.py
"""数据库连接与会话管理（SQLAlchemy 2.0 异步 + SQLite/aiosqlite）。"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import String
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。

    datetime 类型统一映射为 TEXT（存 UTC ISO8601 字符串），
    与契约中「created_at/updated_at 存 TEXT」保持一致。
    """

    type_annotation_map = {
        datetime: String,
        str: String,
    }


def _project_root() -> Path:
    """返回项目根目录（src/ledger/database.py -> 上溯三级）。"""
    return Path(__file__).resolve().parents[2]


def _resolve_db_path() -> str:
    """解析 LEDGER_DB 环境变量；相对路径相对项目根目录。"""
    raw = os.environ.get("LEDGER_DB", "data/ledger.db")
    p = Path(raw)
    if not p.is_absolute():
        p = _project_root() / p
    return str(p)


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """获取（惰性创建）模块级单例 async engine。"""
    global _engine
    if _engine is None:
        db_path = _resolve_db_path()
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取（惰性创建）模块级单例 session factory。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供一个异步数据库会话。"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """初始化数据库：确保 data 目录存在并创建所有表。"""
    # 在函数内导入 models，注册所有表定义，避免循环导入
    from ledger import models  # noqa: F401

    db_path = Path(_resolve_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def utcnow_iso() -> str:
    """当前 UTC 时间 ISO8601 字符串（供模型默认值使用）。"""
    return datetime.now(UTC).isoformat()
