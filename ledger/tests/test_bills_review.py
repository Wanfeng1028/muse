from __future__ import annotations

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


async def _upload(client) -> dict:
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_account(client) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": "测试现金", "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _food_category_id(client) -> int:
    resp = await client.get("/api/categories")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    items = payload["items"] if isinstance(payload, dict) else payload
    for item in items:
        if item.get("name") == "餐饮" and item.get("kind") == "expense":
            return item["id"]
    raise AssertionError("seed expense category not found")


@pytest.mark.asyncio
async def test_ocr_creates_review_row(client):
    body = await _upload(client)
    assert isinstance(body.get("review_id"), int)
    fc = body.get("field_confidence")
    assert isinstance(fc, dict)
    for key in ("merchant", "amount_cents", "occurred_on"):
        assert key in fc

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == body["review_id"]
    assert row["merchant"] == "星巴克臻选"
    assert row["amount_cents"] == 6800
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_review_list_empty(client):
    resp = await client.get("/api/bills/review")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"items": []}


@pytest.mark.asyncio
async def test_confirm_full_chain(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert confirm.status_code == 200, confirm.text
    confirm_body = confirm.json()
    assert confirm_body["review_id"] == review_id
    txn_id = confirm_body["transaction_id"]
    assert isinstance(txn_id, int)

    txn = await client.get(f"/api/transactions/{txn_id}")
    assert txn.status_code == 200, txn.text
    txn_body = txn.json()
    assert txn_body["amount_cents"] == 6800
    assert txn_body["note"] == "午餐"

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200, listing.text
    ids = [row["id"] for row in listing.json()["items"]]
    assert review_id not in ids


@pytest.mark.asyncio
async def test_confirm_default_note(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200, confirm.text
    txn_id = confirm.json()["transaction_id"]

    txn = await client.get(f"/api/transactions/{txn_id}")
    assert txn.status_code == 200, txn.text
    assert txn.json()["note"] == "拍照记账：星巴克"


@pytest.mark.asyncio
async def test_confirm_twice_409(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    payload = {
        "merchant": "星巴克",
        "amount_cents": 6800,
        "occurred_on": "2026-10-16",
        "category_id": category_id,
        "account_id": account_id,
        "note": "午餐",
    }

    first = await client.post(f"/api/bills/review/{review_id}/confirm", json=payload)
    assert first.status_code == 200, first.text

    second = await client.post(f"/api/bills/review/{review_id}/confirm", json=payload)
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_confirm_nonexistent_404(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    resp = await client.post(
        "/api/bills/review/999999/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_confirm_bad_date_422(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-13-99",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_confirm_bad_account_400(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    category_id = await _food_category_id(client)

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": 999999,
            "note": "午餐",
        },
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_reject_flow(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]

    first = await client.post(f"/api/bills/review/{review_id}/reject")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["id"] == review_id
    assert body["status"] == "rejected"

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200, listing.text
    ids = [row["id"] for row in listing.json()["items"]]
    assert review_id not in ids

    second = await client.post(f"/api/bills/review/{review_id}/reject")
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_reject_then_confirm_409(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)

    reject = await client.post(f"/api/bills/review/{review_id}/reject")
    assert reject.status_code == 200, reject.text

    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert confirm.status_code == 409, confirm.text


@pytest.mark.asyncio
async def test_reject_nonexistent_404(client):
    resp = await client.post("/api/bills/review/999999/reject")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_review_image(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]

    resp = await client.get(f"/api/bills/review/{review_id}/image")
    assert resp.status_code == 200, resp.text
    assert "image/png" in resp.headers.get("content-type", "")
    assert resp.content == PNG_BYTES


@pytest.mark.asyncio
async def test_review_image_nonexistent_404(client):
    resp = await client.get("/api/bills/review/999999/image")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_confirm_amount_zero_422(client):
    ocr = await _upload(client)
    review_id = ocr["review_id"]
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)

    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 0,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_multiple_reviews_order(client):
    first = await _upload(client)
    second = await _upload(client)
    assert second["review_id"] > first["review_id"]

    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] > items[1]["id"]
    assert items[0]["id"] == second["review_id"]
    assert items[1]["id"] == first["review_id"]
