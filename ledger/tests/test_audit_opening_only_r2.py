from __future__ import annotations


async def _make_account(client, name, type_="cash", opening=0, currency="CNY"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening, "currency": currency},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_audit_opening_only_ok(client):
    await _make_account(client, "期初户A", opening=7777)
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["error_count"] == 0


async def test_audit_opening_only_identity_holds(client):
    await _make_account(client, "期初户B", opening=7777)
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    identity = resp.json()["identity"]
    assert identity["holds"] is True
    assert identity["balance_sum_cents"] == 7777
    assert identity["expected_cents"] == 7777
    assert identity["diff_cents"] == 0


async def test_audit_opening_only_totals(client):
    await _make_account(client, "期初户C", opening=7777)
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    totals = resp.json()["totals"]
    assert totals["transactions"] == 0
    assert totals["opening_sum_cents"] == 7777
    assert totals["income_sum_cents"] == 0
    assert totals["expense_sum_cents"] == 0
    assert totals["transfer_out_sum_cents"] == 0
    assert totals["transfer_in_sum_cents"] == 0


async def test_audit_opening_only_no_issues(client):
    await _make_account(client, "期初户D", opening=7777)
    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["warning_count"] == 0
    assert body["issues"] == []
