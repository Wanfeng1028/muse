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


async def test_audit_identity_includes_opening_balance(client):
    acc_a = await _make_account(client, "A", opening=12345)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")
    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="salary",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="lunch",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["identity"]["holds"] is True
    assert data["totals"]["opening_sum_cents"] == 12345
    assert data["identity"]["expected_cents"] == 15345
    assert data["identity"]["balance_sum_cents"] == 15345
    assert data["identity"]["diff_cents"] == 0


async def test_audit_ok_true_with_opening_balance(client):
    acc_a = await _make_account(client, "A", opening=12345)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")
    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="salary",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="lunch",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["error_count"] == 0
    assert data["warning_count"] == 0
    assert data["issues"] == []


async def test_account_balance_reflects_opening_income_expense(client):
    acc_a = await _make_account(client, "A", opening=12345)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")
    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="salary",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="lunch",
        currency="CNY",
    )

    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    target = None
    for a in resp.json():
        if a["id"] == acc_a:
            target = a
            break
    assert target is not None
    assert target["balance_cents"] == 15345


async def test_audit_expected_excludes_opening_when_account_has_none(client):
    acc_a = await _make_account(client, "A", opening=0)
    salary = await _cat_id(client, "工资", "income")
    food = await _cat_id(client, "餐饮", "expense")
    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        category_id=salary,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="salary",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        category_id=food,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="lunch",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["opening_sum_cents"] == 0
    assert data["identity"]["expected_cents"] == 3000
    assert data["identity"]["balance_sum_cents"] == 3000
    assert data["identity"]["holds"] is True
    assert data["ok"] is True
