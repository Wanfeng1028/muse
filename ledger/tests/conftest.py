# tests/conftest.py
import os
import sys
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

# 将项目根目录下的 src 加入模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(scope="session")
def _env(tmp_path_factory):
    """会话级：设置临时数据库路径环境变量。"""
    tmp_dir = tmp_path_factory.mktemp("ledger")
    db_path = tmp_dir / "test.db"
    os.environ["LEDGER_DB"] = str(db_path)
    return str(db_path)


@pytest_asyncio.fixture(scope="session")
async def app(_env):
    """会话级：创建应用并手动初始化数据库与种子数据。

    ASGITransport 不会触发 lifespan，因此需手动初始化。
    """
    from ledger.database import get_session_factory, init_db
    from ledger.main import create_app
    from ledger.seed import ensure_seed

    application = create_app()
    await init_db()

    factory = get_session_factory()
    async with factory() as session:
        await ensure_seed(session)

    return application


@pytest_asyncio.fixture(scope="function")
async def client(app):
    """函数级：每个用例前清空数据表并重新播种，返回 httpx 客户端。"""
    from sqlalchemy import text

    from ledger.database import get_session_factory
    from ledger.seed import ensure_seed

    factory = get_session_factory()
    async with factory() as session:
        # 清空所有业务表（按依赖顺序删除）
        for t in (
            "statement_items",
            "statement_batches",
            "match_rules",
            "merchant_aliases",
            "statement_templates",
            "currencies",
            "transactions",
            "budgets",
            "recurring",
            "categories",
            "accounts",
        ):
            await session.execute(text(f"DELETE FROM {t}"))
        await session.commit()

        # 重新播种基础数据
        await ensure_seed(session)
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
