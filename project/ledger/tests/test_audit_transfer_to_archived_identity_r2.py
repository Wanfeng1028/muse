from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text

from ledger.database import get_session_factory
from ledger.models import Account, Transaction
from ledger.seed import ensure_seed


@pytest_asyncio.fixture(scope="function")
async def session(app):
    factory = get_session_factory()
    async with factory() as s:
        for t in (
            "ocr_reviews", "statement_items", "statement_batches", "match_rules",
            "merchant_aliases", "statement_templates", "report_schemes", "currencies",
            "transactions", "budgets", "recurring", "categories", "accounts",
        ):
            await s.execute(text(f"DELETE FROM {t}"))
        await s.commit()
        await ensure_seed(s)
        await s.commit()
        yield s


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


async def test_transfer_to_archived_emits_warning(client, session):
    a = Account(
        name="A", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=0,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    b = Account(
        name="B", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=1,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add_all([a, b])
    await session.commit()
    tx = Transaction(
        type="transfer", account_id=a.id, to_account_id=b.id, category_id=None,
        amount_cents=8000, occurred_on="2026-01-15", note=None, currency="CNY",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add(tx)
    await session.commit()

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()

    archived_issues = [i for i in body["issues"] if i["code"] == "TRANSFER_TO_ARCHIVED"]
    assert len(archived_issues) == 1
    assert archived_issues[0]["severity"] == "warning"
    assert archived_issues[0]["transaction_id"] == tx.id
    assert "B" in archived_issues[0]["detail"]
    assert "已归档" in archived_issues[0]["detail"]


async def test_transfer_to_archived_identity_holds(client, session):
    a = Account(
        name="A", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=0,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    b = Account(
        name="B", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=1,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add_all([a, b])
    await session.commit()
    tx = Transaction(
        type="transfer", account_id=a.id, to_account_id=b.id, category_id=None,
        amount_cents=8000, occurred_on="2026-01-15", note=None, currency="CNY",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add(tx)
    await session.commit()

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()

    identity = body["identity"]
    assert identity["holds"] is True
    assert identity["diff_cents"] == 0
    assert identity["balance_sum_cents"] == 0
    assert identity["expected_cents"] == 0

    totals = body["totals"]
    assert totals["transfer_out_sum_cents"] == 8000
    assert totals["transfer_in_sum_cents"] == 8000


async def test_transfer_to_archived_ok_true_only_warning(client, session):
    a = Account(
        name="A", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=0,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    b = Account(
        name="B", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=1,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add_all([a, b])
    await session.commit()
    tx = Transaction(
        type="transfer", account_id=a.id, to_account_id=b.id, category_id=None,
        amount_cents=8000, occurred_on="2026-01-15", note=None, currency="CNY",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add(tx)
    await session.commit()

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()

    assert body["ok"] is True
    assert body["error_count"] == 0
    assert body["warning_count"] == 1
    codes = [i["code"] for i in body["issues"]]
    assert codes == ["TRANSFER_TO_ARCHIVED"]


async def test_transfer_to_active_account_no_archived_warning(client, session):
    a = Account(
        name="A", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=0,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    b = Account(
        name="B", type="cash", currency="CNY", opening_balance_cents=0,
        note=None, is_archived=0,
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add_all([a, b])
    await session.commit()
    tx = Transaction(
        type="transfer", account_id=a.id, to_account_id=b.id, category_id=None,
        amount_cents=8000, occurred_on="2026-01-15", note=None, currency="CNY",
        created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    session.add(tx)
    await session.commit()

    resp = await client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()

    codes = [i["code"] for i in body["issues"]]
    assert "TRANSFER_TO_ARCHIVED" not in codes
    assert body["ok"] is True
    assert body["error_count"] == 0
    assert body["warning_count"] == 0
    assert body["issues"] == []
    assert body["identity"]["holds"] is True
    assert body["totals"]["transfer_out_sum_cents"] == 8000
    assert body["totals"]["transfer_in_sum_cents"] == 8000
