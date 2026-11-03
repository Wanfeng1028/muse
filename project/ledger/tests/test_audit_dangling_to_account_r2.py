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


async def test_dangling_to_account_produces_transfer_to_account_not_found(client, session):
    acct = Account(
        name="A",
        type="cash",
        currency="CNY",
        opening_balance_cents=0,
        note="",
        is_archived=False,
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)

    txn = Transaction(
        type="transfer",
        account_id=acct.id,
        to_account_id=99999999,
        category_id=None,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="",
        currency="CNY",
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)

    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    dangling = [i for i in body["issues"] if i["code"] == "TRANSFER_TO_ACCOUNT_NOT_FOUND"]
    assert len(dangling) == 1
    assert dangling[0]["severity"] == "error"
    assert dangling[0]["transaction_id"] == txn.id
    assert dangling[0]["detail"] == f"转入账户 {99999999} 不存在"


async def test_dangling_to_account_breaks_identity(client, session):
    acct = Account(
        name="A",
        type="cash",
        currency="CNY",
        opening_balance_cents=0,
        note="",
        is_archived=False,
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)

    txn = Transaction(
        type="transfer",
        account_id=acct.id,
        to_account_id=99999999,
        category_id=None,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="",
        currency="CNY",
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)

    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    broken = [i for i in body["issues"] if i["code"] == "IDENTITY_BROKEN"]
    assert len(broken) == 1
    assert broken[0]["severity"] == "error"
    assert body["identity"]["holds"] is False
    assert body["identity"]["diff_cents"] == -5000
    assert body["identity"]["balance_sum_cents"] == -5000
    assert body["identity"]["expected_cents"] == 0


async def test_dangling_to_account_totals_transfer_out_only(client, session):
    acct = Account(
        name="A",
        type="cash",
        currency="CNY",
        opening_balance_cents=0,
        note="",
        is_archived=False,
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)

    txn = Transaction(
        type="transfer",
        account_id=acct.id,
        to_account_id=99999999,
        category_id=None,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="",
        currency="CNY",
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)

    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["totals"]["transfer_out_sum_cents"] == 5000
    assert body["totals"]["transfer_in_sum_cents"] == 0
    assert body["totals"]["accounts"] == 1
    assert body["totals"]["transactions"] == 1
    assert body["totals"]["opening_sum_cents"] == 0
    assert body["totals"]["income_sum_cents"] == 0
    assert body["totals"]["expense_sum_cents"] == 0


async def test_dangling_to_account_ok_false_and_error_count(client, session):
    acct = Account(
        name="A",
        type="cash",
        currency="CNY",
        opening_balance_cents=0,
        note="",
        is_archived=False,
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(acct)
    await session.commit()
    await session.refresh(acct)

    txn = Transaction(
        type="transfer",
        account_id=acct.id,
        to_account_id=99999999,
        category_id=None,
        amount_cents=5000,
        occurred_on="2026-01-15",
        note="",
        currency="CNY",
        created_at="2026-01-15T00:00:00",
        updated_at="2026-01-15T00:00:00",
    )
    session.add(txn)
    await session.commit()
    await session.refresh(txn)

    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["ok"] is False
    assert body["error_count"] >= 2
    assert body["warning_count"] == 0
    codes = [i["code"] for i in body["issues"]]
    assert "TRANSFER_TO_ACCOUNT_NOT_FOUND" in codes
    assert "IDENTITY_BROKEN" in codes
    severities = [i["severity"] for i in body["issues"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "error" else 1)
