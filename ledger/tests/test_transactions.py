from datetime import date, timedelta

import pytest


async def _create_account(client, name, opening=0):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": opening},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _get_category_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


@pytest.mark.asyncio
async def test_income_expense(client):
    account_id = await _create_account(client, "A")
    income_id = await _get_category_id(client, "工资", "income")
    expense_id = await _get_category_id(client, "餐饮", "expense")
    today = date.today().isoformat()

    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": income_id,
            "type": "income",
            "amount_cents": 500000,
            "occurred_on": today,
            "note": "工资到账",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": expense_id,
            "type": "expense",
            "amount_cents": 12050,
            "occurred_on": today,
            "note": "午餐",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/transactions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2

    resp = await client.get("/api/transactions", params={"q": "午餐"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_transfer(client):
    account_a = await _create_account(client, "A", opening=10000)
    account_b = await _create_account(client, "B", opening=0)
    today = date.today().isoformat()

    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": account_a,
            "to_account_id": account_b,
            "amount_cents": 3000,
            "occurred_on": today,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/accounts")
    assert resp.status_code == 200, resp.text
    balances = {item["id"]: item["balance_cents"] for item in resp.json()}
    assert balances[account_a] == 7000
    assert balances[account_b] == 3000

    expense_id = await _get_category_id(client, "餐饮", "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": account_a,
            "to_account_id": account_b,
            "amount_cents": 1000,
            "occurred_on": today,
            "category_id": expense_id,
        },
    )
    assert resp.status_code == 400, resp.text

    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": account_a,
            "to_account_id": account_a,
            "amount_cents": 1000,
            "occurred_on": today,
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_category_kind_mismatch(client):
    account_id = await _create_account(client, "A")
    income_id = await _get_category_id(client, "工资", "income")
    today = date.today().isoformat()

    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": income_id,
            "type": "expense",
            "amount_cents": 1000,
            "occurred_on": today,
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_filters(client):
    account_id = await _create_account(client, "A")
    income_id = await _get_category_id(client, "工资", "income")
    expense_id = await _get_category_id(client, "餐饮", "expense")

    today = date.today()
    d1 = (today - timedelta(days=2)).isoformat()
    d2 = (today - timedelta(days=1)).isoformat()
    d3 = today.isoformat()

    for payload in [
        {
            "account_id": account_id,
            "category_id": income_id,
            "type": "income",
            "amount_cents": 100000,
            "occurred_on": d1,
            "note": "r1",
        },
        {
            "account_id": account_id,
            "category_id": expense_id,
            "type": "expense",
            "amount_cents": 5000,
            "occurred_on": d2,
            "note": "r2",
        },
        {
            "account_id": account_id,
            "category_id": expense_id,
            "type": "expense",
            "amount_cents": 7000,
            "occurred_on": d3,
            "note": "r3",
        },
    ]:
        resp = await client.post("/api/transactions", json=payload)
        assert resp.status_code == 201, resp.text

    resp = await client.get("/api/transactions", params={"type": "expense"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert all(item["type"] == "expense" for item in body["items"])

    resp = await client.get("/api/transactions", params={"date_from": d2, "date_to": d3})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2

    resp = await client.get("/api/transactions", params={"date_from": d1, "date_to": d1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1

    resp_page1 = await client.get("/api/transactions", params={"limit": 2, "offset": 0})
    assert resp_page1.status_code == 200, resp_page1.text
    page1 = resp_page1.json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2

    resp_page2 = await client.get("/api/transactions", params={"limit": 2, "offset": 2})
    assert resp_page2.status_code == 200, resp_page2.text
    page2 = resp_page2.json()
    assert page2["total"] == 3
    assert len(page2["items"]) == 1


@pytest.mark.asyncio
async def test_update_delete(client):
    account_id = await _create_account(client, "A")
    expense_id = await _get_category_id(client, "餐饮", "expense")
    today = date.today().isoformat()

    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": expense_id,
            "type": "expense",
            "amount_cents": 1000,
            "occurred_on": today,
            "note": "before",
        },
    )
    assert resp.status_code == 201, resp.text
    tx_id = resp.json()["id"]

    resp = await client.put(
        f"/api/transactions/{tx_id}",
        json={"note": "after", "amount_cents": 2500},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["note"] == "after"
    assert updated["amount_cents"] == 2500

    resp = await client.put(
        f"/api/transactions/{tx_id}",
        json={"type": "income"},
    )
    assert resp.status_code == 422, resp.text  # type 不可改，传了会被 schema 拒绝

    resp = await client.delete(f"/api/transactions/{tx_id}")
    assert resp.status_code in (200, 204), resp.text

    resp = await client.get(f"/api/transactions/{tx_id}")
    assert resp.status_code == 404, resp.text
