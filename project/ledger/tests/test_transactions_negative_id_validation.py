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
async def test_list_account_id_negative_returns_400(client):
    acc = await _make_account(client, "neg-account-id-check")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)

    resp = await client.get("/api/transactions", params={"account_id": -1})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "account_id 参数非法"


@pytest.mark.asyncio
async def test_list_category_id_negative_returns_400(client):
    acc = await _make_account(client, "neg-category-id-check")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)

    resp = await client.get("/api/transactions", params={"category_id": -5})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "category_id 参数非法"


@pytest.mark.asyncio
async def test_list_both_ids_negative_returns_400(client):
    acc = await _make_account(client, "neg-both-ids-check")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)

    resp = await client.get(
        "/api/transactions",
        params={"account_id": -1, "category_id": -2},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_account_id_zero_still_returns_200(client):
    acc = await _make_account(client, "zero-account-id-check")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)

    resp = await client.get("/api/transactions", params={"account_id": 0})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_valid_account_filter_returns_200(client):
    acc = await _make_account(client, "valid-account-id-check")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)

    resp = await client.get("/api/transactions", params={"account_id": acc})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
