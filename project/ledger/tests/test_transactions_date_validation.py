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
async def test_list_date_from_bogus_returns_400(client):
    acc = await _make_account(client, "acc-bogus-from")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_from": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 参数非法"


@pytest.mark.asyncio
async def test_list_date_to_bogus_returns_400(client):
    acc = await _make_account(client, "acc-bogus-to")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_to": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_to 参数非法"


@pytest.mark.asyncio
async def test_list_date_from_bad_month_returns_400(client):
    acc = await _make_account(client, "acc-bad-month")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_from": "2024-13-01"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 参数非法"


@pytest.mark.asyncio
async def test_list_date_from_bad_day_returns_400(client):
    acc = await _make_account(client, "acc-bad-day")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_from": "2024-02-30"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 参数非法"


@pytest.mark.asyncio
async def test_list_date_from_short_form_returns_400(client):
    acc = await _make_account(client, "acc-short-form")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_from": "2024-1-1"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "date_from 参数非法"


@pytest.mark.asyncio
async def test_list_date_range_filters(client):
    acc = await _make_account(client, "acc-range")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat, occurred_on="2024-01-05", note="jan")
    await _make_tx(client, account_id=acc, category_id=cat, occurred_on="2024-02-05", note="feb")
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-01-01", "date_to": "2024-01-31"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["note"] == "jan"


@pytest.mark.asyncio
async def test_list_date_from_empty_means_no_filter(client):
    acc = await _make_account(client, "acc-empty-from")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions", params={"date_from": ""})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_date_params_missing_means_no_filter(client):
    acc = await _make_account(client, "acc-no-params")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat)
    resp = await client.get("/api/transactions")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_date_to_only_valid_returns_200(client):
    acc = await _make_account(client, "acc-to-only")
    cat = await _get_category_id(client, "expense")
    await _make_tx(client, account_id=acc, category_id=cat, occurred_on="2024-01-05")
    resp = await client.get("/api/transactions", params={"date_to": "2024-01-31"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
