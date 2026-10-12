from datetime import date, datetime


async def _create_account(client, name, opening=0):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": opening},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["name"] == name and c["kind"] == kind:
            return c["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


async def _add_tx(client, account_id, category_id, amount_cents, kind="expense", occurred_on=None):
    if occurred_on is None:
        occurred_on = date.today().isoformat()
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "amount_cents": amount_cents,
            "type": kind,
            "occurred_on": occurred_on,
            "note": "",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _this_month():
    return datetime.now().strftime("%Y-%m")


async def test_budget_progress(client):
    acc = await _create_account(client, "钱包A", opening=0)
    cat_id = await _cat_id(client, "餐饮", "expense")
    month = _this_month()

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": month, "amount_cents": 100000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], cat_id, 10000)
    await _add_tx(client, acc["id"], cat_id, 20000)

    resp = await client.get("/api/budgets", params={"month": month})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    item = next((x for x in items if x["category_id"] == cat_id), None)
    assert item is not None, items
    assert item["spent_cents"] == 30000
    assert item["remaining_cents"] == 70000
    assert item["pct"] == 30.0


async def test_duplicate_409(client):
    cat_id = await _cat_id(client, "餐饮", "expense")
    month = _this_month()

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": month, "amount_cents": 50000},
    )
    assert resp.status_code == 201, resp.text

    resp2 = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": month, "amount_cents": 60000},
    )
    assert resp2.status_code == 409, resp2.text


async def test_income_category_400(client):
    cat_id = await _cat_id(client, "工资", "income")
    month = _this_month()

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": month, "amount_cents": 100000},
    )
    assert resp.status_code == 400, resp.text


async def test_crud(client):
    cat_id = await _cat_id(client, "餐饮", "expense")
    month = _this_month()

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": month, "amount_cents": 100000},
    )
    assert resp.status_code == 201, resp.text
    budget_id = resp.json()["id"]

    resp = await client.put(
        f"/api/budgets/{budget_id}",
        json={"amount_cents": 200000},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["amount_cents"] == 200000

    resp = await client.delete(f"/api/budgets/{budget_id}")
    assert resp.status_code == 204, resp.text

    resp = await client.get("/api/budgets", params={"month": month})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_missing_month_400(client):
    resp = await client.get("/api/budgets")
    assert resp.status_code in (400, 422)
