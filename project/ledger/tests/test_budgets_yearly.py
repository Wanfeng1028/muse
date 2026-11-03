from datetime import date


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


async def test_yearly_missing_year_422(client):
    resp = await client.get("/api/budgets/yearly")
    assert resp.status_code == 422, resp.text


async def test_yearly_invalid_year_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "26"})
    assert resp.status_code == 400, resp.text


async def test_yearly_non_numeric_year_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "abcd"})
    assert resp.status_code == 400, resp.text


async def test_yearly_structure_and_order(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["year"] == "2026"
    months = data["months"]
    assert len(months) == 12
    assert [m["year_month"] for m in months] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
    ]


async def test_yearly_with_budget_and_spent(client):
    acc = await _create_account(client, "钱包Y1", opening=0)
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": "2026-03", "amount_cents": 120000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], cat_id, 95000, occurred_on="2026-03-15")

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-03")
    assert m["budget_cents"] == 120000
    assert m["spent_cents"] == 95000
    assert m["pct"] == 79.2
    assert m["has_budget"] is True


async def test_yearly_month_without_budget(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-07")
    assert m["budget_cents"] == 0
    assert m["spent_cents"] == 0
    assert m["pct"] == 0.0
    assert m["has_budget"] is False


async def test_yearly_year_isolation(client):
    acc = await _create_account(client, "钱包Y2", opening=0)
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": "2025-12", "amount_cents": 50000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], cat_id, 30000, occurred_on="2025-12-20")
    await _add_tx(client, acc["id"], cat_id, 10000, occurred_on="2026-01-05")

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m1 = next(x for x in months if x["year_month"] == "2026-01")
    assert m1["budget_cents"] == 0
    assert m1["spent_cents"] == 10000
    assert m1["has_budget"] is False

    resp = await client.get("/api/budgets/yearly", params={"year": "2025"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m12 = next(x for x in months if x["year_month"] == "2025-12")
    assert m12["budget_cents"] == 50000
    assert m12["spent_cents"] == 30000
    assert m12["pct"] == 60.0
    assert m12["has_budget"] is True


async def test_yearly_pct_zero_when_no_budget(client):
    acc = await _create_account(client, "钱包Y3", opening=0)
    cat_id = await _cat_id(client, "餐饮", "expense")

    await _add_tx(client, acc["id"], cat_id, 12345, occurred_on="2026-05-10")

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-05")
    assert m["budget_cents"] == 0
    assert m["spent_cents"] == 12345
    assert m["pct"] == 0.0
    assert m["has_budget"] is False


async def test_yearly_income_excluded(client):
    acc = await _create_account(client, "钱包Y4", opening=0)
    expense_cat = await _cat_id(client, "餐饮", "expense")
    income_cat = await _cat_id(client, "工资", "income")

    resp = await client.post(
        "/api/budgets",
        json={"category_id": expense_cat, "year_month": "2026-04", "amount_cents": 100000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], expense_cat, 20000, occurred_on="2026-04-01")
    await _add_tx(
        client,
        acc["id"],
        income_cat,
        500000,
        kind="income",
        occurred_on="2026-04-01",
    )

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-04")
    assert m["budget_cents"] == 100000
    assert m["spent_cents"] == 20000
    assert m["pct"] == 20.0


async def test_yearly_transfer_excluded(client):
    acc = await _create_account(client, "钱包Y5", opening=0)
    acc2 = await _create_account(client, "钱包Y5B", opening=0)
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat_id, "year_month": "2026-06", "amount_cents": 80000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], cat_id, 40000, occurred_on="2026-06-10")

    resp_tx = await client.post(
        "/api/transactions",
        json={
            "account_id": acc["id"],
            "category_id": None,
            "amount_cents": 99999,
            "type": "transfer",
            "occurred_on": "2026-06-11",
            "note": "",
            "to_account_id": acc2["id"],
        },
    )
    assert resp_tx.status_code == 201, resp_tx.text

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-06")
    assert m["budget_cents"] == 80000
    assert m["spent_cents"] == 40000
    assert m["pct"] == 50.0


async def test_yearly_multiple_categories_summed(client):
    acc = await _create_account(client, "钱包Y6", opening=0)
    cat1 = await _cat_id(client, "餐饮", "expense")
    cat2 = await _cat_id(client, "交通", "expense")

    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat1, "year_month": "2026-08", "amount_cents": 60000},
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/budgets",
        json={"category_id": cat2, "year_month": "2026-08", "amount_cents": 40000},
    )
    assert resp.status_code == 201, resp.text

    await _add_tx(client, acc["id"], cat1, 30000, occurred_on="2026-08-05")
    await _add_tx(client, acc["id"], cat2, 20000, occurred_on="2026-08-06")

    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    months = resp.json()["months"]
    m = next(x for x in months if x["year_month"] == "2026-08")
    assert m["budget_cents"] == 100000
    assert m["spent_cents"] == 50000
    assert m["pct"] == 50.0
    assert m["has_budget"] is True
