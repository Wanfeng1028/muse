async def test_create_account(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "现金", "type": "cash", "opening_balance_cents": 10000},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "现金"
    assert data["type"] == "cash"
    assert data["opening_balance_cents"] == 10000
    assert data["balance_cents"] == 10000


async def test_account_crud(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "招商银行", "type": "savings", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    resp = await client.put(
        f"/api/accounts/{account_id}",
        json={"name": "招商银行储蓄"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "招商银行储蓄"

    resp = await client.get(f"/api/accounts/{account_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == account_id
    assert resp.json()["name"] == "招商银行储蓄"

    resp = await client.delete(f"/api/accounts/{account_id}")
    assert resp.status_code == 204, resp.text

    resp = await client.get(f"/api/accounts/{account_id}")
    assert resp.status_code == 404

    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert account_id not in ids


async def test_balance_with_transactions(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "测试账户A", "type": "cash", "opening_balance_cents": 5000},
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.json()
    income_id = next(c["id"] for c in cats if c["name"] == "工资" and c["kind"] == "income")
    expense_id = next(c["id"] for c in cats if c["name"] == "餐饮" and c["kind"] == "expense")

    occurred_on = "2024-05-15"

    resp = await client.post(
        "/api/transactions",
        json={
            "type": "income",
            "account_id": account_id,
            "category_id": income_id,
            "amount_cents": 5000,
            "occurred_on": occurred_on,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": account_id,
            "category_id": expense_id,
            "amount_cents": 2000,
            "occurred_on": occurred_on,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    accounts = resp.json()
    target = next(a for a in accounts if a["id"] == account_id)
    assert target["balance_cents"] == 8000


async def test_archive_keeps_transactions(client):
    resp = await client.post(
        "/api/accounts",
        json={"name": "待归档账户", "type": "savings", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    resp = await client.get("/api/categories", params={"kind": "income"})
    assert resp.status_code == 200
    category_id = next(c["id"] for c in resp.json() if c["name"] == "工资")

    resp = await client.post(
        "/api/transactions",
        json={
            "type": "income",
            "account_id": account_id,
            "category_id": category_id,
            "amount_cents": 3000,
            "occurred_on": "2024-06-01",
        },
    )
    assert resp.status_code == 201
    transaction_id = resp.json()["id"]

    resp = await client.delete(f"/api/accounts/{account_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/transactions/{transaction_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == transaction_id
    assert data["account_id"] == account_id
    assert data["amount_cents"] == 3000
