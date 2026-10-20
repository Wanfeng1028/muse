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


async def test_expense_amount_zero_rejected(client):
    account_id = await _make_account(client, "零额账户")
    category_id = await _cat_id(client, "餐饮", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "to_account_id": None,
            "category_id": category_id,
            "amount_cents": 0,
            "occurred_on": "2026-01-15",
            "note": "零金额",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 422


async def test_expense_amount_negative_rejected(client):
    account_id = await _make_account(client, "负额账户")
    category_id = await _cat_id(client, "交通", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "to_account_id": None,
            "category_id": category_id,
            "amount_cents": -100,
            "occurred_on": "2026-01-15",
            "note": "负金额",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 422


async def test_expense_amount_positive_accepted(client):
    account_id = await _make_account(client, "正额账户")
    category_id = await _cat_id(client, "购物", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "to_account_id": None,
            "category_id": category_id,
            "amount_cents": 1,
            "occurred_on": "2026-01-15",
            "note": "最小正金额",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["amount_cents"] == 1


async def test_transfer_amount_zero_rejected(client):
    from_id = await _make_account(client, "转出账户")
    to_id = await _make_account(client, "转入账户")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": from_id,
            "to_account_id": to_id,
            "category_id": None,
            "amount_cents": 0,
            "occurred_on": "2026-01-15",
            "note": "零额转账",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 422
