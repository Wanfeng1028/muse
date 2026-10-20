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


async def _balance(client, account_id):
    resp = await client.get("/api/accounts")
    assert resp.status_code == 200, resp.text
    for a in resp.json():
        if a["id"] == account_id:
            return a["balance_cents"]
    raise AssertionError(f"account not found: {account_id}")


async def test_account_balance_full_formula(client):
    a = await _make_account(client, "余额A", opening=1000)
    b = await _make_account(client, "余额B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=a,
        to_account_id=None,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="收入",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=a,
        to_account_id=None,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="支出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=a,
        to_account_id=b,
        category_id=None,
        amount_cents=1500,
        occurred_on="2026-01-15",
        note="转出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b,
        to_account_id=a,
        category_id=None,
        amount_cents=300,
        occurred_on="2026-01-15",
        note="转入",
        currency="CNY",
    )

    assert await _balance(client, a) == 1000 + 5000 - 2000 - 1500 + 300
    assert await _balance(client, a) == 2800
    assert await _balance(client, b) == 0 + 1500 - 300
    assert await _balance(client, b) == 1200


async def test_balance_each_term_matters(client):
    a = await _make_account(client, "项A", opening=1000)
    b = await _make_account(client, "项B", opening=0)
    salary = await _cat_id(client, "工资", "income")

    assert await _balance(client, a) == 1000

    await _make_tx(
        client,
        type="income",
        account_id=a,
        to_account_id=None,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="收入",
        currency="CNY",
    )
    assert await _balance(client, a) == 6000

    await _make_tx(
        client,
        type="transfer",
        account_id=a,
        to_account_id=b,
        category_id=None,
        amount_cents=1500,
        occurred_on="2026-01-15",
        note="转出",
        currency="CNY",
    )
    assert await _balance(client, a) == 4500
    assert await _balance(client, b) == 1500

    await _make_tx(
        client,
        type="transfer",
        account_id=b,
        to_account_id=a,
        category_id=None,
        amount_cents=300,
        occurred_on="2026-01-15",
        note="转入",
        currency="CNY",
    )
    assert await _balance(client, a) == 4800
    assert await _balance(client, b) == 1200


async def test_expense_deletion_recomputes_balance(client):
    a = await _make_account(client, "删支A", opening=1000)
    b = await _make_account(client, "删支B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=a,
        to_account_id=None,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="收入",
        currency="CNY",
    )
    expense_id = await _make_tx(
        client,
        type="expense",
        account_id=a,
        to_account_id=None,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="支出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=a,
        to_account_id=b,
        category_id=None,
        amount_cents=1500,
        occurred_on="2026-01-15",
        note="转出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b,
        to_account_id=a,
        category_id=None,
        amount_cents=300,
        occurred_on="2026-01-15",
        note="转入",
        currency="CNY",
    )

    assert await _balance(client, a) == 2800

    resp = await client.delete(f"/api/transactions/{expense_id}")
    assert resp.status_code == 204, resp.text

    assert await _balance(client, a) == 1000 + 5000 - 1500 + 300
    assert await _balance(client, a) == 4800
    assert await _balance(client, b) == 1200


async def test_balance_formula_persists_across_reads(client):
    a = await _make_account(client, "读A", opening=1000)
    b = await _make_account(client, "读B", opening=0)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=a,
        to_account_id=None,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="收入",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=a,
        to_account_id=None,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="支出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=a,
        to_account_id=b,
        category_id=None,
        amount_cents=1500,
        occurred_on="2026-01-15",
        note="转出",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b,
        to_account_id=a,
        category_id=None,
        amount_cents=300,
        occurred_on="2026-01-15",
        note="转入",
        currency="CNY",
    )

    first = await _balance(client, a)
    second = await _balance(client, a)
    assert first == 2800
    assert second == 2800
    assert first == second
