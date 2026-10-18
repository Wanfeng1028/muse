from __future__ import annotations

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


async def _make_account(client) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": "现金钱包", "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_food_category_id(client) -> int:
    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    items = resp.json()
    for cat in items:
        if cat["name"] == "餐饮":
            return cat["id"]
    raise AssertionError("未找到餐饮分类")


async def _upload_ocr(client) -> int:
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "review_id" in body
    return body["review_id"]


@pytest.mark.asyncio
async def test_upload_two_list_order_deep2(client):
    first_id = await _upload_ocr(client)
    second_id = await _upload_ocr(client)
    assert second_id > first_id

    resp = await client.get("/api/bills/review")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert [it["id"] for it in items] == [second_id, first_id]


@pytest.mark.asyncio
async def test_review_image_bytes_and_content_type_deep2(client):
    review_id = await _upload_ocr(client)

    resp = await client.get(f"/api/bills/review/{review_id}/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.content == PNG_BYTES


@pytest.mark.asyncio
async def test_review_image_missing_returns_404_deep2(client):
    resp = await client.get("/api/bills/review/999999/image")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_removes_from_pending_list_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["review_id"] == review_id

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200
    ids = [it["id"] for it in listing.json()["items"]]
    assert review_id not in ids


@pytest.mark.asyncio
async def test_confirm_creates_expense_transaction_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-02",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200
    tx_id = confirm.json()["transaction_id"]
    assert isinstance(tx_id, int)

    tx_resp = await client.get(f"/api/transactions/{tx_id}")
    assert tx_resp.status_code == 200
    tx = tx_resp.json()
    assert tx["amount_cents"] == 6800
    assert tx["type"] == "expense"
    assert tx["note"] == "拍照记账：星巴克臻选"


@pytest.mark.asyncio
async def test_confirm_zero_amount_returns_422_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 0,
            "occurred_on": "2024-05-03",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_empty_occurred_on_returns_422_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reject_then_list_empty_deep2(client):
    review_id = await _upload_ocr(client)

    resp = await client.post(f"/api/bills/review/{review_id}/reject")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == review_id
    assert body["status"] == "rejected"

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200
    assert listing.json()["items"] == []


@pytest.mark.asyncio
async def test_reject_confirmed_returns_409_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-04",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200

    resp = await client.post(f"/api/bills/review/{review_id}/reject")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reject_missing_returns_404_deep2(client):
    resp = await client.post("/api/bills/review/999999/reject")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_rejected_returns_409_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)

    reject = await client.post(f"/api/bills/review/{review_id}/reject")
    assert reject.status_code == 200

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-05",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reject_one_confirm_other_status_isolation_deep2(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)

    rejected_id = await _upload_ocr(client)
    confirmed_id = await _upload_ocr(client)
    assert confirmed_id > rejected_id

    reject = await client.post(f"/api/bills/review/{rejected_id}/reject")
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    confirm = await client.post(
        f"/api/bills/review/{confirmed_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-06",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["review_id"] == confirmed_id

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200
    assert listing.json()["items"] == []

    second_reject = await client.post(f"/api/bills/review/{rejected_id}/reject")
    assert second_reject.status_code == 409

    second_confirm = await client.post(
        f"/api/bills/review/{confirmed_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 6800,
            "occurred_on": "2024-05-06",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert second_confirm.status_code == 409