from __future__ import annotations

import pytest


async def _get_expense_category_id(client, name: str) -> int:
    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"expense category {name!r} not found")


async def _get_income_category_id(client, name: str) -> int:
    resp = await client.get("/api/categories", params={"kind": "income"})
    assert resp.status_code == 200
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"income category {name!r} not found")


@pytest.mark.asyncio
async def test_currencies_list_sorted_by_code_deep2(client):
    resp = await client.get("/api/currencies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    codes = [item["code"] for item in data]
    assert codes == sorted(codes)
    for item in data:
        assert set(item.keys()) == {"code", "rate_to_base", "updated_at"}


@pytest.mark.asyncio
async def test_put_currency_create_usd_then_update_deep2(client):
    first = await client.put("/api/currencies/USD", json={"rate_to_base": 7.1})
    assert first.status_code == 200
    body = first.json()
    assert body["code"] == "USD"
    assert body["rate_to_base"] == 7.1
    assert "updated_at" in body

    listing = await client.get("/api/currencies")
    assert listing.status_code == 200
    codes = [item["code"] for item in listing.json()]
    assert "USD" in codes

    second = await client.put("/api/currencies/USD", json={"rate_to_base": 7.25})
    assert second.status_code == 200
    body2 = second.json()
    assert body2["code"] == "USD"
    assert body2["rate_to_base"] == 7.25

    listing2 = await client.get("/api/currencies")
    usd_entries = [i for i in listing2.json() if i["code"] == "USD"]
    assert len(usd_entries) == 1
    assert usd_entries[0]["rate_to_base"] == 7.25


@pytest.mark.asyncio
async def test_put_base_currency_rejected_deep2(client):
    resp = await client.put("/api/currencies/CNY", json={"rate_to_base": 1.0})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_put_invalid_currency_code_rejected_deep2(client):
    resp_numeric = await client.put("/api/currencies/12", json={"rate_to_base": 1.0})
    assert resp_numeric.status_code == 400

    resp_empty = await client.put("/api/currencies/%20", json={"rate_to_base": 1.0})
    assert resp_empty.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_returns_201_deep2(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    resp = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-03", "amount_cents": 150000},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["category_id"] == category_id
    assert body["year_month"] == "2031-03"
    assert body["amount_cents"] == 150000

    listing = await client.get("/api/budgets", params={"month": "2031-03"})
    assert listing.status_code == 200
    ids = [b["id"] for b in listing.json()]
    assert body["id"] in ids


@pytest.mark.asyncio
async def test_create_budget_duplicate_conflict_deep2(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    first = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-04", "amount_cents": 100000},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-04", "amount_cents": 200000},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_budget_income_category_rejected_deep2(client):
    category_id = await _get_income_category_id(client, "工资")
    resp = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-05", "amount_cents": 50000},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_budget_missing_category_404_deep2(client):
    resp = await client.post(
        "/api/budgets",
        json={"category_id": 99999999, "year_month": "2031-06", "amount_cents": 10000},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_budget_amount_takes_effect_deep2(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    created = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-07", "amount_cents": 300000},
    )
    assert created.status_code == 201
    budget_id = created.json()["id"]

    updated = await client.put(
        f"/api/budgets/{budget_id}",
        json={"amount_cents": 450000},
    )
    assert updated.status_code == 200
    assert updated.json()["amount_cents"] == 450000

    listing = await client.get("/api/budgets", params={"month": "2031-07"})
    assert listing.status_code == 200
    matched = [b for b in listing.json() if b["id"] == budget_id]
    assert len(matched) == 1
    assert matched[0]["amount_cents"] == 450000


@pytest.mark.asyncio
async def test_delete_budget_removes_from_list_deep2(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    created = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-08", "amount_cents": 70000},
    )
    assert created.status_code == 201
    budget_id = created.json()["id"]

    deleted = await client.delete(f"/api/budgets/{budget_id}")
    assert deleted.status_code == 204

    listing = await client.get("/api/budgets", params={"month": "2031-08"})
    assert listing.status_code == 200
    ids = [b["id"] for b in listing.json()]
    assert budget_id not in ids


@pytest.mark.asyncio
async def test_delete_missing_budget_404_deep2(client):
    resp = await client.delete("/api/budgets/99999999")
    assert resp.status_code == 404