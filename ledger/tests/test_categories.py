from datetime import date


async def _create_category(client, name, kind="expense", icon="🧪", color="#123456"):
    resp = await client.post(
        "/api/categories",
        json={"name": name, "kind": kind, "icon": icon, "color": color},
    )
    return resp


async def _create_account(client, name="测试账户"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    return resp


async def _create_expense(client, account_id, category_id, amount_cents=1000):
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "amount_cents": amount_cents,
            "account_id": account_id,
            "category_id": category_id,
            "occurred_on": date.today().isoformat(),
        },
    )
    return resp


async def test_seed_categories(client):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0

    expense_names = [c["name"] for c in data if c["kind"] == "expense"]
    income_names = [c["name"] for c in data if c["kind"] == "income"]

    assert "餐饮" in expense_names
    assert "工资" in income_names


async def test_create_and_list(client):
    resp = await _create_category(client, "测试分类", kind="expense", icon="🧪", color="#123456")
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "测试分类"
    assert created["kind"] == "expense"

    list_resp = await client.get("/api/categories", params={"kind": "expense"})
    assert list_resp.status_code == 200
    names = [c["name"] for c in list_resp.json()]
    assert "测试分类" in names


async def test_duplicate_409(client):
    first = await _create_category(client, "重复分类", kind="expense")
    assert first.status_code == 201

    second = await _create_category(client, "重复分类", kind="expense")
    assert second.status_code == 409


async def test_delete_used_category_409(client):
    cat_resp = await _create_category(client, "被引用分类", kind="expense")
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    acc_resp = await _create_account(client, "被引用账户")
    assert acc_resp.status_code in (200, 201)
    account_id = acc_resp.json()["id"]

    tx_resp = await _create_expense(client, account_id, category_id)
    assert tx_resp.status_code in (200, 201)

    del_resp = await client.delete(f"/api/categories/{category_id}")
    assert del_resp.status_code == 409


async def test_delete_unused_ok(client):
    cat_resp = await _create_category(client, "未使用分类", kind="expense")
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    del_resp = await client.delete(f"/api/categories/{category_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get("/api/categories", params={"kind": "expense"})
    assert list_resp.status_code == 200
    ids = [c["id"] for c in list_resp.json()]
    assert category_id not in ids


async def test_update_category(client):
    cat_resp = await _create_category(client, "更新分类", kind="expense", icon="🧪", color="#123456")
    assert cat_resp.status_code == 201
    category_id = cat_resp.json()["id"]

    update_resp = await client.put(
        f"/api/categories/{category_id}",
        json={"icon": "🎯", "color": "#abcdef"},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["icon"] == "🎯"
    assert updated["color"] == "#abcdef"

    get_resp = await client.get("/api/categories", params={"kind": "expense"})
    assert get_resp.status_code == 200
    match = [c for c in get_resp.json() if c["id"] == category_id]
    assert len(match) == 1
    assert match[0]["icon"] == "🎯"
    assert match[0]["color"] == "#abcdef"
