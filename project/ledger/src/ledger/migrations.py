"""数据库迁移：使用 PRAGMA user_version 进行版本化。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.exc import DatabaseError
from sqlalchemy.schema import CreateTable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


CURRENT_VERSION = 6


V1_TABLES = ("accounts", "categories", "transactions", "budgets", "recurring")
V2_TABLES = (
    "statement_templates",
    "match_rules",
    "statement_batches",
    "statement_items",
)


class MigrationError(Exception):
    """数据库迁移失败。"""


def _compile_create_table(table) -> str:
    """将 SQLAlchemy Table 对象编译为 SQLite 的 CREATE TABLE 语句。"""
    ddl = str(CreateTable(table).compile(dialect=sqlite_dialect.dialect()))
    # 加 IF NOT EXISTS 保证幂等
    return ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)


async def _read_user_version(conn) -> int:
    result = await conn.execute(text("PRAGMA user_version"))
    return int(result.scalar_one())


async def _table_exists(conn, name: str) -> bool:
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    )
    return result.first() is not None


async def _migrate_v2_to_v3(conn) -> None:
    """v2 -> v3：新建 currencies 表；transactions 表加 currency 列（若不存在）。"""
    from ledger import models  # noqa: F401  局部导入，避免循环

    table = models.Base.metadata.tables["currencies"]
    await conn.execute(text(_compile_create_table(table)))
    result = await conn.execute(text("PRAGMA table_info(transactions)"))
    cols = {row[1] for row in result.fetchall()}
    if "currency" not in cols:
        await conn.execute(text("ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'"))


async def _migrate_v3_to_v4(conn) -> None:
    """v3 -> v4：新建 merchant_aliases 表（商户别名学习）。"""
    from ledger import models  # noqa: F401  局部导入，避免循环

    table = models.Base.metadata.tables["merchant_aliases"]
    await conn.execute(text(_compile_create_table(table)))


async def _migrate_v5_to_v6(conn) -> None:
    """v5 -> v6：match_rules 加规则引擎列，statement_items 加 suggested_rule_id，新建 report_schemes 表。"""
    from ledger import models  # noqa: F401 局部导入，避免循环
    result = await conn.execute(text("PRAGMA table_info(match_rules)"))
    rule_cols = {row[1] for row in result.fetchall()}
    if "pattern_type" not in rule_cols:
        await conn.execute(text("ALTER TABLE match_rules ADD COLUMN pattern_type TEXT NOT NULL DEFAULT 'keyword'"))
    if "is_enabled" not in rule_cols:
        await conn.execute(text("ALTER TABLE match_rules ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1"))
    if "hit_count" not in rule_cols:
        await conn.execute(text("ALTER TABLE match_rules ADD COLUMN hit_count INTEGER NOT NULL DEFAULT 0"))
    result = await conn.execute(text("PRAGMA table_info(statement_items)"))
    item_cols = {row[1] for row in result.fetchall()}
    if "suggested_rule_id" not in item_cols:
        await conn.execute(text("ALTER TABLE statement_items ADD COLUMN suggested_rule_id INTEGER"))
    await conn.execute(text(_compile_create_table(models.Base.metadata.tables["report_schemes"])))
    result = await conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='match_rules'")
    )
    create_sql = result.scalar_one_or_none() or ""
    if "uq_match_rules_keyword_direction" in create_sql:
        await conn.execute(text(
            "CREATE TABLE match_rules_new ("
            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
            "keyword VARCHAR NOT NULL, "
            "category_id INTEGER NOT NULL REFERENCES categories (id), "
            "direction VARCHAR NOT NULL DEFAULT 'any', "
            "priority INTEGER NOT NULL DEFAULT 0, "
            "created_at VARCHAR NOT NULL, "
            "pattern_type VARCHAR NOT NULL DEFAULT 'keyword', "
            "is_enabled INTEGER NOT NULL DEFAULT 1, "
            "hit_count INTEGER NOT NULL DEFAULT 0, "
            "CONSTRAINT uq_match_rules_keyword_ptype_direction UNIQUE (keyword, pattern_type, direction)"
            ")"
        ))
        await conn.execute(text(
            "INSERT INTO match_rules_new "
            "(id, keyword, category_id, direction, priority, created_at, pattern_type, is_enabled, hit_count) "
            "SELECT id, keyword, category_id, direction, priority, created_at, "
            "COALESCE(pattern_type, 'keyword'), COALESCE(is_enabled, 1), COALESCE(hit_count, 0) "
            "FROM match_rules"
        ))
        await conn.execute(text("DROP TABLE match_rules"))
        await conn.execute(text("ALTER TABLE match_rules_new RENAME TO match_rules"))



async def _migrate_v4_to_v5(conn) -> None:
    """v4 -> v5：新建 ocr_reviews 表（OCR 审核队列）。"""
    from ledger import models  # noqa: F401  局部导入，避免循环

    table = models.Base.metadata.tables["ocr_reviews"]
    await conn.execute(text(_compile_create_table(table)))


async def run_migrations(engine: AsyncEngine) -> int:
    """执行迁移，返回迁移后的 user_version。"""
    from ledger import models  # noqa: F401  注册所有表定义

    try:
        async with engine.begin() as conn:
            version = await _read_user_version(conn)

            if version >= CURRENT_VERSION:
                return version

            accounts_exists = await _table_exists(conn, "accounts")

            if version == 0 and not accounts_exists:
                # 全新库：models 已包含 currencies 表与 currency 列
                await conn.run_sync(models.Base.metadata.create_all)
            else:
                # 老库：按版本逐级补齐
                if version < 2:
                    for table_name in V2_TABLES:
                        table = models.Base.metadata.tables[table_name]
                        ddl = _compile_create_table(table)
                        await conn.execute(text(ddl))
                if version < 3:
                    await _migrate_v2_to_v3(conn)

                if version < 4:
                    await _migrate_v3_to_v4(conn)

                if version < 5:
                    await _migrate_v4_to_v5(conn)
                if version < 6:
                    await _migrate_v5_to_v6(conn)

            await conn.execute(text(f"PRAGMA user_version = {CURRENT_VERSION}"))
            return CURRENT_VERSION
    except sqlite3.DatabaseError as exc:
        raise MigrationError(f"数据库文件损坏或不是 SQLite 库: {_engine_path(engine)}") from exc
    except DatabaseError as exc:
        # SQLAlchemy 包装后的 sqlite 错误
        orig = getattr(exc, "orig", None)
        if isinstance(orig, sqlite3.DatabaseError):
            raise MigrationError(f"数据库文件损坏或不是 SQLite 库: {_engine_path(engine)}") from exc
        raise


def _engine_path(engine: AsyncEngine) -> str:
    url = engine.url
    if url.database and url.database != ":memory:":
        return str(Path(url.database))
    return str(url)
