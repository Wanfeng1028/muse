from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _make_account(client, name: str = "deep3账户") -> int:
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
    name: str = "deep3计划",
    type_: str = "expense",
    amount_cents: int = 10000,
    day_of_month: int = 15,
    note: str = "note",
    is_active: bool = True,
):
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
    return await client.post("/api/recurring", json=payload)


async def test_create_recurring_missing_name_rejected(client):
    account_id = await _make_account(client, "无名账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await client.post(
        "/api/recurring",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": category_id,
            "amount_cents": 100,
            "day_of_month": 5,
        },
    )
    assert resp.status_code == 422


async def test_create_recurring_missing_account_id_rejected(client):
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "缺账户",
            "type": "expense",
            "category_id": category_id,
            "amount_cents": 100,
            "day_of_month": 5,
        },
    )
    assert resp.status_code == 422


async def test_create_recurring_negative_amount_rejected(client):
    account_id = await _make_account(client, "负额账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, amount_cents=-1)
    assert resp.status_code == 422


async def test_create_recurring_day_of_month_28_accepted(client):
    account_id = await _make_account(client, "day28账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, day_of_month=28)
    assert resp.status_code == 201
    assert resp.json()["day_of_month"] == 28


async def test_create_recurring_income_type_with_income_category(client):
    account_id = await _make_account(client, "收入账户")
    category_id = await _get_category_id(client, "income", "工资")

    resp = await _make_recurring(
        client, account_id, category_id, type_="income", name="工资计划"
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "income"
    assert body["category_id"] == category_id


async def test_create_recurring_is_active_false_persists(client):
    account_id = await _make_account(client, "停用创建账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await _make_recurring(client, account_id, category_id, is_active=False)
    assert resp.status_code == 201
    assert resp.json()["is_active"] is False

    rid = resp.json()["id"]
    fetched = await client.get(f"/api/recurring/{rid}")
    assert fetched.status_code == 200
    assert fetched.json()["is_active"] is False


async def test_create_recurring_note_null_accepted(client):
    account_id = await _make_account(client, "无note账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "无note计划",
            "type": "expense",
            "account_id": account_id,
            "category_id": category_id,
            "amount_cents": 500,
            "day_of_month": 10,
            "note": None,
            "is_active": True,
        },
    )
    assert resp.status_code == 422


async def test_create_recurring_very_long_name_accepted(client):
    account_id = await _make_account(client, "长名账户")
    category_id = await _get_category_id(client, "expense", "餐饮")
    long_name = "长" * 500

    resp = await _make_recurring(client, account_id, category_id, name=long_name)
    assert resp.status_code == 201
    assert resp.json()["name"] == long_name


async def test_list_recurring_empty_returns_empty_list(client):
    resp = await client.get("/api/recurring")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_recurring_orders_active_first_then_id(client):
    account_id = await _make_account(client, "排序账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    inactive = await _make_recurring(
        client, account_id, category_id, name="停用", is_active=False
    )
    active1 = await _make_recurring(
        client, account_id, category_id, name="启用1", is_active=True
    )
    active2 = await _make_recurring(
        client, account_id, category_id, name="启用2", is_active=True
    )
    assert inactive.status_code == 201
    assert active1.status_code == 201
    assert active2.status_code == 201

    resp = await client.get("/api/recurring")
    assert resp.status_code == 200
    items = resp.json()
    ids = [i["id"] for i in items]
    assert ids[0] == active1.json()["id"]
    assert ids[1] == active2.json()["id"]
    assert ids[-1] == inactive.json()["id"]
    assert all(i["is_active"] for i in items[:2])


async def test_update_recurring_amount_and_note(client):
    account_id = await _make_account(client, "更新账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id, amount_cents=1000)
    rid = created.json()["id"]

    resp = await client.put(
        f"/api/recurring/{rid}",
        json={"amount_cents": 9999, "note": "新备注"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_cents"] == 9999
    assert body["note"] == "新备注"


async def test_update_recurring_account_not_found(client):
    account_id = await _make_account(client, "更新账户2")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    resp = await client.put(f"/api/recurring/{rid}", json={"account_id": 999999})
    assert resp.status_code == 404


async def test_update_recurring_category_not_found(client):
    account_id = await _make_account(client, "更新账户3")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    resp = await client.put(f"/api/recurring/{rid}", json={"category_id": 999999})
    assert resp.status_code == 404


async def test_update_recurring_type_category_mismatch(client):
    account_id = await _make_account(client, "更新账户4")
    expense_cat = await _get_category_id(client, "expense", "餐饮")
    await _get_category_id(client, "income", "工资")

    created = await _make_recurring(client, account_id, expense_cat)
    rid = created.json()["id"]

    resp = await client.put(
        f"/api/recurring/{rid}",
        json={"type": "income", "category_id": expense_cat},
    )
    assert resp.status_code == 400


async def test_update_recurring_day_of_month_out_of_range(client):
    account_id = await _make_account(client, "更新账户5")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    resp = await client.put(f"/api/recurring/{rid}", json={"day_of_month": 29})
    assert resp.status_code == 422


async def test_update_recurring_not_found(client):
    resp = await client.put("/api/recurring/999999", json={"note": "x"})
    assert resp.status_code == 404


async def test_update_recurring_type_invalid_value(client):
    account_id = await _make_account(client, "更新账户6")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    resp = await client.put(f"/api/recurring/{rid}", json={"type": "transfer"})
    assert resp.status_code == 422


async def test_update_recurring_empty_body_returns_unchanged(client):
    account_id = await _make_account(client, "更新账户7")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id, name="原名称")
    rid = created.json()["id"]

    resp = await client.put(f"/api/recurring/{rid}", json={})
    assert resp.status_code == 200
    assert resp.json()["name"] == "原名称"


async def test_update_recurring_updated_at_changes(client):
    account_id = await _make_account(client, "更新账户8")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]
    original_updated_at = created.json()["updated_at"]

    resp = await client.put(f"/api/recurring/{rid}", json={"note": "改"})
    assert resp.status_code == 200
    assert resp.json()["updated_at"] >= original_updated_at


async def test_get_recurring_returns_created_fields(client):
    account_id = await _make_account(client, "获取账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(
        client, account_id, category_id, name="获取计划", amount_cents=777
    )
    rid = created.json()["id"]

    resp = await client.get(f"/api/recurring/{rid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == rid
    assert body["name"] == "获取计划"
    assert body["amount_cents"] == 777


async def test_delete_recurring_twice_second_returns_404(client):
    account_id = await _make_account(client, "双删账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    first = await client.delete(f"/api/recurring/{rid}")
    assert first.status_code == 204
    second = await client.delete(f"/api/recurring/{rid}")
    assert second.status_code == 404


async def test_delete_recurring_removes_from_list(client):
    account_id = await _make_account(client, "列表删除账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(client, account_id, category_id)
    rid = created.json()["id"]

    listed = await client.get("/api/recurring")
    assert any(i["id"] == rid for i in listed.json())

    deleted = await client.delete(f"/api/recurring/{rid}")
    assert deleted.status_code == 204

    listed_after = await client.get("/api/recurring")
    assert all(i["id"] != rid for i in listed_after.json())


async def test_upcoming_default_days_returns_list(client):
    resp = await client.get("/api/recurring/upcoming")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_upcoming_days_large_value_accepted(client):
    resp = await client.get("/api/recurring/upcoming", params={"days": 3650})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_upcoming_non_integer_days_rejected(client):
    resp = await client.get("/api/recurring/upcoming", params={"days": "abc"})
    assert resp.status_code == 422


async def test_upcoming_contains_created_active_recurring(client):
    account_id = await _make_account(client, "即将到期账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(
        client, account_id, category_id, day_of_month=1, is_active=True
    )
    rid = created.json()["id"]

    resp = await client.get("/api/recurring/upcoming", params={"days": 30})
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert rid in ids


async def test_upcoming_excludes_inactive_recurring(client):
    account_id = await _make_account(client, "即将停用账户")
    category_id = await _get_category_id(client, "expense", "餐饮")

    created = await _make_recurring(
        client, account_id, category_id, day_of_month=1, is_active=False
    )
    rid = created.json()["id"]

    resp = await client.get("/api/recurring/upcoming", params={"days": 30})
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()]
    assert rid not in ids