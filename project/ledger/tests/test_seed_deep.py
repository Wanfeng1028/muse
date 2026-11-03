"""seed 模块深度测试：边界、失败注入、幂等、并发、中文场景。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from ledger.database import get_session_factory
from ledger.models import Category, Currency, utcnow
from ledger.seed import DEFAULT_CATEGORIES, ensure_seed


def _category_signature() -> set[tuple[str, str, str, str, int]]:
    return {(n, k, i, c, o) for n, k, i, c, o in DEFAULT_CATEGORIES}


@pytest.mark.asyncio
async def test_seed_creates_all_default_categories(client):
    """空表时 ensure_seed 写入全部默认分类。"""
    factory = get_session_factory()
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(Category))
        assert count == len(DEFAULT_CATEGORIES)
        assert count == 18

        rows = (await session.execute(select(Category))).scalars().all()
        names_kinds = {(c.name, c.kind) for c in rows}
        assert ("餐饮", "expense") in names_kinds
        assert ("工资", "income") in names_kinds


@pytest.mark.asyncio
async def test_seed_category_fields_exact(client):
    """默认分类的图标、颜色、排序号与常量逐字一致。"""
    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(Category))).scalars().all()
        by_key = {(c.name, c.kind): c for c in rows}
        canyin = by_key[("餐饮", "expense")]
        assert canyin.icon == "🍜"
        assert canyin.color == "#ef4444"
        assert canyin.sort_order == 10

        gongzi = by_key[("工资", "income")]
        assert gongzi.icon == "💼"
        assert gongzi.sort_order == 10


@pytest.mark.asyncio
async def test_seed_idempotent_repeated_call(client):
    """重复调用 ensure_seed 不产生重复分类。"""
    factory = get_session_factory()
    async with factory() as session:
        before = await session.scalar(select(func.count()).select_from(Category))
        await ensure_seed(session)
        await ensure_seed(session)
        after = await session.scalar(select(func.count()).select_from(Category))
        assert before == len(DEFAULT_CATEGORIES)
        assert after == before


@pytest.mark.asyncio
async def test_seed_idempotent_does_not_change_existing_row(client):
    """已有分类行不被覆盖：改一条再调用 ensure_seed，改动保留。"""
    factory = get_session_factory()
    async with factory() as session:
        target = await session.scalar(
            select(Category).where(Category.name == "餐饮", Category.kind == "expense")
        )
        target.color = "#000000"
        await session.commit()

        await ensure_seed(session)
        await session.refresh(target)
        assert target.color == "#000000"
        assert target.icon == "🍜"


@pytest.mark.asyncio
async def test_seed_base_currency_inserted_once(client):
    """本位币汇率行插入一次，重复调用不翻倍。"""
    factory = get_session_factory()
    async with factory() as session:
        first = await session.scalar(select(func.count()).select_from(Currency))
        await ensure_seed(session)
        second = await session.scalar(select(func.count()).select_from(Currency))
        assert first == second
        assert first >= 1

        base = await session.scalar(select(Currency).where(Currency.rate_to_base == 1.0))
        assert base is not None
        assert base.rate_to_base == 1.0


@pytest.mark.asyncio
async def test_seed_preserves_pre_existing_currency(client):
    """本位币行已存在时不重复插入。"""
    from ledger.config import get_settings

    factory = get_session_factory()
    code = get_settings().base_currency
    async with factory() as session:
        existing = await session.scalar(select(Currency).where(Currency.code == code))
        assert existing is not None
        before_code = existing.code

        await ensure_seed(session)
        again = await session.scalar(select(Currency).where(Currency.code == code))
        assert again is not None
        assert again.code == before_code


@pytest.mark.asyncio
async def test_seed_skips_when_categories_nonempty(client):
    """分类表非空时 ensure_seed 提前返回，不新增行。"""
    factory = get_session_factory()
    async with factory() as session:
        extra = Category(name="自定义", kind="expense", icon="🧪", color="#111111", sort_order=999)
        session.add(extra)
        await session.commit()
        baseline = await session.scalar(select(func.count()).select_from(Category))

        await ensure_seed(session)
        after = await session.scalar(select(func.count()).select_from(Category))
        assert after == baseline
        assert after == len(DEFAULT_CATEGORIES) + 1


@pytest.mark.asyncio
async def test_seed_db_error_on_category_query(client, monkeypatch):
    """分类查询抛异常时 ensure_seed 向上抛出，不吞掉。"""
    factory = get_session_factory()

    real_scalar = None
    async with factory() as session:
        real_scalar = session.scalar

        call_state = {"n": 0}

        async def flaky_scalar(stmt):
            call_state["n"] += 1
            if call_state["n"] == 2:
                raise RuntimeError("db blew up")
            return await real_scalar(stmt)

        monkeypatch.setattr(session, "scalar", flaky_scalar)

        with pytest.raises(RuntimeError) as ei:
            await ensure_seed(session)
        assert "db blew up" in str(ei.value)


@pytest.mark.asyncio
async def test_seed_currency_commit_failure_propagates(client, monkeypatch):
    """本位币 commit 失败时异常向上抛出。"""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("DELETE FROM currencies"))
        await session.commit()

        async def boom():
            raise RuntimeError("currency commit failed")

        monkeypatch.setattr(session, "commit", boom)

        with pytest.raises(RuntimeError) as ei:
            await ensure_seed(session)
        assert "currency commit failed" in str(ei.value)


@pytest.mark.asyncio
async def test_seed_concurrent_double_write_no_duplicates(client):
    """两个并发 ensure_seed 任务同时执行，分类不翻倍。"""
    factory = get_session_factory()

    async def run_once():
        async with factory() as session:
            await ensure_seed(session)

    await asyncio.gather(run_once(), run_once())

    async with factory() as session:
        total = await session.scalar(select(func.count()).select_from(Category))
        names_kinds = (await session.execute(select(Category.name, Category.kind))).all()
        assert total == len(DEFAULT_CATEGORIES)
        assert len(set(names_kinds)) == len(DEFAULT_CATEGORIES)


@pytest.mark.asyncio
async def test_seed_signature_matches_constant(client):
    """DB 里写入的分类签名与 DEFAULT_CATEGORIES 常量一致。"""
    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(Category))).scalars().all()
        db_sig = {(c.name, c.kind, c.icon, c.color, c.sort_order) for c in rows}
        assert db_sig == _category_signature()
        assert len(db_sig) == 18


@pytest.mark.asyncio
async def test_seed_chinese_merchant_and_remark_roundtrip(client):
    """中文商户名与备注可写入并读回（存于 note 字段）。"""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO accounts (name, type, currency, opening_balance_cents, note, is_archived, created_at, updated_at) "
                "VALUES ('seedtest-cn', 'cash', 'CNY', 0, '', 0, :ts, :ts)"
            ),
            {"ts": utcnow()},
        )
        aid = (await session.execute(text("SELECT id FROM accounts WHERE name = 'seedtest-cn'"))).scalar_one()
        await session.execute(
            text(
                "INSERT INTO transactions (type, account_id, category_id, amount_cents, occurred_on, note, currency, created_at, updated_at) "
                "VALUES ('expense', :aid, NULL, 12850, '2024-05-01', :note, 'CNY', :ts, :ts)"
            ),
            {"aid": aid, "note": "楼外楼·杭州西湖店 同事聚餐 AA，AA 后我出 128.50 元", "ts": utcnow()},
        )
        await session.commit()

        row = (
            await session.execute(
                text("SELECT note, amount_cents FROM transactions WHERE note LIKE '楼外楼%'"),
            )
        ).one()
        assert "楼外楼·杭州西湖店" in row.note
        assert "同事聚餐 AA，AA 后我出 128.50 元" in row.note
        assert row.amount_cents == 12850


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_seed_extreme_amount_values_roundtrip(client):
    """极大金额可写入并读回（精度不丢）；非正金额被 CHECK 约束拒绝。"""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO accounts (name, type, currency, opening_balance_cents, note, is_archived, created_at, updated_at) "
                "VALUES ('seedtest-big', 'cash', 'CNY', 0, '', 0, :ts, :ts)"
            ),
            {"ts": utcnow()},
        )
        aid = (await session.execute(text("SELECT id FROM accounts WHERE name = 'seedtest-big'"))).scalar_one()
        await session.execute(
            text(
                "INSERT INTO transactions (type, account_id, category_id, amount_cents, occurred_on, note, currency, created_at, updated_at) "
                "VALUES ('income', :aid, NULL, 999999999999, '2024-05-01', '极大金额', 'CNY', :ts, :ts)"
            ),
            {"aid": aid, "ts": utcnow()},
        )
        await session.commit()

        big = (
            await session.execute(text("SELECT amount_cents FROM transactions WHERE note = '极大金额'"))
        ).scalar_one()
        assert big == 999999999999

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO transactions (type, account_id, category_id, amount_cents, occurred_on, note, currency, created_at, updated_at) "
                    "VALUES ('expense', :aid, NULL, -1, '2024-05-01', '负金额', 'CNY', :ts, :ts)"
                ),
                {"aid": aid, "ts": utcnow()},
            )
            await session.flush()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_seed_long_chinese_merchant_name(client):
    """超长中文商户名可完整写入并读回（存于 note 字段）。"""
    factory = get_session_factory()
    long_name = "北京" * 40 + "烤鸭店"
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO accounts (name, type, currency, opening_balance_cents, note, is_archived, created_at, updated_at) "
                "VALUES ('seedtest-long', 'cash', 'CNY', 0, '', 0, :ts, :ts)"
            ),
            {"ts": utcnow()},
        )
        aid = (await session.execute(text("SELECT id FROM accounts WHERE name = 'seedtest-long'"))).scalar_one()
        await session.execute(
            text(
                "INSERT INTO transactions (type, account_id, category_id, amount_cents, occurred_on, note, currency, created_at, updated_at) "
                "VALUES ('expense', :aid, NULL, 6600, '2024-05-01', :note, 'CNY', :ts, :ts)"
            ),
            {"aid": aid, "note": long_name + " 超长商户名测试", "ts": utcnow()},
        )
        await session.commit()

        got = (
            await session.execute(text("SELECT note FROM transactions WHERE note LIKE '%超长商户名测试'"))
        ).scalar_one()
        assert long_name in got
        assert len(long_name) == 83
