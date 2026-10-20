from __future__ import annotations


async def _make_account(client, name, type_="cash", opening=0, currency="CNY"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening, "currency": currency},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _make_tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _balance_of(client, account_id):
    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    for a in resp.json():
        if a["id"] == account_id:
            return a["balance_cents"]
    raise AssertionError(f"account not found: {account_id}")


async def test_transfer_reversal_identity_holds(client):
    a_id = await _make_account(client, "红冲A", opening=0)
    b_id = await _make_account(client, "红冲B", opening=0)
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=10000,
        occurred_on="2026-01-15",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b_id,
        to_account_id=a_id,
        amount_cents=10000,
        occurred_on="2026-01-16",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["error_count"] == 0
    assert body["identity"]["holds"] is True
    assert body["identity"]["diff_cents"] == 0
    assert body["totals"]["transfer_out_sum_cents"] == 20000
    assert body["totals"]["transfer_in_sum_cents"] == 20000


async def test_transfer_reversal_balances_zero(client):
    a_id = await _make_account(client, "归零A", opening=0)
    b_id = await _make_account(client, "归零B", opening=0)
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=10000,
        occurred_on="2026-01-15",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b_id,
        to_account_id=a_id,
        amount_cents=10000,
        occurred_on="2026-01-16",
        currency="CNY",
    )
    assert await _balance_of(client, a_id) == 0
    assert await _balance_of(client, b_id) == 0


async def test_transfer_reversal_then_new_transfer_holds(client):
    a_id = await _make_account(client, "续A", opening=0)
    b_id = await _make_account(client, "续B", opening=0)
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=10000,
        occurred_on="2026-01-15",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b_id,
        to_account_id=a_id,
        amount_cents=10000,
        occurred_on="2026-01-16",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=3000,
        occurred_on="2026-01-17",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["identity"]["holds"] is True
    assert body["identity"]["diff_cents"] == 0
    assert body["totals"]["transfer_out_sum_cents"] == 23000
    assert body["totals"]["transfer_in_sum_cents"] == 23000
    assert await _balance_of(client, a_id) == -3000
    assert await _balance_of(client, b_id) == 3000


async def test_transfer_reversal_identity_totals_consistent(client):
    a_id = await _make_account(client, "恒等A", opening=0)
    b_id = await _make_account(client, "恒等B", opening=0)
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=10000,
        occurred_on="2026-01-15",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=b_id,
        to_account_id=a_id,
        amount_cents=10000,
        occurred_on="2026-01-16",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=a_id,
        to_account_id=b_id,
        amount_cents=3000,
        occurred_on="2026-01-17",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    identity = body["identity"]
    expected = (
        body["totals"]["opening_sum_cents"]
        + body["totals"]["income_sum_cents"]
        - body["totals"]["expense_sum_cents"]
    )
    assert identity["expected_cents"] == expected
    assert identity["balance_sum_cents"] == expected
    assert identity["diff_cents"] == identity["balance_sum_cents"] - identity["expected_cents"]
    assert body["error_count"] == 0
    assert body["warning_count"] == 0
