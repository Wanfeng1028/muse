from __future__ import annotations


async def _make_account(client, name, type_="cash", opening=0, currency="CNY"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening, "currency": currency},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    for c in resp.json():
        if c.get("name") == name and c.get("kind") == kind:
            return c["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


async def _make_tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_update_income_add_to_account_rejected(client):
    acc_a = await _make_account(client, "更新收入A", opening=0)
    acc_b = await _make_account(client, "更新收入B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="工资入账",
        currency="CNY",
    )
    resp = await client.put(f"/api/transactions/{txn_id}", json={"to_account_id": acc_b})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "收入/支出不能指定转入账户"


async def test_update_income_add_to_account_not_persisted(client):
    acc_a = await _make_account(client, "未生效A", opening=0)
    acc_b = await _make_account(client, "未生效B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=8000,
        occurred_on="2026-01-16",
        note="奖金",
        currency="CNY",
    )
    put_resp = await client.put(f"/api/transactions/{txn_id}", json={"to_account_id": acc_b})
    assert put_resp.status_code == 400
    get_resp = await client.get(f"/api/transactions/{txn_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["to_account_id"] is None
    assert body["account_id"] == acc_a
    assert body["amount_cents"] == 8000
    assert body["note"] == "奖金"
    assert body["category_id"] == salary
    assert body["type"] == "income"


async def test_update_income_add_to_account_then_amount_change_rejected(client):
    acc_a = await _make_account(client, "混合A", opening=0)
    acc_b = await _make_account(client, "混合B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=3000,
        occurred_on="2026-01-17",
        note="兼职",
        currency="CNY",
    )
    resp = await client.put(
        f"/api/transactions/{txn_id}",
        json={"to_account_id": acc_b, "amount_cents": 9999},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "收入/支出不能指定转入账户"
    get_resp = await client.get(f"/api/transactions/{txn_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["to_account_id"] is None
    assert body["amount_cents"] == 3000


async def test_update_income_add_to_account_and_category_rejected(client):
    acc_a = await _make_account(client, "分类A", opening=0)
    acc_b = await _make_account(client, "分类B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    bonus = await _cat_id(client, "奖金", "income")
    txn_id = await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=6600,
        occurred_on="2026-01-19",
        note="分红",
        currency="CNY",
    )
    resp = await client.put(
        f"/api/transactions/{txn_id}",
        json={"to_account_id": acc_b, "category_id": bonus},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "收入/支出不能指定转入账户"
    get_resp = await client.get(f"/api/transactions/{txn_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["to_account_id"] is None
    assert body["category_id"] == salary
    assert body["amount_cents"] == 6600
