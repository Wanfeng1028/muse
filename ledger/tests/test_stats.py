from datetime import date, datetime


async def _create_account(client, name, opening):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": opening},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(f"category {name} ({kind}) not found")


async def _tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _prev_month_day15():
    today = date.today()
    if today.month == 1:
        y, m = today.year - 1, 12
    else:
        y, m = today.year, today.month - 1
    return date(y, m, 15).isoformat()


async def _prepare(client):
    await _create_account(client, "A", 100000)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")

    this_month = date.today().isoformat()
    prev = _prev_month_day15()

    await _tx(
        client,
        account_id=(await client.get("/api/accounts")).json()[0]["id"],
        category_id=salary,
        type="income",
        amount_cents=500000,
        occurred_on=this_month,
        note="本月工资",
    )
    await _tx(
        client,
        account_id=(await client.get("/api/accounts")).json()[0]["id"],
        category_id=food,
        type="expense",
        amount_cents=80000,
        occurred_on=this_month,
        note="本月餐饮",
    )
    await _tx(
        client,
        account_id=(await client.get("/api/accounts")).json()[0]["id"],
        category_id=salary,
        type="income",
        amount_cents=400000,
        occurred_on=prev,
        note="上月工资",
    )
    await _tx(
        client,
        account_id=(await client.get("/api/accounts")).json()[0]["id"],
        category_id=food,
        type="expense",
        amount_cents=60000,
        occurred_on=prev,
        note="上月餐饮",
    )


async def test_summary(client):
    await _prepare(client)
    month = datetime.now().strftime("%Y-%m")
    resp = await client.get("/api/stats/summary", params={"month": month})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["income_cents"] == 500000
    assert data["expense_cents"] == 80000
    assert data["net_cents"] == 420000


async def test_summary_default_month(client):
    await _prepare(client)
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["month"] == datetime.now().strftime("%Y-%m")


async def test_trend(client):
    await _prepare(client)
    resp = await client.get("/api/stats/trend", params={"months": 2})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 2
    months = [item["month"] for item in data]
    assert months == sorted(months)
    assert data[0]["income_cents"] == 400000
    assert data[1]["income_cents"] == 500000


async def test_by_category(client):
    await _prepare(client)
    month = datetime.now().strftime("%Y-%m")
    resp = await client.get("/api/stats/by-category", params={"month": month, "kind": "expense"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    food = next(item for item in data if item["name"] == "餐饮")
    assert food["total_cents"] == 80000


async def test_net_worth(client):
    await _prepare(client)
    resp = await client.get("/api/stats/net-worth")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_cents"] == 100000 + 500000 - 80000 + 400000 - 60000
