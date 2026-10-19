from __future__ import annotations

import pytest
from sqlalchemy import select

from ledger.database import get_session_factory
from ledger.models import OcrReview

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


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


async def _make_review(status: str = "pending", merchant: str = "星巴克臻选") -> int:
    factory = get_session_factory()
    async with factory() as session:
        row = OcrReview(
            image=PNG_BYTES,
            content_type="image/png",
            filename="receipt.png",
            merchant=merchant,
            amount_cents=6800,
            occurred_on="2026-10-16",
            raw_text="",
            provider="mock",
            mock=1,
            category_id=None,
            field_confidence="{}",
            status=status,
            created_at="2026-10-16T00:00:00+00:00",
            updated_at="2026-10-16T00:00:00+00:00",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return int(row.id)


async def _get_review(review_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(OcrReview).where(OcrReview.id == review_id)
        row = (await session.execute(stmt)).scalar_one()
        return {
            "id": row.id,
            "status": row.status,
            "transaction_id": row.transaction_id,
        }


def _confirm_item(review_id: int, account_id: int, category_id: int) -> dict:
    return {
        "review_id": review_id,
        "merchant": "星巴克",
        "amount_cents": 6800,
        "occurred_on": "2026-10-16",
        "category_id": category_id,
        "account_id": account_id,
        "note": "午餐",
    }


@pytest.mark.asyncio
async def test_batch_invalid_action(client):
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "nope", "items": [1]},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_batch_empty_items(client):
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": []},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_batch_reject_all_success(client):
    rid1 = await _make_review()
    rid2 = await _make_review()
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": [rid1, rid2]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["failed"] == []
    succeeded = body["succeeded"]
    assert len(succeeded) == 2
    ids = sorted(item["review_id"] for item in succeeded)
    assert ids == sorted([rid1, rid2])
    for item in succeeded:
        assert item["status"] == "rejected"
    row1 = await _get_review(rid1)
    row2 = await _get_review(rid2)
    assert row1["status"] == "rejected"
    assert row2["status"] == "rejected"


@pytest.mark.asyncio
async def test_batch_reject_partial_already_processed(client):
    rid_pending = await _make_review()
    rid_done = await _make_review(status="confirmed")
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": [rid_pending, rid_done]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["succeeded"]) == 1
    assert body["succeeded"][0]["review_id"] == rid_pending
    assert body["succeeded"][0]["status"] == "rejected"
    assert len(body["failed"]) == 1
    assert body["failed"][0]["review_id"] == rid_done
    assert body["failed"][0]["error"]
    row = await _get_review(rid_pending)
    assert row["status"] == "rejected"


@pytest.mark.asyncio
async def test_batch_reject_missing_id(client):
    rid = await _make_review()
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": [rid, 999999]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["succeeded"]) == 1
    assert body["succeeded"][0]["review_id"] == rid
    assert len(body["failed"]) == 1
    assert body["failed"][0]["review_id"] == 999999
    assert body["failed"][0]["error"]


@pytest.mark.asyncio
async def test_batch_confirm_all_success(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid1 = await _make_review()
    rid2 = await _make_review()
    items = [
        _confirm_item(rid1, account_id, category_id),
        _confirm_item(rid2, account_id, category_id),
    ]
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["failed"] == []
    assert len(body["succeeded"]) == 2
    txn_ids = [item["transaction_id"] for item in body["succeeded"]]
    assert all(isinstance(tid, int) for tid in txn_ids)
    assert len(set(txn_ids)) == 2
    for item in body["succeeded"]:
        assert item["review_id"] in (rid1, rid2)
    row1 = await _get_review(rid1)
    row2 = await _get_review(rid2)
    assert row1["status"] == "confirmed"
    assert row2["status"] == "confirmed"
    assert row1["transaction_id"] in txn_ids
    assert row2["transaction_id"] in txn_ids


@pytest.mark.asyncio
async def test_batch_confirm_one_invalid_amount(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid_ok = await _make_review()
    rid_bad = await _make_review()
    bad_item = _confirm_item(rid_bad, account_id, category_id)
    bad_item["amount_cents"] = 0
    items = [
        _confirm_item(rid_ok, account_id, category_id),
        bad_item,
    ]
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["succeeded"]) == 1
    assert body["succeeded"][0]["review_id"] == rid_ok
    assert isinstance(body["succeeded"][0]["transaction_id"], int)
    assert len(body["failed"]) == 1
    assert body["failed"][0]["review_id"] == rid_bad
    assert body["failed"][0]["error"]
    row_ok = await _get_review(rid_ok)
    row_bad = await _get_review(rid_bad)
    assert row_ok["status"] == "confirmed"
    assert row_bad["status"] == "pending"


@pytest.mark.asyncio
async def test_batch_confirm_duplicate_second_time_failed(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid = await _make_review()
    items = [_confirm_item(rid, account_id, category_id)]
    first = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["failed"] == []
    assert len(first_body["succeeded"]) == 1
    assert first_body["succeeded"][0]["review_id"] == rid

    second = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["succeeded"] == []
    assert len(second_body["failed"]) == 1
    assert second_body["failed"][0]["review_id"] == rid
    assert second_body["failed"][0]["error"] == "该记录已处理，不可重复确认"


@pytest.mark.asyncio
async def test_batch_confirm_then_single_confirm_returns_409(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid = await _make_review()
    items = [_confirm_item(rid, account_id, category_id)]
    batch = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["failed"] == []

    single = await client.post(
        f"/api/bills/review/{rid}/confirm",
        json={
            "merchant": "星巴克",
            "amount_cents": 6800,
            "occurred_on": "2026-10-16",
            "category_id": category_id,
            "account_id": account_id,
            "note": "午餐",
        },
    )
    assert single.status_code == 409, single.text
    assert single.json()["detail"] == "该记录已处理，不可重复确认"


@pytest.mark.asyncio
async def test_batch_reject_then_single_reject_returns_409(client):
    rid = await _make_review()
    batch = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": [rid]},
    )
    assert batch.status_code == 200, batch.text
    assert len(batch.json()["succeeded"]) == 1

    single = await client.post(f"/api/bills/review/{rid}/reject")
    assert single.status_code == 409, single.text
    assert single.json()["detail"] == "该记录已处理，不可重复驳回"


@pytest.mark.asyncio
async def test_batch_confirm_missing_id(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid_ok = await _make_review()
    items = [
        _confirm_item(rid_ok, account_id, category_id),
        _confirm_item(999999, account_id, category_id),
    ]
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["succeeded"]) == 1
    assert body["succeeded"][0]["review_id"] == rid_ok
    assert len(body["failed"]) == 1
    assert body["failed"][0]["review_id"] == 999999
    assert body["failed"][0]["error"]


@pytest.mark.asyncio
async def test_batch_confirm_invalid_date(client):
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    rid_ok = await _make_review()
    rid_bad = await _make_review()
    bad_item = _confirm_item(rid_bad, account_id, category_id)
    bad_item["occurred_on"] = "2026/10/16"
    items = [
        _confirm_item(rid_ok, account_id, category_id),
        bad_item,
    ]
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "confirm", "items": items},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["succeeded"]) == 1
    assert body["succeeded"][0]["review_id"] == rid_ok
    assert len(body["failed"]) == 1
    assert body["failed"][0]["review_id"] == rid_bad
    assert body["failed"][0]["error"]
    row_ok = await _get_review(rid_ok)
    row_bad = await _get_review(rid_bad)
    assert row_ok["status"] == "confirmed"
    assert row_bad["status"] == "pending"


@pytest.mark.asyncio
async def test_batch_reject_all_missing(client):
    resp = await client.post(
        "/api/bills/review/batch",
        json={"action": "reject", "items": [999998, 999999]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["succeeded"] == []
    assert len(body["failed"]) == 2
    failed_ids = sorted(item["review_id"] for item in body["failed"])
    assert failed_ids == [999998, 999999]
    for item in body["failed"]:
        assert item["error"]
