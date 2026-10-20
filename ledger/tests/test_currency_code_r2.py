from __future__ import annotations


async def _make_account(client, name, type_="cash", opening=0, currency="CNY"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening, "currency": currency},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    for c in resp.json():
        if c.get("name") == name and c.get("kind") == kind:
            return c["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


async def _make_tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_transaction_currency_lowercase_normalized(client):
    account_id = await _make_account(client, "现金", currency="CNY")
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": cat,
            "amount_cents": 1234,
            "occurred_on": "2026-01-15",
            "note": "小写币种",
            "currency": "cny",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["currency"] == "CNY"


async def test_transaction_currency_invalid_charset(client):
    account_id = await _make_account(client, "现金", currency="CNY")
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": cat,
            "amount_cents": 100,
            "occurred_on": "2026-01-15",
            "note": "非法币种",
            "currency": "XX1",
        },
    )
    assert resp.status_code == 422


async def test_transaction_currency_too_long(client):
    account_id = await _make_account(client, "现金", currency="CNY")
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": cat,
            "amount_cents": 100,
            "occurred_on": "2026-01-15",
            "note": "超长币种",
            "currency": "usdollar",
        },
    )
    assert resp.status_code == 422


async def test_account_currency_lowercase_normalized(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "美元账户", "type": "cash", "opening_balance_cents": 0, "currency": "usd"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["currency"] == "USD"


async def test_account_currency_chinese_rejected(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "人民币账户", "type": "cash", "opening_balance_cents": 0, "currency": "人民币"},
    )
    assert resp.status_code == 422
