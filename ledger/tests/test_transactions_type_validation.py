from __future__ import annotations

import pytest


async def _make_account(client, name: str, type_: str = "cash", opening: int = 0) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_category_id(client, kind: str) -> int:
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    cats = resp.json()
    assert isinstance(cats, list) and len(cats) > 0
    for c in cats:
        if c.get("kind") == kind:
            return c["id"]
    raise AssertionError(f"no category of kind {kind}")


async def _make_tx(client, **kwargs) -> int:
    resp = await client.post("/api/transactions", json=kwargs)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_list_type_bogus_returns_400(client):
    acc = await _make_account(client, "tv")
    cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=cat,
        amount_cents=100,
        occurred_on="2024-01-01",
        note="x",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"type": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "type 参数非法"


@pytest.mark.asyncio
async def test_list_type_empty_means_no_filter(client):
    acc = await _make_account(client, "tv")
    cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=cat,
        amount_cents=100,
        occurred_on="2024-01-01",
        note="x",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"type": ""})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_type_expense_filters(client):
    acc = await _make_account(client, "tv")
    cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=cat,
        amount_cents=100,
        occurred_on="2024-01-01",
        note="x",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"type": "expense"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert all(item["type"] == "expense" for item in resp.json()["items"])


@pytest.mark.asyncio
async def test_list_type_valid_values_return_200(client):
    acc = await _make_account(client, "tv")
    cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=cat,
        amount_cents=100,
        occurred_on="2024-01-01",
        note="x",
        currency="CNY",
    )
    for t in ["income", "transfer"]:
        resp = await client.get("/api/transactions", params={"type": t})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_type_missing_means_no_filter(client):
    acc = await _make_account(client, "tv")
    cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=cat,
        amount_cents=100,
        occurred_on="2024-01-01",
        note="x",
        currency="CNY",
    )
    resp = await client.get("/api/transactions")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
