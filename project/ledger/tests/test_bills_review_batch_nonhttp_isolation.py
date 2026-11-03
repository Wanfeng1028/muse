from __future__ import annotations

import pytest
from sqlalchemy import select

from ledger.database import get_session_factory
from ledger.models import OcrReview
from ledger.routers import bills as bills_router

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


async def _make_account(client) -> int:
    resp = await client.post("/api/accounts", json={"name": "测试现金", "type": "cash", "opening_balance_cents": 0})
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
        return {"id": row.id, "status": row.status, "transaction_id": row.transaction_id}


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
async def test_batch_confirm_nonhttp_failure_does_not_abort_batch(client, monkeypatch):
    rid_ok1 = await _make_review()
    rid_bad = await _make_review(merchant="异常条目")
    rid_ok2 = await _make_review()
    account_id = await _make_account(client)
    category_id = await _food_category_id(client)
    orig = bills_router._confirm_one

    async def fake_confirm(session, review_id, payload):
        if review_id == rid_bad:
            raise RuntimeError("boom")
        return await orig(session, review_id, payload)

    monkeypatch.setattr(bills_router, "_confirm_one", fake_confirm)
    items = [
        _confirm_item(rid_ok1, account_id, category_id),
        _confirm_item(rid_bad, account_id, category_id),
        _confirm_item(rid_ok2, account_id, category_id),
    ]
    resp = await client.post("/api/bills/review/batch", json={"action": "confirm", "items": items})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    succeeded = body.get("succeeded", [])
    failed = body.get("failed", [])
    assert [item.get("review_id") for item in succeeded] == [rid_ok1, rid_ok2]
    assert all(isinstance(item.get("transaction_id"), int) for item in succeeded)
    assert len(failed) == 1
    assert failed[0].get("review_id") == rid_bad
    assert failed[0].get("error") == "处理失败"
    for review_id in (rid_ok1, rid_ok2):
        got = await _get_review(review_id)
        assert got["status"] == "confirmed"
        assert isinstance(got["transaction_id"], int)
    got_bad = await _get_review(rid_bad)
    assert got_bad["status"] == "pending"


@pytest.mark.asyncio
async def test_batch_reject_nonhttp_failure_does_not_abort_batch(client, monkeypatch):
    rid_ok1 = await _make_review()
    rid_bad = await _make_review(merchant="异常条目")
    rid_ok2 = await _make_review()
    orig = bills_router._reject_one

    async def fake_reject(session, review_id):
        if review_id == rid_bad:
            raise RuntimeError("boom")
        return await orig(session, review_id)

    monkeypatch.setattr(bills_router, "_reject_one", fake_reject)
    resp = await client.post("/api/bills/review/batch", json={"action": "reject", "items": [rid_ok1, rid_bad, rid_ok2]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    succeeded = body.get("succeeded", [])
    failed = body.get("failed", [])
    assert [item.get("review_id") for item in succeeded] == [rid_ok1, rid_ok2]
    assert all(item.get("status") == "rejected" for item in succeeded)
    assert len(failed) == 1
    assert failed[0].get("review_id") == rid_bad
    assert failed[0].get("error") == "处理失败"
    for review_id in (rid_ok1, rid_ok2):
        got = await _get_review(review_id)
        assert got["status"] == "rejected"
    got_bad = await _get_review(rid_bad)
    assert got_bad["status"] == "pending"
