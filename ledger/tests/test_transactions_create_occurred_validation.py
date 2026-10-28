from __future__ import annotations

from uuid import uuid4

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


def _tx_payload(account_id: int, category_id: int, occurred_on: str) -> dict:
    return {
        "type": "expense",
        "account_id": account_id,
        "to_account_id": None,
        "category_id": category_id,
        "amount_cents": 100,
        "occurred_on": occurred_on,
        "note": "x",
        "currency": "CNY",
    }


INVALID_OCCURRED_ON = [
    "not-a-date",
    "2024-13-01",
    "2024-01-32",
    "",
    "2024/01/05",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("occurred_on", INVALID_OCCURRED_ON)
async def test_create_invalid_occurred_on_returns_400(client, occurred_on):
    name = f"invalid-occurred-on-{occurred_on or 'empty'}-{uuid4().hex[:8]}"
    acc = await _make_account(client, name)
    cat = await _get_category_id(client, "expense")

    resp = await client.post("/api/transactions", json=_tx_payload(acc, cat, occurred_on))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "occurred_on 参数非法"


@pytest.mark.asyncio
async def test_create_leap_day_occurred_on_returns_201(client):
    acc = await _make_account(client, f"leap-day-occurred-on-{uuid4().hex[:8]}")
    cat = await _get_category_id(client, "expense")

    resp = await client.post(
        "/api/transactions", json=_tx_payload(acc, cat, "2024-02-29")
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_create_valid_occurred_on_persists(client):
    acc = await _make_account(client, f"valid-occurred-on-{uuid4().hex[:8]}")
    cat = await _get_category_id(client, "expense")

    resp = await client.post(
        "/api/transactions", json=_tx_payload(acc, cat, "2024-01-05")
    )
    assert resp.status_code == 201

    resp = await client.get("/api/transactions", params={"account_id": acc})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
