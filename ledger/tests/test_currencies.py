"""多币种与汇率测试：迁移、配置、工具函数、汇率 API、统计折算。"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ledger import models
from ledger.config import get_settings
from ledger.currency import to_base_cents, validate_currency_code
from ledger.migrations import CURRENT_VERSION, run_migrations


async def _create_account(client, name, opening, currency=None):
    payload = {"name": name, "type": "cash", "opening_balance_cents": opening}
    if currency is not None:
        payload["currency"] = currency
    resp = await client.post("/api/accounts", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(f"category {name} ({kind}) not found")


async def _tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _make_engine(tmp_path, name: str = "test.db"):
    db_file = tmp_path / name
    return create_async_engine(f"sqlite+aiosqlite:///{db_file}")


async def _list_tables(engine) -> set:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in result.fetchall()}


async def _get_user_version(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA user_version"))
        return int(result.scalar_one())


async def _column_names(engine, table: str) -> set:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result.fetchall()}


async def test_migration_v2_to_v3(tmp_path):
    engine = _make_engine(tmp_path, "old_v2.db")
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        # 用 ORM 插入（Python 端 default 生效），再 DROP currency 列模拟 v2 老库
        await conn.execute(
            text(
                "INSERT INTO accounts (name, type, currency, opening_balance_cents, note,"
                " is_archived, created_at, updated_at) VALUES"
                " ('老账', 'cash', 'CNY', 0, '', 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
            )
        )
        await conn.execute(text("DROP TABLE currencies"))
        await conn.execute(text("ALTER TABLE transactions DROP COLUMN currency"))
        await conn.execute(text("PRAGMA user_version = 2"))

    version = await run_migrations(engine)
    assert version == 4
    assert await _get_user_version(engine) == 4
    tables = await _list_tables(engine)
    assert "currencies" in tables
    assert "merchant_aliases" in tables
    assert "currency" in await _column_names(engine, "transactions")
    # 老数据行 currency 回填默认 CNY
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT currency FROM accounts WHERE name='老账'"))
        assert result.scalar_one() == "CNY"
    await engine.dispose()


async def test_fresh_db_has_v4(tmp_path):
    engine = _make_engine(tmp_path, "fresh.db")
    version = await run_migrations(engine)
    assert version == 4
    assert version == CURRENT_VERSION
    tables = await _list_tables(engine)
    assert "currencies" in tables
    assert "merchant_aliases" in tables
    assert "currency" in await _column_names(engine, "transactions")

    version_again = await run_migrations(engine)
    assert version_again == 4
    await engine.dispose()


async def test_migration_idempotent_on_v4(tmp_path):
    engine = _make_engine(tmp_path, "idem.db")
    assert await run_migrations(engine) == 4
    assert await run_migrations(engine) == 4
    await engine.dispose()


def test_base_currency_invalid_failfast(monkeypatch):
    monkeypatch.setenv("LEDGER_BASE_CURRENCY", "XX")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_base_currency_normalized(monkeypatch):
    monkeypatch.setenv("LEDGER_BASE_CURRENCY", "usd")
    get_settings.cache_clear()
    try:
        assert get_settings().base_currency == "USD"
    finally:
        get_settings.cache_clear()


def test_validate_currency_code():
    assert validate_currency_code("usd") == "USD"
    assert validate_currency_code("CNY") == "CNY"
    for bad in ("US", "USDD", "123", ""):
        with pytest.raises(ValueError):
            validate_currency_code(bad)


def test_to_base_cents():
    assert to_base_cents(10000, 7.2) == 72000
    assert to_base_cents(1, 0.055) == 0
    assert to_base_cents(199, 0.5) == 100


async def test_list_currencies_has_base(client):
    resp = await client.get("/api/currencies")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    codes = {item["code"]: item for item in items}
    assert "CNY" in codes
    assert codes["CNY"]["rate_to_base"] == 1.0


async def test_upsert_create_currency(client):
    resp = await client.put("/api/currencies/USD", json={"rate_to_base": 7.2})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == "USD"
    assert body["rate_to_base"] == 7.2

    listing = await client.get("/api/currencies")
    assert listing.status_code == 200, listing.text
    codes = {item["code"] for item in listing.json()}
    assert "USD" in codes


async def test_upsert_update_currency(client):
    first = await client.put("/api/currencies/USD", json={"rate_to_base": 7.2})
    assert first.status_code == 200, first.text
    second = await client.put("/api/currencies/USD", json={"rate_to_base": 7.3})
    assert second.status_code == 200, second.text

    listing = await client.get("/api/currencies")
    assert listing.status_code == 200, listing.text
    codes = {item["code"]: item for item in listing.json()}
    assert codes["USD"]["rate_to_base"] == 7.3


async def test_upsert_bad_code(client):
    resp = await client.put("/api/currencies/US", json={"rate_to_base": 7})
    assert resp.status_code == 400, resp.text


async def test_upsert_bad_rate(client):
    zero = await client.put("/api/currencies/USD", json={"rate_to_base": 0})
    assert zero.status_code == 422, zero.text
    neg = await client.put("/api/currencies/USD", json={"rate_to_base": -1})
    assert neg.status_code == 422, neg.text


async def test_upsert_base_currency_rejected(client):
    resp = await client.put("/api/currencies/CNY", json={"rate_to_base": 2.0})
    assert resp.status_code == 400, resp.text


async def test_create_account_bad_currency(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "坏币种", "type": "cash", "currency": "XX"},
    )
    assert resp.status_code == 422, resp.text


async def test_create_account_with_currency(client):
    resp = await client.post(
        "/api/accounts",
        json={
            "name": "美元户",
            "type": "savings",
            "currency": "USD",
            "opening_balance_cents": 0,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["currency"] == "USD"


async def test_create_txn_default_currency(client):
    account = await _create_account(client, "现金", 0)
    cat = await _cat_id(client, "工资", "income")
    txn = await _tx(
        client,
        type="income",
        account_id=account["id"],
        category_id=cat,
        amount_cents=1000,
        occurred_on=date.today().isoformat(),
        note="默认币种",
    )
    assert txn["currency"] == "CNY"


async def test_create_txn_with_currency(client):
    account = await _create_account(client, "现金", 0)
    cat = await _cat_id(client, "工资", "income")
    txn = await _tx(
        client,
        type="income",
        account_id=account["id"],
        category_id=cat,
        amount_cents=1000,
        occurred_on=date.today().isoformat(),
        currency="USD",
    )
    assert txn["currency"] == "USD"

    fetched = await client.get(f"/api/transactions/{txn['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["currency"] == "USD"


async def test_create_txn_bad_currency(client):
    account = await _create_account(client, "现金", 0)
    cat = await _cat_id(client, "工资", "income")
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account["id"],
            "category_id": cat,
            "amount_cents": 1000,
            "occurred_on": date.today().isoformat(),
            "currency": "USDD",
        },
    )
    assert resp.status_code == 422, resp.text


async def test_summary_converts_foreign(client):
    account = await _create_account(client, "美元户", 0, currency="USD")
    cat = await _cat_id(client, "工资", "income")
    await _tx(
        client,
        type="income",
        account_id=account["id"],
        category_id=cat,
        amount_cents=10000,
        occurred_on=date.today().isoformat(),
        currency="USD",
    )
    rate = await client.put("/api/currencies/USD", json={"rate_to_base": 7.2})
    assert rate.status_code == 200, rate.text

    month = date.today().strftime("%Y-%m")
    resp = await client.get("/api/stats/summary", params={"month": month})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["income_cents"] == 72000
    assert body["unknown_count"] == 0


async def test_summary_unknown_currency(client):
    account = await _create_account(client, "现金", 0, currency="CNY")
    cat = await _cat_id(client, "工资", "income")
    await _tx(
        client,
        type="income",
        account_id=account["id"],
        category_id=cat,
        amount_cents=5000,
        occurred_on=date.today().isoformat(),
        currency="EUR",
    )

    month = date.today().strftime("%Y-%m")
    first = await client.get("/api/stats/summary", params={"month": month})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["unknown_count"] == 1
    assert first_body["income_cents"] == 0

    rate = await client.put("/api/currencies/EUR", json={"rate_to_base": 7.8})
    assert rate.status_code == 200, rate.text

    second = await client.get("/api/stats/summary", params={"month": month})
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["unknown_count"] == 0
    assert second_body["income_cents"] == 39000


async def test_net_worth_multi_currency(client):
    await _create_account(client, "人民币户", 10000, currency="CNY")
    await _create_account(client, "美元户", 10000, currency="USD")
    rate = await client.put("/api/currencies/USD", json={"rate_to_base": 7.2})
    assert rate.status_code == 200, rate.text

    resp = await client.get("/api/stats/net-worth")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_cents"] == 10000 + 72000


async def test_update_txn_currency(client):
    account = await _create_account(client, "现金", 0)
    cat = await _cat_id(client, "工资", "income")
    txn = await _tx(
        client,
        type="income",
        account_id=account["id"],
        category_id=cat,
        amount_cents=1000,
        occurred_on=date.today().isoformat(),
    )
    assert txn["currency"] == "CNY"

    resp = await client.put(
        f"/api/transactions/{txn['id']}",
        json={"currency": "USD"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["currency"] == "USD"
