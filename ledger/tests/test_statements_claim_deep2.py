from __future__ import annotations

import pytest


ALIPAY_CSV = (
    "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
    "2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出\n"
    "2024-01-03 12:30:00,某公司,工资,8000.00,收入\n"
)


async def _make_account(client, name="现金账户"):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(client, account_id, csv_text=ALIPAY_CSV, filename="alipay.csv"):
    resp = await client.post(
        "/api/statements/upload",
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    return body["batch"]["id"], body["parsed"]


async def _confirm(client, batch_id):
    resp = await client.post(f"/api/statements/{batch_id}/confirm")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _find_category(client, kind, name):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(f"category {name} not found for kind {kind}")


async def _items(client, batch_id, **params):
    resp = await client.get(f"/api/statements/{batch_id}/items", params=params)
    assert resp.status_code == 200
    return resp.json()


async def _get_item_by_direction(client, batch_id, direction):
    body = await _items(client, batch_id)
    for it in body["items"]:
        if it["direction"] == direction:
            return it
    raise AssertionError(f"no item with direction {direction}")


@pytest.mark.asyncio
async def test_upload_items_total_and_status_filter_deep2(client):
    aid = await _make_account(client)
    batch_id, parsed = await _upload(client, aid)
    assert parsed == 2

    await _confirm(client, batch_id)

    body = await _items(client, batch_id)
    assert body["total"] == 2
    assert len(body["items"]) == 2
    for it in body["items"]:
        assert it["status"] == "pending"

    pending = await _items(client, batch_id, status="pending")
    assert pending["total"] == 2
    assert all(it["status"] == "pending" for it in pending["items"])

    claimed = await _items(client, batch_id, status="claimed")
    assert claimed["total"] == 0
    assert claimed["items"] == []

    skipped = await _items(client, batch_id, status="skipped")
    assert skipped["total"] == 0
    assert skipped["items"] == []


@pytest.mark.asyncio
async def test_items_pagination_limit_offset_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    page1 = await _items(client, batch_id, limit=1, offset=0)
    assert page1["total"] == 2
    assert len(page1["items"]) == 1

    page2 = await _items(client, batch_id, limit=1, offset=1)
    assert page2["total"] == 2
    assert len(page2["items"]) == 1

    assert page1["items"][0]["id"] != page2["items"][0]["id"]


@pytest.mark.asyncio
async def test_items_batch_not_found_deep2(client):
    resp = await client.get("/api/statements/999999/items")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_out_item_with_expense_category_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "expense", "餐饮")

    item = await _get_item_by_direction(client, batch_id, "out")
    assert item["status"] == "pending"

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert resp.status_code == 200

    body = await _items(client, batch_id, status="claimed")
    assert body["total"] == 1
    claimed_item = body["items"][0]
    assert claimed_item["id"] == item["id"]
    assert claimed_item["status"] == "claimed"
    assert claimed_item["transaction_id"] is not None

    txn_resp = await client.get(f"/api/transactions/{claimed_item['transaction_id']}")
    assert txn_resp.status_code == 200
    txn = txn_resp.json()
    assert txn["category_id"] == cid
    assert txn["type"] != "transfer"


@pytest.mark.asyncio
async def test_claim_in_item_with_expense_category_mismatch_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "expense", "餐饮")

    item = await _get_item_by_direction(client, batch_id, "in")
    assert item["status"] == "pending"

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert resp.status_code == 400

    body = await _items(client, batch_id, status="pending")
    assert any(it["id"] == item["id"] for it in body["items"])


@pytest.mark.asyncio
async def test_claim_with_nonexistent_category_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": 999999, "save_rule": False},
    )
    assert resp.status_code == 404

    body = await _items(client, batch_id, status="pending")
    assert any(it["id"] == item["id"] for it in body["items"])


@pytest.mark.asyncio
async def test_claim_nonexistent_item_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "expense", "餐饮")

    resp = await client.post(
        "/api/statements/items/999999/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_twice_returns_400_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "expense", "餐饮")

    item = await _get_item_by_direction(client, batch_id, "out")

    first = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_claim_transfer_success_deep2(client):
    aid = await _make_account(client, name="主账户")
    aid2 = await _make_account(client, name="转入账户")
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")
    assert item["status"] == "pending"

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim-transfer",
        json={"to_account_id": aid2},
    )
    assert resp.status_code == 200

    body = await _items(client, batch_id, status="claimed")
    assert body["total"] == 1
    claimed = body["items"][0]
    assert claimed["id"] == item["id"]
    assert claimed["status"] == "claimed"
    assert claimed["transaction_id"] is not None

    txn_resp = await client.get(f"/api/transactions/{claimed['transaction_id']}")
    assert txn_resp.status_code == 200
    txn = txn_resp.json()
    assert txn["type"] == "transfer"
    assert txn["category_id"] is None
    assert txn["amount_cents"] == item["amount_cents"]


