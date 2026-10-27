from __future__ import annotations

import pytest


async def _make_account(client, name: str) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_category_id(client, kind: str) -> int:
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    data = resp.json()
    for entry in data:
        if entry.get("kind") == kind:
            return entry["id"]
    raise AssertionError(f"no category found with kind={kind}")


async def _make_tx(client, **kwargs) -> dict:
    payload = {
        "type": "expense",
        "account_id": None,
        "to_account_id": None,
        "category_id": None,
        "amount_cents": 100,
        "occurred_on": "2024-01-01",
        "note": "x",
        "currency": "CNY",
    }
    payload.update(kwargs)
    resp = await client.post("/api/transactions", json=payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_list_date_inverted_returns_400(client):
    acc = await _make_account(client, "acc-inverted")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-02-01", "date_to": "2024-01-01"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 不能晚于 date_to"


@pytest.mark.asyncio
async def test_list_date_equal_returns_200(client):
    acc = await _make_account(client, "acc-equal")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-01-01", "date_to": "2024-01-01"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_date_normal_range_returns_200(client):
    acc = await _make_account(client, "acc-normal-range")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-01-01", "date_to": "2024-01-31"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_date_only_from_returns_200(client):
    acc = await _make_account(client, "acc-only-from")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-01-01"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_date_only_to_returns_200(client):
    acc = await _make_account(client, "acc-only-to")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_to": "2024-01-31"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_date_empty_from_with_to_returns_200(client):
    acc = await _make_account(client, "acc-empty-from")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "", "date_to": "2024-01-31"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_date_bogus_from_precedes_order_check(client):
    acc = await _make_account(client, "acc-bogus-from-order")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "bogus", "date_to": "2024-01-01"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 参数非法"
