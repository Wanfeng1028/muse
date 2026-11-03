"""ledger.services 深度测试：边界值、失败注入、幂等、并发、中文场景。"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from ledger.models import utcnow

from ledger.services import (
    account_balance,
    by_category,
    get_rates,
    list_accounts_with_balance,
    month_range,
    monthly_summary,
    trend,
)


@pytest_asyncio.fixture(scope="function")
async def session(app):
    """函数级：清空业务表并重播种，返回一个新的 AsyncSession。"""
    from sqlalchemy import text

    from ledger.database import get_session_factory
    from ledger.seed import ensure_seed

    factory = get_session_factory()
    async with factory() as s:
        for t in (
            "ocr_reviews",
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
            await s.execute(text(f"DELETE FROM {t}"))
        await s.commit()
        await ensure_seed(s)
        await s.commit()
        yield s


# ---------------------------------------------------------------------------
# 边界值
# ---------------------------------------------------------------------------


async def test_month_range_december_boundary():
    start, end = month_range("2024-12")
    assert start == "2024-12-01"
    assert end == "2025-01-01"


async def test_month_range_normal_month():
    start, end = month_range("2024-02")
    assert start == "2024-02-01"
    assert end == "2024-03-01"


async def test_trend_zero_months_falls_back_to_twelve(session):
    rows = await trend(session, months=0)
    assert len(rows) == 12
    assert rows == sorted(rows, key=lambda r: r["month"])
    assert rows[-1]["month"] == date.today().strftime("%Y-%m")


async def test_trend_negative_months_falls_back_to_twelve(session):
    rows = await trend(session, months=-5)
    assert len(rows) == 12
    assert all(set(r.keys()) == {"month", "income_cents", "expense_cents"} for r in rows)


async def test_account_balance_not_found_raises(session):
    with pytest.raises(ValueError) as exc:
        await account_balance(session, 999999)
    assert "account not found" in str(exc.value)
    assert isinstance(exc.value, ValueError)


async def test_account_balance_empty_account_returns_opening(session):
    from ledger.models import Account

    acc = Account(
        name="空账户",
        type="cash",
        currency="CNY",
        opening_balance_cents=12345,
        is_archived=0,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    bal = await account_balance(session, acc.id)
    assert bal == 12345
    assert isinstance(bal, int)


# ---------------------------------------------------------------------------
# 中文场景
# ---------------------------------------------------------------------------


async def test_monthly_summary_chinese_merchant_and_note(session):
    from ledger.models import Account, Category, Transaction

    acc = Account(name="招商银行储蓄卡", type="bank", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    from sqlalchemy import select as _select
    _cat = (await session.execute(_select(Category).where(Category.name == "餐饮", Category.kind == "expense"))).scalar_one_or_none()
    if _cat is None:
        _cat = Category(name="餐饮", kind="expense", icon="fork", color="#f00")
        session.add(_cat)
        await session.commit()
        await session.refresh(_cat)
    cat = _cat
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    today = date.today().strftime("%Y-%m")
    tx = Transaction(
        type="expense",
        amount_cents=8888,
        currency="CNY",
        account_id=acc.id,
        category_id=cat.id,
        occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
        note="海底捞火锅 | 和同事聚餐 AA 后我付的部分",
        
    )
    session.add(tx)
    await session.commit()

    summary = await monthly_summary(session, today)
    assert summary["expense_cents"] == 8888
    assert summary["income_cents"] == 0
    assert summary["net_cents"] == -8888
    assert summary["count"] == 1


async def test_by_category_chinese_category_name(session):
    from ledger.models import Account, Category, Transaction

    acc = Account(name="现金", type="cash", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    from sqlalchemy import select as _select2
    _cat2 = (await session.execute(_select2(Category).where(Category.name == "交通出行", Category.kind == "expense"))).scalar_one_or_none()
    if _cat2 is None:
        _cat2 = Category(name="交通出行", kind="expense", icon="bus", color="#00f")
        session.add(_cat2)
        await session.commit()
        await session.refresh(_cat2)
    cat = _cat2
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    today = date.today().strftime("%Y-%m")
    session.add_all(
        [
            Transaction(
                type="expense",
                amount_cents=300,
                currency="CNY",
                account_id=acc.id,
                category_id=cat.id,
                occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
                note="北京地铁 | 上班通勤",
                
            ),
            Transaction(
                type="expense",
                amount_cents=700,
                currency="CNY",
                account_id=acc.id,
                category_id=cat.id,
                occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
                note="滴滴出行 | 打车回家",
                
            ),
        ]
    )
    await session.commit()

    rows = await by_category(session, today, kind="expense")
    match = [r for r in rows if r["category_id"] == cat.id]
    assert len(match) == 1
    assert match[0]["name"] == "交通出行"
    assert int(match[0]["total_cents"]) == 1000
    assert Decimal(str(match[0]["pct"])) == Decimal("100")


# ---------------------------------------------------------------------------
# 失败注入
# ---------------------------------------------------------------------------


async def test_get_rates_returns_decimal_for_each_currency(session):
    rates = await get_rates(session)
    assert isinstance(rates, dict)
    assert len(rates) >= 1
    assert all(isinstance(v, Decimal) for v in rates.values())
    assert "CNY" in rates


async def test_monthly_summary_unknown_currency_counted(session):
    from ledger.models import Account, Transaction

    acc = Account(name="外币户", type="bank", currency="XYZ", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    today = date.today().strftime("%Y-%m")
    session.add(
        Transaction(
            type="expense",
            amount_cents=500,
            currency="XYZ",
            account_id=acc.id,
            category_id=None,
            occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
            note="海外商户 | 没有汇率的币种",
            
        )
    )
    await session.commit()

    summary = await monthly_summary(session, today)
    assert summary["unknown_count"] == 1
    assert summary["expense_cents"] == 0
    assert summary["count"] == 1


async def test_account_balance_db_error_propagates(session):
    await session.close()
    with pytest.raises(Exception) as exc:
        await account_balance(session, 1)
    assert exc.value is not None
    assert not isinstance(exc.value, AssertionError)


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------


async def test_list_accounts_with_balance_idempotent(session):
    from ledger.models import Account

    acc = Account(name="工资卡", type="bank", currency="CNY", opening_balance_cents=100, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()

    first = await list_accounts_with_balance(session)
    second = await list_accounts_with_balance(session)
    assert [a["id"] for a in first] == [a["id"] for a in second]
    assert [a["balance_cents"] for a in first] == [a["balance_cents"] for a in second]
    assert len(first) == len(second)


async def test_monthly_summary_repeat_same_result(session):
    from ledger.models import Account, Transaction

    acc = Account(name="重复校验", type="cash", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    today = date.today().strftime("%Y-%m")
    session.add(
        Transaction(
            type="income",
            amount_cents=2000,
            currency="CNY",
            account_id=acc.id,
            category_id=None,
            occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
            note="工资 | 本月工资",
            
        )
    )
    await session.commit()

    a = await monthly_summary(session, today)
    b = await monthly_summary(session, today)
    assert a == b
    assert a["income_cents"] == 2000


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------


async def test_concurrent_account_balance_same_account(session):
    from ledger.database import get_session_factory
    from ledger.models import Account, Transaction

    factory = get_session_factory()
    async with factory() as s:
        acc = Account(name="并发账户", type="bank", currency="CNY", opening_balance_cents=1000, is_archived=0, created_at=utcnow(), updated_at=utcnow())
        s.add(acc)
        await s.commit()
        await s.refresh(acc)
        acc_id = acc.id
        s.add(
            Transaction(
                type="expense",
                amount_cents=250,
                currency="CNY",
                account_id=acc_id,
                category_id=None,
                occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
                note="并发商户 | 并发读取同一账单",
                
            )
        )
        await s.commit()

    async def read_balance():
        async with factory() as s2:
            return await account_balance(s2, acc_id)

    results = await asyncio.gather(read_balance(), read_balance(), read_balance())
    assert results == [750, 750, 750]
    assert len(set(results)) == 1


async def test_concurrent_monthly_summary_consistent(session):
    from ledger.database import get_session_factory
    from ledger.models import Account, Transaction

    factory = get_session_factory()
    today = date.today().strftime("%Y-%m")
    async with factory() as s:
        acc = Account(name="并发统计", type="cash", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
        s.add(acc)
        await s.commit()
        await s.refresh(acc)
        s.add(
            Transaction(
                type="expense",
                amount_cents=999,
                currency="CNY",
                account_id=acc.id,
                category_id=None,
                occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
                note="并发统计商户 | 同一账单被并发汇总",
                
            )
        )
        await s.commit()

    async def read_summary():
        async with factory() as s2:
            return await monthly_summary(s2, today)

    r1, r2 = await asyncio.gather(read_summary(), read_summary())
    assert r1["expense_cents"] == r2["expense_cents"]
    assert r1["count"] == r2["count"]
    assert r1["expense_cents"] == 999


# ---------------------------------------------------------------------------
# 极大金额 / 负数
# ---------------------------------------------------------------------------


async def test_account_balance_large_amount(session):
    from ledger.models import Account, Transaction

    acc = Account(name="大额账户", type="bank", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    big = 9_000_000_000_000
    session.add(
        Transaction(
            type="income",
            amount_cents=big,
            currency="CNY",
            account_id=acc.id,
            category_id=None,
            occurred_on=date.today().isoformat(),
        created_at=utcnow(),
        updated_at=utcnow(),
            note="大额入账 | 极大金额测试",
            
        )
    )
    await session.commit()

    bal = await account_balance(session, acc.id)
    assert bal == big
    assert bal > 0


async def test_account_balance_negative_amount_cents(session):
    """负数金额被 DB CHECK 约束拒绝（ck_transactions_amount_positive）。"""
    import pytest
    from sqlalchemy.exc import IntegrityError

    from ledger.models import Account, Transaction

    acc = Account(name="负数账户", type="cash", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    session.add(
        Transaction(
            type="expense",
            amount_cents=-500,
            currency="CNY",
            account_id=acc.id,
            category_id=None,
            occurred_on=date.today().isoformat(),
            created_at=utcnow(),
            updated_at=utcnow(),
            note="冲正 | 负数金额边界",
        )
    )
    with pytest.raises(IntegrityError):
        await session.commit()