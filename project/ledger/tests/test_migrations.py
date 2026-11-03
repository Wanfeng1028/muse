"""迁移模块测试：全新库、v1 老库升级、损坏文件。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ledger import models
from ledger.migrations import (
    CURRENT_VERSION,
    V1_TABLES,
    V2_TABLES,
    MigrationError,
    run_migrations,
)


async def _list_tables(engine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        return {row[0] for row in result.fetchall()}


async def _get_user_version(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA user_version"))
        return int(result.scalar_one())


def _make_engine(tmp_path, name: str = "test.db"):
    db_file = tmp_path / name
    return create_async_engine(f"sqlite+aiosqlite:///{db_file}")


async def test_fresh_database(tmp_path):
    engine = _make_engine(tmp_path)
    try:
        version = await run_migrations(engine)
        assert version == CURRENT_VERSION
        assert await _get_user_version(engine) == CURRENT_VERSION

        tables = await _list_tables(engine)
        for name in V1_TABLES:
            assert name in tables, f"缺少 v1 表 {name}"
        for name in V2_TABLES:
            assert name in tables, f"缺少 v2 表 {name}"
        # 至少 9 张表
        assert len({*V1_TABLES, *V2_TABLES}) == 9

        # 幂等
        version2 = await run_migrations(engine)
        assert version2 == CURRENT_VERSION
    finally:
        await engine.dispose()


async def test_upgrade_from_v1(tmp_path):
    engine = _make_engine(tmp_path)
    try:
        # 只建 v1 五表
        v1_tables = [
            models.Account.__table__,
            models.Category.__table__,
            models.Transaction.__table__,
            models.Budget.__table__,
            models.Recurring.__table__,
        ]
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: models.Base.metadata.create_all(
                    sync_conn, tables=v1_tables
                )
            )

        # 插入一条 account
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO accounts "
                    "(name, type, currency, opening_balance_cents, note, is_archived, "
                    " created_at, updated_at) "
                    "VALUES ('测试账户', 'cash', 'CNY', 12345, '', 0, "
                    "'2024-01-01T00:00:00+00:00', '2024-01-01T00:00:00+00:00')"
                )
            )

        # user_version 保持 0
        assert await _get_user_version(engine) == 0

        tables_before = await _list_tables(engine)
        for name in V2_TABLES:
            assert name not in tables_before

        # 执行迁移
        version = await run_migrations(engine)
        assert version == CURRENT_VERSION
        assert await _get_user_version(engine) == CURRENT_VERSION

        tables_after = await _list_tables(engine)
        for name in V2_TABLES:
            assert name in tables_after, f"迁移后缺少 {name}"

        # 老数据保留
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name, opening_balance_cents FROM accounts")
            )
            rows = result.fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "测试账户"
            assert rows[0][1] == 12345
    finally:
        await engine.dispose()


async def test_corrupt_file(tmp_path):
    db_file = tmp_path / "corrupt.db"
    db_file.write_bytes(b"\x00\x01\x02\x03 not a sqlite file \xff\xfe" * 100)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    try:
        with pytest.raises(MigrationError):
            await run_migrations(engine)
    finally:
        await engine.dispose()
