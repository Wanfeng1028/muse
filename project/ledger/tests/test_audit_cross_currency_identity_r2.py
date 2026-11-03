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


async def test_cross_currency_transfer_emits_warning(client):
    acc_a = await _make_account(client, "A-CNY", currency="CNY")
    acc_b = await _make_account(client, "B-USD", currency="USD")
    await _make_tx(
        client,
        type="transfer",
        account_id=acc_a,
        to_account_id=acc_b,
        amount_cents=10000,
        occurred_on="2026-01-15",
        note="cross currency",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    matches = [i for i in body["issues"] if i["code"] == "TRANSFER_CROSS_CURRENCY"]
    assert len(matches) == 1, body["issues"]
    assert matches[0]["severity"] == "warning"


async def test_cross_currency_identity_still_holds(client):
    acc_a = await _make_account(client, "A-CNY", currency="CNY")
    acc_b = await _make_account(client, "B-USD", currency="USD")
    await _make_tx(
        client,
        type="transfer",
        account_id=acc_a,
        to_account_id=acc_b,
        amount_cents=10000,
        occurred_on="2026-01-15",
        note="cross currency",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    identity = body["identity"]
    assert identity["holds"] is True
    assert identity["diff_cents"] == 0
    totals = body["totals"]
    assert totals["transfer_out_sum_cents"] == totals["transfer_in_sum_cents"] == 10000


async def test_cross_currency_ok_and_counts(client):
    acc_a = await _make_account(client, "A-CNY", currency="CNY")
    acc_b = await _make_account(client, "B-USD", currency="USD")
    await _make_tx(
        client,
        type="transfer",
        account_id=acc_a,
        to_account_id=acc_b,
        amount_cents=10000,
        occurred_on="2026-01-15",
        note="cross currency",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["error_count"] == 0
    assert body["warning_count"] >= 1


async def test_cross_currency_warning_detail_mentions_currencies(client):
    acc_a = await _make_account(client, "A-CNY", currency="CNY")
    acc_b = await _make_account(client, "B-USD", currency="USD")
    await _make_tx(
        client,
        type="transfer",
        account_id=acc_a,
        to_account_id=acc_b,
        amount_cents=10000,
        occurred_on="2026-01-15",
        note="cross currency",
        currency="CNY",
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    match = next(i for i in body["issues"] if i["code"] == "TRANSFER_CROSS_CURRENCY")
    assert "CNY->USD" in match["detail"]
    assert "未做汇率折算" in match["detail"]
    assert match["transaction_id"] is not None
