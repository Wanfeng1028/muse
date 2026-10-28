from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "bad_value",
    [
        "not-a-date",
        "2024-13-01",
        "2024-01-32",
        "",
        "2024/01/05",
        "20240105",
        "2024-1-5",
        "2023-02-29",
    ],
)
async def test_update_occurred_on_invalid_returns_400_and_keeps_original(client, bad_value):
    name = f"acct-{uuid4().hex[:8]}"
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    acc = resp.json()["id"]

    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    cat = next(c["id"] for c in resp.json() if c.get("kind") == "expense")

    payload = {
        "type": "expense",
        "account_id": acc,
        "to_account_id": None,
        "category_id": cat,
        "amount_cents": 100,
        "occurred_on": "2024-01-05",
        "note": "x",
        "currency": "CNY",
    }
    resp = await client.post("/api/transactions", json=payload)
    assert resp.status_code == 201
    txn = resp.json()["id"]

    resp = await client.put(f"/api/transactions/{txn}", json={"occurred_on": bad_value})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "occurred_on 参数非法"

    resp = await client.get(f"/api/transactions/{txn}")
    assert resp.status_code == 200
    assert resp.json()["occurred_on"] == "2024-01-05"


async def test_update_occurred_on_null_returns_400_and_keeps_original(client):
    name = f"acct-{uuid4().hex[:8]}"
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    acc = resp.json()["id"]

    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    cat = next(c["id"] for c in resp.json() if c.get("kind") == "expense")

    payload = {
        "type": "expense",
        "account_id": acc,
        "to_account_id": None,
        "category_id": cat,
        "amount_cents": 100,
        "occurred_on": "2024-01-05",
        "note": "x",
        "currency": "CNY",
    }
    resp = await client.post("/api/transactions", json=payload)
    assert resp.status_code == 201
    txn = resp.json()["id"]

    resp = await client.put(f"/api/transactions/{txn}", json={"occurred_on": None})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "occurred_on 参数非法"

    resp = await client.get(f"/api/transactions/{txn}")
    assert resp.status_code == 200
    assert resp.json()["occurred_on"] == "2024-01-05"


@pytest.mark.parametrize(
    "good_value",
    ["2024-02-29", "2024-03-15", "2024-12-31"],
)
async def test_update_occurred_on_valid_persists(client, good_value):
    name = f"acct-{uuid4().hex[:8]}"
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    acc = resp.json()["id"]

    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    cat = next(c["id"] for c in resp.json() if c.get("kind") == "expense")

    payload = {
        "type": "expense",
        "account_id": acc,
        "to_account_id": None,
        "category_id": cat,
        "amount_cents": 100,
        "occurred_on": "2024-01-05",
        "note": "x",
        "currency": "CNY",
    }
    resp = await client.post("/api/transactions", json=payload)
    assert resp.status_code == 201
    txn = resp.json()["id"]

    resp = await client.put(f"/api/transactions/{txn}", json={"occurred_on": good_value})
    assert resp.status_code == 200

    resp = await client.get(f"/api/transactions/{txn}")
    assert resp.status_code == 200
    assert resp.json()["occurred_on"] == good_value


async def test_update_without_occurred_on_keeps_original(client):
    name = f"acct-{uuid4().hex[:8]}"
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    acc = resp.json()["id"]

    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    cat = next(c["id"] for c in resp.json() if c.get("kind") == "expense")

    payload = {
        "type": "expense",
        "account_id": acc,
        "to_account_id": None,
        "category_id": cat,
        "amount_cents": 100,
        "occurred_on": "2024-01-05",
        "note": "x",
        "currency": "CNY",
    }
    resp = await client.post("/api/transactions", json=payload)
    assert resp.status_code == 201
    txn = resp.json()["id"]

    resp = await client.put(f"/api/transactions/{txn}", json={"note": "y"})
    assert resp.status_code == 200

    resp = await client.get(f"/api/transactions/{txn}")
    assert resp.status_code == 200
    assert resp.json()["occurred_on"] == "2024-01-05"