from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _make_account(client, name: str = "深测账户") -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_category_id(client, kind: str, name: str) -> int:
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    for cat in resp.json():
        if cat["name"] == name:
            return cat["id"]
    raise AssertionError(f"category {name!r} (kind={kind}) not found")


async def _make_recurring(
    client,
    account_id: int,
    category_id: int | None,
    *,
    name: str = "深测计划",
    type_: str = "expense",
    amount_cents: int = 10000,
    day_of_month: int = 15,
    note: str = "note",
    is_active: bool = True,
) -> dict:
    payload = {
        "name": name,
        "type": type_,
        "account_id": account_id,
        "category_id": category_id,
        "amount_cents": amount_cents,
        "day_of_month": day_of_month,
        "note": note,
        "is_active": is_active,
    }
    resp = await client.post("/api/recurring", json=payload)
    return resp


async def test_create_recurring_echoes_fields_deep2(client):
    account_id = await _make_account(client, "回显账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(
        client,
        account_id,
        category_id,
        name="房租计划",
        type_="expense",
        amount_cents=250000,
        day_of_month=1,
        note="每月房租",
        is_active=True,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "房租计划"
    assert body["type"] == "expense"
    assert body["account_id"] == account_id
    assert body["category_id"] == category_id
    assert body["amount_cents"] == 250000
    assert body["day_of_month"] == 1
    assert body["note"] == "每月房租"
    assert body["is_active"] is True
    assert isinstance(body["id"], int)


async def test_create_recurring_invalid_type_transfer_deep2(client):
    account_id = await _make_account(client, "非法类型账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, type_="transfer")
    assert resp.status_code == 422


async def test_create_recurring_day_of_month_zero_deep2(client):
    account_id = await _make_account(client, "day零账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, day_of_month=0)
    assert resp.status_code == 422


async def test_create_recurring_day_of_month_29_deep2(client):
    account_id = await _make_account(client, "day29账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, day_of_month=29)
    assert resp.status_code == 422


async def test_create_recurring_amount_cents_zero_deep2(client):
    account_id = await _make_account(client, "零金额账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, amount_cents=0)
    assert resp.status_code == 422


async def test_create_recurring_account_not_found_deep2(client):
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, 999999, category_id)
    assert resp.status_code == 404


async def test_create_recurring_category_not_found_deep2(client):
    account_id = await _make_account(client, "缺分类账户")

    resp = await _make_recurring(client, account_id, 999999)
    assert resp.status_code == 404


async def test_create_recurring_type_category_kind_mismatch_deep2(client):
    account_id = await _make_account(client, "类型不匹配账户")
    income_category_id = await _get_category_id(client, "income", "工资")

    resp = await _make_recurring(
        client, account_id, income_category_id, type_="expense"
    )
    assert resp.status_code == 400


async def test_create_recurring_missing_category_id_deep2(client):
    account_id = await _make_account(client, "缺category账户")

    resp = await _make_recurring(client, account_id, None)
    assert resp.status_code == 400


async def test_update_recurring_is_active_false_excludes_from_upcoming_deep2(client):
    account_id = await _make_account(client, "停用账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(
        client, account_id, category_id, day_of_month=1, is_active=True
    )
    assert created.status_code == 201
    recurring_id = created.json()["id"]

    upcoming_before = await client.get("/api/recurring/upcoming", params={"days": 30})
    assert upcoming_before.status_code == 200
    assert any(item["id"] == recurring_id for item in upcoming_before.json())

    updated = await client.put(
        f"/api/recurring/{recurring_id}",
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    upcoming_after = await client.get("/api/recurring/upcoming", params={"days": 30})
    assert upcoming_after.status_code == 200
    assert all(item["id"] != recurring_id for item in upcoming_after.json())


async def test_delete_recurring_then_get_returns_404_deep2(client):
    account_id = await _make_account(client, "删除账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    assert created.status_code == 201
    recurring_id = created.json()["id"]

    deleted = await client.delete(f"/api/recurring/{recurring_id}")
    assert deleted.status_code == 204

    fetched = await client.get(f"/api/recurring/{recurring_id}")
    assert fetched.status_code == 404


async def test_delete_recurring_not_found_deep2(client):
    resp = await client.delete("/api/recurring/999999")
    assert resp.status_code == 404


async def test_upcoming_days_zero_is_valid_deep2(client):
    resp = await client.get("/api/recurring/upcoming", params={"days": 0})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_upcoming_days_negative_rejected_deep2(client):
    resp = await client.get("/api/recurring/upcoming", params={"days": -1})
    assert resp.status_code == 422


async def test_get_recurring_not_found_deep2(client):
    resp = await client.get("/api/recurring/999999")
    assert resp.status_code == 404