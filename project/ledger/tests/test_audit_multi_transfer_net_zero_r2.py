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


async def _balance(client, account_id):
    resp = await client.get("/api/accounts")
    assert resp.status_code == 200
    for a in resp.json():
        if a["id"] == account_id:
            return a["balance_cents"]
    raise AssertionError(f"account not found: {account_id}")


async def test_multi_transfer_net_zero_identity_holds(client):
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0)
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=5000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=3000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=b, to_account_id=a,
                   amount_cents=8000, occurred_on="2026-01-15", currency="CNY")

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["transfer_out_sum_cents"] == 16000
    assert data["totals"]["transfer_in_sum_cents"] == 16000
    assert data["identity"]["holds"] is True
    assert data["identity"]["diff_cents"] == 0
    assert data["ok"] is True
    assert data["error_count"] == 0


async def test_multi_transfer_net_zero_account_balances_zero(client):
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0)
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=5000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=3000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=b, to_account_id=a,
                   amount_cents=8000, occurred_on="2026-01-15", currency="CNY")

    assert await _balance(client, a) == 0
    assert await _balance(client, b) == 0


async def test_extra_one_cent_transfer_identity_still_holds(client):
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0)
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=5000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=3000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=b, to_account_id=a,
                   amount_cents=8000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=1, occurred_on="2026-01-15", currency="CNY")

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["transfer_out_sum_cents"] == 16001
    assert data["totals"]["transfer_in_sum_cents"] == 16001
    assert data["identity"]["holds"] is True
    assert data["identity"]["diff_cents"] == 0
    assert data["ok"] is True


async def test_extra_one_cent_transfer_balances(client):
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0)
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=5000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=3000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=b, to_account_id=a,
                   amount_cents=8000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=1, occurred_on="2026-01-15", currency="CNY")

    assert await _balance(client, a) == -1
    assert await _balance(client, b) == 1


async def test_transfer_totals_counted_by_amount_not_count(client):
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0)
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=5000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=a, to_account_id=b,
                   amount_cents=3000, occurred_on="2026-01-15", currency="CNY")
    await _make_tx(client, type="transfer", account_id=b, to_account_id=a,
                   amount_cents=8000, occurred_on="2026-01-15", currency="CNY")

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["totals"]["transactions"] == 3
    assert data["totals"]["accounts"] == 2
    assert data["totals"]["opening_sum_cents"] == 0
    assert data["totals"]["income_sum_cents"] == 0
    assert data["totals"]["expense_sum_cents"] == 0
    assert data["totals"]["transfer_out_sum_cents"] == 16000
    assert data["totals"]["transfer_in_sum_cents"] == 16000
    assert data["identity"]["balance_sum_cents"] == 0
    assert data["identity"]["expected_cents"] == 0
