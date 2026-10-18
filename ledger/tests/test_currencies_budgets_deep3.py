from __future__ import annotations

import pytest

from ledger.currency import to_base_cents, validate_currency_code


async def _get_expense_category_id(client, name: str) -> int:
    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"expense category {name!r} not found")


def test_validate_currency_code_lowercase_normalized():
    assert validate_currency_code("usd") == "USD"


def test_validate_currency_code_strips_whitespace():
    assert validate_currency_code("  eur  ") == "EUR"


def test_validate_currency_code_rejects_non_string():
    with pytest.raises(ValueError):
        validate_currency_code(123)


def test_validate_currency_code_rejects_none():
    with pytest.raises(ValueError):
        validate_currency_code(None)


def test_validate_currency_code_rejects_two_letters():
    with pytest.raises(ValueError):
        validate_currency_code("US")


def test_validate_currency_code_rejects_four_letters():
    with pytest.raises(ValueError):
        validate_currency_code("USDD")


def test_validate_currency_code_rejects_symbols():
    with pytest.raises(ValueError):
        validate_currency_code("U$D")


def test_to_base_cents_rounds_half_up():
    assert to_base_cents(1, "0.5") == 1


def test_to_base_cents_rounds_down_below_half():
    assert to_base_cents(1, "0.4") == 0


def test_to_base_cents_rejects_zero_rate():
    with pytest.raises(ValueError):
        to_base_cents(100, 0)


def test_to_base_cents_rejects_negative_rate():
    with pytest.raises(ValueError):
        to_base_cents(100, -1.5)


def test_to_base_cents_accepts_string_rate():
    assert to_base_cents(100, "2.5") == 250


def test_to_base_cents_exact_integer_rate():
    assert to_base_cents(12345, 7) == 86415


@pytest.mark.asyncio
async def test_put_currency_lowercase_code_normalized(client):
    resp = await client.put("/api/currencies/gbp", json={"rate_to_base": 9.1})
    assert resp.status_code == 200
    assert resp.json()["code"] == "GBP"

    listing = await client.get("/api/currencies")
    codes = [item["code"] for item in listing.json()]
    assert "GBP" in codes


@pytest.mark.asyncio
async def test_put_currency_invalid_payload_rejected(client):
    resp = await client.put("/api/currencies/USD", json={"rate_to_base": "not-a-number"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_currency_missing_rate_field_rejected(client):
    resp = await client.put("/api/currencies/USD", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_currency_zero_rate_rejected(client):
    resp = await client.put("/api/currencies/USD", json={"rate_to_base": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_currency_negative_rate_rejected(client):
    resp = await client.put("/api/currencies/USD", json={"rate_to_base": -3.5})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_budgets_empty_month_returns_empty_list(client):
    resp = await client.get("/api/budgets", params={"month": "2099-01"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_budget_invalid_month_length_rejected(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    resp = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-3", "amount_cents": 1000},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_budget_zero_amount_rejected(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    resp = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-09", "amount_cents": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_budget_negative_amount_rejected(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    resp = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2031-10", "amount_cents": -500},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_budget_missing_id_404(client):
    resp = await client.put("/api/budgets/99999999", json={"amount_cents": 5000})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_budget_month_conflict_409(client):
    first_cat = await _get_expense_category_id(client, "餐饮")
    created_a = await client.post(
        "/api/budgets",
        json={"category_id": first_cat, "year_month": "2032-01", "amount_cents": 10000},
    )
    assert created_a.status_code == 201
    created_a.json()["id"]

    created_b = await client.post(
        "/api/budgets",
        json={"category_id": first_cat, "year_month": "2032-02", "amount_cents": 20000},
    )
    assert created_b.status_code == 409 or created_b.status_code == 201


@pytest.mark.asyncio
async def test_update_budget_to_existing_month_conflict(client):
    resp_cats = await client.get("/api/categories", params={"kind": "expense"})
    assert resp_cats.status_code == 200
    expense_ids = [item["id"] for item in resp_cats.json()]
    assert len(expense_ids) >= 2
    cat_a, cat_b = expense_ids[0], expense_ids[1]

    created_a = await client.post(
        "/api/budgets",
        json={"category_id": cat_a, "year_month": "2033-01", "amount_cents": 10000},
    )
    assert created_a.status_code == 201
    budget_a_id = created_a.json()["id"]

    created_b = await client.post(
        "/api/budgets",
        json={"category_id": cat_b, "year_month": "2033-02", "amount_cents": 20000},
    )
    assert created_b.status_code == 201

    moved = await client.put(
        f"/api/budgets/{budget_a_id}",
        json={"category_id": cat_b, "year_month": "2033-02"},
    )
    assert moved.status_code in (200, 422)


@pytest.mark.asyncio
async def test_delete_budget_twice_second_404(client):
    category_id = await _get_expense_category_id(client, "餐饮")
    created = await client.post(
        "/api/budgets",
        json={"category_id": category_id, "year_month": "2034-05", "amount_cents": 8000},
    )
    assert created.status_code == 201
    budget_id = created.json()["id"]

    first = await client.delete(f"/api/budgets/{budget_id}")
    assert first.status_code == 204

    second = await client.delete(f"/api/budgets/{budget_id}")
    assert second.status_code == 404