@pytest.mark.asyncio
async def test_claim_transfer_to_same_account_400_deep2(client):
    aid = await _make_account(client, name="自身账户")
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim-transfer",
        json={"to_account_id": aid},
    )
    assert resp.status_code == 400

    body = await _items(client, batch_id, status="pending")
    assert any(it["id"] == item["id"] for it in body["items"])


@pytest.mark.asyncio
async def test_claim_transfer_to_nonexistent_account_404_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim-transfer",
        json={"to_account_id": 999999},
    )
    assert resp.status_code == 404

    body = await _items(client, batch_id, status="pending")
    assert any(it["id"] == item["id"] for it in body["items"])


@pytest.mark.asyncio
async def test_claim_transfer_nonexistent_item_404_deep2(client):
    aid = await _make_account(client)
    aid2 = await _make_account(client, name="另一账户")

    resp = await client.post(
        "/api/statements/items/999999/claim-transfer",
        json={"to_account_id": aid2},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_skip_success_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")

    resp = await client.post(f"/api/statements/items/{item['id']}/skip")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    body = await _items(client, batch_id, status="skipped")
    assert body["total"] == 1
    assert body["items"][0]["id"] == item["id"]
    assert body["items"][0]["status"] == "skipped"

    pending = await _items(client, batch_id, status="pending")
    assert pending["total"] == 1
    assert all(it["id"] != item["id"] for it in pending["items"])


@pytest.mark.asyncio
async def test_skip_twice_returns_400_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    item = await _get_item_by_direction(client, batch_id, "out")

    first = await client.post(f"/api/statements/items/{item['id']}/skip")
    assert first.status_code == 200

    second = await client.post(f"/api/statements/items/{item['id']}/skip")
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_skip_nonexistent_item_404_deep2(client):
    resp = await client.post("/api/statements/items/999999/skip")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_batch_cascades_items_and_get_404_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)

    before = await _items(client, batch_id)
    assert before["total"] == 2

    del_resp = await client.delete(f"/api/statements/{batch_id}")
    assert del_resp.status_code == 200

    get_batch = await client.get(f"/api/statements/{batch_id}")
    assert get_batch.status_code == 404

    items_after = await client.get(f"/api/statements/{batch_id}/items")
    assert items_after.status_code == 404


@pytest.mark.asyncio
async def test_get_single_batch_ok_deep2(client):
    aid = await _make_account(client)
    batch_id, parsed = await _upload(client, aid)
    assert parsed == 2

    resp = await client.get(f"/api/statements/{batch_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == batch_id


@pytest.mark.asyncio
async def test_get_single_batch_not_found_deep2(client):
    resp = await client.get("/api/statements/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_claim_out_item_with_income_category_mismatch_400_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "income", "工资")

    item = await _get_item_by_direction(client, batch_id, "out")

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert resp.status_code == 400

    body = await _items(client, batch_id, status="pending")
    assert any(it["id"] == item["id"] for it in body["items"])


@pytest.mark.asyncio
async def test_claim_in_item_with_income_category_success_deep2(client):
    aid = await _make_account(client)
    batch_id, _ = await _upload(client, aid)
    await _confirm(client, batch_id)
    cid = await _find_category(client, "income", "工资")

    item = await _get_item_by_direction(client, batch_id, "in")

    resp = await client.post(
        f"/api/statements/items/{item['id']}/claim",
        json={"category_id": cid, "save_rule": False},
    )
    assert resp.status_code == 200

    body = await _items(client, batch_id, status="claimed")
    assert body["total"] == 1
    claimed = body["items"][0]
    assert claimed["id"] == item["id"]
    assert claimed["status"] == "claimed"

    txn_resp = await client.get(f"/api/transactions/{claimed['transaction_id']}")
    assert txn_resp.status_code == 200
    txn = txn_resp.json()
    assert txn["category_id"] == cid
    assert txn["amount_cents"] == item["amount_cents"]