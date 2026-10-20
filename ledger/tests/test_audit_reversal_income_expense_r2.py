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


async def test_audit_reversal_income_expense_ok(client):
    acc_a = await _make_account(client, "红冲A", opening=0)
    income_cat = await _cat_id(client, "工资", "income")
    expense_cat = await _cat_id(client, "其他", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        to_account_id=None,
        category_id=income_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="工资入账",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        to_account_id=None,
        category_id=expense_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="退款红冲",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ok"] is True
    assert data["error_count"] == 0
    assert data["warning_count"] == 0
    assert data["issues"] == []

    identity = data["identity"]
    assert identity["holds"] is True
    assert identity["diff_cents"] == 0
    assert identity["balance_sum_cents"] == 0
    assert identity["expected_cents"] == 0

    totals = data["totals"]
    assert totals["accounts"] == 1
    assert totals["transactions"] == 2
    assert totals["opening_sum_cents"] == 0
    assert totals["income_sum_cents"] == 5000
    assert totals["expense_sum_cents"] == 5000
    assert totals["transfer_out_sum_cents"] == 0
    assert totals["transfer_in_sum_cents"] == 0


async def test_audit_reversal_account_balance_zero(client):
    acc_a = await _make_account(client, "红冲B", opening=0)
    income_cat = await _cat_id(client, "工资", "income")
    expense_cat = await _cat_id(client, "其他", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        to_account_id=None,
        category_id=income_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="工资入账",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        to_account_id=None,
        category_id=expense_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="退款红冲",
        currency="CNY",
    )

    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    accounts = resp.json()
    target = None
    for a in accounts:
        if a["id"] == acc_a:
            target = a
            break
    assert target is not None
    assert target["name"] == "红冲B"
    assert target["balance_cents"] == 0
    assert target["opening_balance_cents"] == 0


async def test_audit_reversal_issue_codes_absent(client):
    acc_a = await _make_account(client, "红冲C", opening=0)
    income_cat = await _cat_id(client, "工资", "income")
    expense_cat = await _cat_id(client, "其他", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        to_account_id=None,
        category_id=income_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="工资入账",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        to_account_id=None,
        category_id=expense_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="退款红冲",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()

    codes = [i["code"] for i in data["issues"]]
    assert "IDENTITY_BROKEN" not in codes
    assert "ACCOUNT_NOT_FOUND" not in codes
    assert "CATEGORY_NOT_FOUND" not in codes
    assert "CATEGORY_KIND_MISMATCH" not in codes
    assert "TRANSACTION_MISSING_CATEGORY" not in codes
    assert "UNKNOWN_TYPE" not in codes


async def test_audit_reversal_partial_offset_identity_holds(client):
    acc_a = await _make_account(client, "红冲D", opening=0)
    income_cat = await _cat_id(client, "工资", "income")
    expense_cat = await _cat_id(client, "其他", "expense")

    await _make_tx(
        client,
        type="income",
        account_id=acc_a,
        to_account_id=None,
        category_id=income_cat,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="工资入账",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc_a,
        to_account_id=None,
        category_id=expense_cat,
        amount_cents=2000,
        occurred_on="2026-01-15",
        note="部分红冲",
        currency="CNY",
    )

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ok"] is True
    assert data["error_count"] == 0
    assert data["warning_count"] == 0
    assert data["identity"]["holds"] is True
    assert data["identity"]["diff_cents"] == 0
    assert data["identity"]["balance_sum_cents"] == 3000
    assert data["identity"]["expected_cents"] == 3000

    totals = data["totals"]
    assert totals["income_sum_cents"] == 5000
    assert totals["expense_sum_cents"] == 2000

    resp2 = await client.get("/api/accounts")
    assert resp2.status_code == 200
    target = None
    for a in resp2.json():
        if a["id"] == acc_a:
            target = a
            break
    assert target is not None
    assert target["balance_cents"] == 3000
