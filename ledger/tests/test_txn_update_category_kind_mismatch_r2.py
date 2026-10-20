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


async def test_update_category_kind_mismatch_rejected(client):
    acc = await _make_account(client, "A", opening=100000)
    dining = await _cat_id(client, "餐饮", "expense")
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        category_id=dining,
        amount_cents=3000,
        occurred_on="2026-01-15",
        note="午饭",
        currency="CNY",
    )
    resp = await client.put("/api/transactions/" + str(txn_id), json={"category_id": salary})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "分类类型与交易类型不一致"


async def test_update_category_kind_mismatch_not_persisted(client):
    acc = await _make_account(client, "A", opening=100000)
    dining = await _cat_id(client, "餐饮", "expense")
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        category_id=dining,
        amount_cents=3000,
        occurred_on="2026-01-15",
        note="午饭",
        currency="CNY",
    )
    bad = await client.put("/api/transactions/" + str(txn_id), json={"category_id": salary})
    assert bad.status_code == 400
    got = await client.get("/api/transactions/" + str(txn_id))
    assert got.status_code == 200
    assert got.json()["category_id"] == dining
    assert got.json()["amount_cents"] == 3000


async def test_update_category_kind_mismatch_keeps_note(client):
    acc = await _make_account(client, "A", opening=100000)
    dining = await _cat_id(client, "餐饮", "expense")
    salary = await _cat_id(client, "工资", "income")
    txn_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        category_id=dining,
        amount_cents=3000,
        occurred_on="2026-01-15",
        note="午饭",
        currency="CNY",
    )
    bad = await client.put("/api/transactions/" + str(txn_id), json={"category_id": salary})
    assert bad.status_code == 400
    got = await client.get("/api/transactions/" + str(txn_id))
    assert got.status_code == 200
    assert got.json()["note"] == "午饭"


async def test_update_note_only_succeeds(client):
    acc = await _make_account(client, "A", opening=100000)
    dining = await _cat_id(client, "餐饮", "expense")
    txn_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        category_id=dining,
        amount_cents=3000,
        occurred_on="2026-01-15",
        note="午饭",
        currency="CNY",
    )
    resp = await client.put("/api/transactions/" + str(txn_id), json={"note": "改备注"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "改备注"
    got = await client.get("/api/transactions/" + str(txn_id))
    assert got.status_code == 200
    assert got.json()["note"] == "改备注"
    assert got.json()["category_id"] == dining
