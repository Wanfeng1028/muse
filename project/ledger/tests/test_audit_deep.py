"""账本平衡审计深度测试。

约定：asyncio_mode=auto，client fixture 每用例清表重播种。
脏数据通过 get_session_factory 直接插库，绕过 API 校验。
"""

from datetime import UTC, datetime

from ledger.database import get_session_factory
from ledger.models import Account, Transaction


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _make_account(client, name, opening=0, currency=None):
    payload = {"name": name, "type": "cash", "opening_balance_cents": opening}
    if currency is not None:
        payload["currency"] = currency
    resp = await client.post("/api/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _pick_category(client, kind):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["kind"] == kind:
            return c["id"]
    raise AssertionError(f"no category of kind={kind}")


async def _raw_insert_transaction(**fields):
    now = _now()
    defaults = {
        "type": "transfer",
        "account_id": None,
        "to_account_id": None,
        "category_id": None,
        "amount_cents": 0,
        "occurred_on": "2026-10-19",
        "note": "",
        "currency": "CNY",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(fields)
    async with get_session_factory()() as s:
        txn = Transaction(**defaults)
        s.add(txn)
        await s.commit()
        await s.refresh(txn)
        return txn.id


async def _raw_insert_account(name, opening=0, currency="CNY", is_archived=0):
    now = _now()
    async with get_session_factory()() as s:
        acc = Account(
            name=name,
            type="cash",
            currency=currency,
            opening_balance_cents=opening,
            note="",
            is_archived=is_archived,
            created_at=now,
            updated_at=now,
        )
        s.add(acc)
        await s.commit()
        await s.refresh(acc)
        return acc.id


# T1 ------------------------------------------------------------------------
async def test_t1_clean_ledger(client):
    await _make_account(client, "Cash", opening=5000)
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["issues"] == []
    assert body["identity"]["holds"] is True
    assert body["identity"]["diff_cents"] == 0


# T2 ------------------------------------------------------------------------
async def test_t2_normal_transfer_identity(client):
    a = await _make_account(client, "A", opening=10000)
    b = await _make_account(client, "B", opening=0)

    r1 = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": a["id"],
            "to_account_id": b["id"],
            "amount_cents": 3000,
            "occurred_on": "2026-10-19",
            "currency": "CNY",
        },
    )
    assert r1.status_code == 201, r1.text

    cat_id = await _pick_category(client, "expense")
    r2 = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": a["id"],
            "category_id": cat_id,
            "amount_cents": 2000,
            "occurred_on": "2026-10-19",
            "currency": "CNY",
        },
    )
    assert r2.status_code == 201, r2.text

    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    totals = body["totals"]
    assert totals["transfer_out_sum_cents"] == 3000
    assert totals["transfer_in_sum_cents"] == 3000
    ident = body["identity"]
    assert ident["balance_sum_cents"] == 8000
    assert ident["holds"] is True


# T3 ------------------------------------------------------------------------
async def test_t3_transfer_to_account_dangling(client):
    a = await _make_account(client, "A", opening=10000)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=999999,
        amount_cents=4000,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    codes = [i["code"] for i in body["issues"]]
    assert "TRANSFER_TO_ACCOUNT_NOT_FOUND" in codes
    matched = [i for i in body["issues"] if i["code"] == "TRANSFER_TO_ACCOUNT_NOT_FOUND"]
    assert matched[0]["transaction_id"] == txn_id
    assert body["identity"]["holds"] is False
    assert body["identity"]["diff_cents"] == -4000


# T4 ------------------------------------------------------------------------
async def test_t4_transfer_missing_to(client):
    a = await _make_account(client, "A", opening=1000)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=None,
        amount_cents=500,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    matched = [i for i in body["issues"] if i["code"] == "TRANSFER_MISSING_TO"]
    assert matched and matched[0]["transaction_id"] == txn_id


# T5 ------------------------------------------------------------------------
async def test_t5_transfer_self(client):
    a = await _make_account(client, "A", opening=1000)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=a["id"],
        amount_cents=300,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    matched = [i for i in body["issues"] if i["code"] == "TRANSFER_SELF"]
    assert matched and matched[0]["transaction_id"] == txn_id


# T6 ------------------------------------------------------------------------
async def test_t6_income_missing_category(client):
    a = await _make_account(client, "A", opening=0)
    txn_id = await _raw_insert_transaction(
        type="income",
        account_id=a["id"],
        category_id=None,
        amount_cents=1000,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    matched = [i for i in body["issues"] if i["code"] == "TRANSACTION_MISSING_CATEGORY"]
    assert matched and matched[0]["transaction_id"] == txn_id


# T7 ------------------------------------------------------------------------
async def test_t7_category_kind_mismatch(client):
    a = await _make_account(client, "A", opening=0)
    expense_cat = await _pick_category(client, "expense")
    txn_id = await _raw_insert_transaction(
        type="income",
        account_id=a["id"],
        category_id=expense_cat,
        amount_cents=700,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    matched = [i for i in body["issues"] if i["code"] == "CATEGORY_KIND_MISMATCH"]
    assert matched and matched[0]["transaction_id"] == txn_id


# T8 ------------------------------------------------------------------------
async def test_t8_cross_currency_transfer_warning(client):
    # 先尝试通过 API 建带 currency 的账户；若 400 则退化为直接插库。
    resp_cny = await client.post(
        "/api/accounts",
        json={"name": "CNY-A", "type": "cash", "opening_balance_cents": 10000, "currency": "CNY"},
    )
    if resp_cny.status_code == 201:
        cny = resp_cny.json()
    else:
        cny_id = await _raw_insert_account("CNY-A", opening=10000, currency="CNY")
        cny = {"id": cny_id}

    resp_usd = await client.post(
        "/api/accounts",
        json={"name": "USD-B", "type": "cash", "opening_balance_cents": 0, "currency": "USD"},
    )
    if resp_usd.status_code == 201:
        usd = resp_usd.json()
    else:
        usd_id = await _raw_insert_account("USD-B", opening=0, currency="USD")
        usd = {"id": usd_id}

    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=cny["id"],
        to_account_id=usd["id"],
        amount_cents=2000,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # warning 不影响 ok
    assert body["ok"] is True
    matched = [i for i in body["issues"] if i["code"] == "TRANSFER_CROSS_CURRENCY"]
    assert matched and matched[0]["transaction_id"] == txn_id
    assert matched[0]["severity"] == "warning"


# T9 ------------------------------------------------------------------------
async def test_t9_transfer_to_archived_warning(client):
    a = await _make_account(client, "A", opening=10000)
    b = await _make_account(client, "B", opening=0)

    # 尝试通过 API 归档；若接口不支持则直接改库。
    # PUT /api/accounts 不支持 is_archived 字段（会静默忽略），直接改库归档。
    async with get_session_factory()() as s:
        acc = await s.get(Account, b["id"])
        acc.is_archived = 1
        await s.commit()

    # 走 API 的转账会被拒（"转入账户已归档"），所以直接插。
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=b["id"],
        amount_cents=1500,
    )
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    matched = [i for i in body["issues"] if i["code"] == "TRANSFER_TO_ARCHIVED"]
    assert matched and matched[0]["transaction_id"] == txn_id
    assert matched[0]["severity"] == "warning"
    assert body["identity"]["holds"] is True
