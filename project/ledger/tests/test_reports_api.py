"""月度收支报告接口测试。

全部用例通过真实 HTTP 调用 API，并使用数据库会话插入交易数据，不做 mock。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from ledger.database import get_session_factory
from ledger.models import Account, Category, Transaction, utcnow
from ledger.seed import ensure_seed


@pytest_asyncio.fixture(scope="function")
async def session(app):
    """函数级：清空业务表并重播种，返回一个新的 AsyncSession。"""
    from sqlalchemy import text

    factory = get_session_factory()
    async with factory() as s:
        for t in (
            "ocr_reviews",
            "statement_items",
            "statement_batches",
            "match_rules",
            "merchant_aliases",
            "statement_templates",
            "report_schemes",
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


async def _seed_categories(session) -> dict[str, int]:
    """取已有分类（种子数据里有），返回 分类名 -> id 映射。"""
    from sqlalchemy import select

    specs = [
        ("餐饮", "expense"),
        ("教育", "expense"),
        ("交通", "expense"),
        ("数码", "expense"),
        ("住房", "expense"),
        ("日用", "expense"),
        ("其他", "expense"),
        ("工资", "income"),
    ]
    result: dict[str, int] = {}
    for name, kind in specs:
        row = (
            await session.execute(
                select(Category).where(Category.name == name, Category.kind == kind)
            )
        ).scalar_one_or_none()
        if row is None:
            row = Category(name=name, kind=kind)
            session.add(row)
            await session.flush()
        result[name] = row.id
    await session.commit()
    return result


async def _ensure_account(session) -> int:
    """确保 accounts 表至少有一行，返回其 id。"""
    row = (await session.execute(select(Account).limit(1))).scalar_one_or_none()
    if row is not None:
        return row.id
    now = utcnow()
    account = Account(name="现金", type="cash", currency="CNY", created_at=now, updated_at=now)
    session.add(account)
    await session.flush()
    return account.id


def _make_txn(
    txn_type: str,
    amount_cents: int,
    occurred_on: str,
    account_id: int,
    category_id: int | None = None,
    note: str | None = None,
) -> Transaction:
    """构造一笔交易行。"""
    now = utcnow()
    return Transaction(
        type=txn_type,
        account_id=account_id,
        to_account_id=None,
        category_id=category_id,
        amount_cents=amount_cents,
        occurred_on=occurred_on,
        note=note,
        currency="CNY",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_default_scheme_auto_created(client: AsyncClient) -> None:
    """首次读取口径时应自动写入默认的 9月口径。"""
    resp = await client.get("/api/reports/category-scheme")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schemes"], "默认口径应被自动创建"
    names = [s["name"] for s in data["schemes"]]
    assert "9月口径" in names
    assert data["active"] == "9月口径"


@pytest.mark.asyncio
async def test_put_invalid_category_returns_400(client: AsyncClient, session) -> None:
    """写入不存在的分类名应返回 400 并列出非法名。"""
    await _seed_categories(session)
    payload = {
        "name": "测试口径",
        "mapping": {"吃喝": ["餐饮"], "乱写": ["不存在的分类"]},
    }
    resp = await client.put("/api/reports/category-scheme", json=payload)
    assert resp.status_code == 400
    assert "不存在的分类" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_put_valid_scheme_and_read_back(client: AsyncClient, session) -> None:
    """写入合法口径后应能读回。"""
    await _seed_categories(session)
    payload = {
        "name": "自定义口径",
        "mapping": {"吃喝": ["餐饮"], "出行": ["交通"]},
    }
    resp = await client.put("/api/reports/category-scheme", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "name": "自定义口径"}

    resp = await client.get("/api/reports/category-scheme")
    assert resp.status_code == 200
    data = resp.json()
    names = [s["name"] for s in data["schemes"]]
    assert "自定义口径" in names


@pytest.mark.asyncio
async def test_monthly_report_basic(client: AsyncClient, session) -> None:
    """月报核心指标、桶、环比、商户榜断言。"""
    cats = await _seed_categories(session)
    account_id = await _ensure_account(session)

    # 2026-09 三笔支出 + 一笔收入
    session.add(_make_txn("expense", 10000, "2026-09-05", account_id, cats["餐饮"], "食堂 午饭"))
    session.add(_make_txn("expense", 140000, "2026-09-06", account_id, cats["教育"], "网课 报名"))
    session.add(_make_txn("expense", 5000, "2026-09-07", account_id, cats["交通"], "地铁 通勤"))
    session.add(_make_txn("income", 500000, "2026-09-10", account_id, cats["工资"], "公司 九月工资"))
    # 2026-08 一笔餐饮
    session.add(_make_txn("expense", 20000, "2026-08-15", account_id, cats["餐饮"], "食堂 晚饭"))
    await session.commit()

    resp = await client.get(
        "/api/reports/monthly",
        params={"year_month": "2026-09", "scheme": "9月口径"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["income_cents"] == 500000
    assert data["expense_cents"] == 155000
    assert data["net_cents"] == 345000

    buckets = {b["bucket"]: b["amount_cents"] for b in data["buckets"]}
    assert buckets["考研投入"] == 140000
    assert buckets["饮食"] == 10000
    assert buckets["交通"] == 5000

    mom = {m["name"]: m for m in data["mom"]}
    assert mom["餐饮"]["this_cents"] == 10000
    assert mom["餐饮"]["last_cents"] == 20000
    assert mom["餐饮"]["delta_cents"] == -10000
    assert mom["餐饮"]["delta_pct"] == -50.0

    merchants = {m["merchant"]: m for m in data["top_merchants"]}
    assert merchants["食堂"]["amount_cents"] == 10000
    assert merchants["食堂"]["count"] == 1
    assert merchants["网课"]["amount_cents"] == 140000
    assert merchants["地铁"]["amount_cents"] == 5000
    # 收入不计入商户榜
    assert "公司" not in merchants


@pytest.mark.asyncio
async def test_monthly_report_cross_year_mom(client: AsyncClient, session) -> None:
    """跨年环比：2026-01 的上月应取 2025-12。"""
    cats = await _seed_categories(session)
    account_id = await _ensure_account(session)
    session.add(_make_txn("expense", 30000, "2025-12-20", account_id, cats["餐饮"], "食堂 年末"))
    session.add(_make_txn("expense", 10000, "2026-01-05", account_id, cats["餐饮"], "食堂 年初"))
    await session.commit()

    resp = await client.get(
        "/api/reports/monthly",
        params={"year_month": "2026-01", "scheme": "9月口径"},
    )
    assert resp.status_code == 200
    data = resp.json()
    mom = {m["name"]: m for m in data["mom"]}
    assert mom["餐饮"]["this_cents"] == 10000
    assert mom["餐饮"]["last_cents"] == 30000
    assert mom["餐饮"]["delta_cents"] == -20000


@pytest.mark.asyncio
async def test_invalid_year_month_returns_422(client: AsyncClient) -> None:
    """非法月份格式应返回 422。"""
    for bad in ("2026-13", "202609"):
        resp = await client.get(
            "/api/reports/monthly",
            params={"year_month": bad},
        )
        assert resp.status_code == 422, f"{bad} 应返回 422"


@pytest.mark.asyncio
async def test_transfer_excluded(client: AsyncClient, session) -> None:
    """transfer 类型交易不计入收支。"""
    cats = await _seed_categories(session)
    account_id = await _ensure_account(session)
    session.add(_make_txn("expense", 5000, "2026-09-05", account_id, cats["餐饮"], "食堂 午饭"))
    session.add(
        _make_txn("transfer", 999999, "2026-09-06", account_id, None, "转账 内部")
    )
    await session.commit()

    resp = await client.get(
        "/api/reports/monthly",
        params={"year_month": "2026-09", "scheme": "9月口径"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["income_cents"] == 0
    assert data["expense_cents"] == 5000
    assert data["net_cents"] == -5000
    assert data["tx_count"] == 1


@pytest.mark.asyncio
async def test_scheme_not_found_returns_404(client: AsyncClient) -> None:
    """指定不存在的口径应返回 404。"""
    resp = await client.get(
        "/api/reports/monthly",
        params={"year_month": "2026-09", "scheme": "不存在的口径"},
    )
    assert resp.status_code == 404
