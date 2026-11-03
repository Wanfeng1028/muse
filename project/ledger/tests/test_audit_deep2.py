"""账本审计端点（GET /api/audit）深度边界用例第二辑。

覆盖 audit_ledger 的真实语义：未知类型、账户悬空、悬空转出/缺转入账户的恒等式数学、
自转的收支相抵、问题排序、totals 精确值、混合计数、warning 不影响 ok、
分类悬空、单交易多问题叠加、空交易基线。脏数据一律绕过 API 直插库。
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


async def _raw_insert_account(**fields):
    now = _now()
    defaults = {
        "name": "raw",
        "type": "cash",
        "currency": "CNY",
        "opening_balance_cents": 0,
        "note": "",
        "is_archived": False,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(fields)
    async with get_session_factory()() as s:
        acc = Account(**defaults)
        s.add(acc)
        await s.commit()
        await s.refresh(acc)
        return acc.id


async def _audit(client) -> dict:
    resp = await client.get("/api/audit")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _issues_by_code(payload: dict, code: str) -> list[dict]:
    return [i for i in payload["issues"] if i["code"] == code]


async def test_unknown_type_is_error(client):
    """未知交易类型应产出 error 级 UNKNOWN_TYPE，并使 ok 为 False。

    交易指向真实账户，排除 ACCOUNT_NOT_FOUND 干扰，验证审计只针对类型判定。
    """
    acc = await _make_account(client, "A")
    txn_id = await _raw_insert_transaction(
        type="weird_type", account_id=acc["id"], amount_cents=700
    )
    payload = await _audit(client)

    hits = _issues_by_code(payload, "UNKNOWN_TYPE")
    assert len(hits) == 1, payload
    assert hits[0]["severity"] == "error"
    assert hits[0]["transaction_id"] == txn_id
    assert payload["ok"] is False
    assert payload["error_count"] >= 1


async def test_account_not_found_reports_txn_id(client):
    """交易指向不存在的账户时，ACCOUNT_NOT_FOUND 必须带出该交易 id。

    用 income 交易且分类有效，隔离出唯一问题源。
    """
    cat_id = await _pick_category(client, "income")
    txn_id = await _raw_insert_transaction(
        type="income",
        account_id=999999,
        category_id=cat_id,
        amount_cents=1000,
    )
    payload = await _audit(client)

    hits = _issues_by_code(payload, "ACCOUNT_NOT_FOUND")
    assert len(hits) == 1, payload
    assert hits[0]["severity"] == "error"
    assert hits[0]["transaction_id"] == txn_id
    assert payload["ok"] is False


async def test_dangling_transfer_out_identity_diff(client):
    """悬空转入账户的转出仍计入转出和，转入丢失，diff 应为 -amount。

    转出 4000 记入 tout_sum，tin_sum 未增加，故 balance - expected = -4000。
    """
    acc = await _make_account(client, "A", opening=0)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=acc["id"],
        to_account_id=999999,
        amount_cents=4000,
    )
    payload = await _audit(client)

    assert payload["totals"]["transfer_out_sum_cents"] == 4000
    assert payload["totals"]["transfer_in_sum_cents"] == 0
    assert payload["identity"]["diff_cents"] == -4000
    assert payload["identity"]["holds"] is False
    hits = _issues_by_code(payload, "IDENTITY_BROKEN")
    assert len(hits) == 1, payload
    assert hits[0]["severity"] == "error"
    assert hits[0]["transaction_id"] is None
    to_hits = _issues_by_code(payload, "TRANSFER_TO_ACCOUNT_NOT_FOUND")
    assert [h["transaction_id"] for h in to_hits] == [txn_id]


async def test_missing_to_account_identity_diff(client):
    """to_account_id=None 的转账：转出计入、转入丢失，diff 应为 -amount。

    同时必须触发 TRANSFER_MISSING_TO error。
    """
    acc = await _make_account(client, "A", opening=0)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=acc["id"],
        to_account_id=None,
        amount_cents=2500,
    )
    payload = await _audit(client)

    assert payload["totals"]["transfer_out_sum_cents"] == 2500
    assert payload["totals"]["transfer_in_sum_cents"] == 0
    assert payload["identity"]["diff_cents"] == -2500
    assert payload["identity"]["holds"] is False
    missing = _issues_by_code(payload, "TRANSFER_MISSING_TO")
    assert [h["transaction_id"] for h in missing] == [txn_id]
    assert missing[0]["severity"] == "error"


async def test_self_transfer_identity_holds(client):
    """自转：转出与转入记同一账户，恒等式两侧同增同减，diff 为 0。

    但 TRANSFER_SELF 仍为 error，故 ok 为 False 而 holds 为 True。
    """
    acc = await _make_account(client, "A", opening=0)
    txn_id = await _raw_insert_transaction(
        type="transfer",
        account_id=acc["id"],
        to_account_id=acc["id"],
        amount_cents=3000,
    )
    payload = await _audit(client)

    self_hits = _issues_by_code(payload, "TRANSFER_SELF")
    assert [h["transaction_id"] for h in self_hits] == [txn_id]
    assert self_hits[0]["severity"] == "error"
    assert payload["totals"]["transfer_out_sum_cents"] == 3000
    assert payload["totals"]["transfer_in_sum_cents"] == 3000
    assert payload["identity"]["diff_cents"] == 0
    assert payload["identity"]["holds"] is True
    assert payload["ok"] is False


async def test_issue_ordering_errors_first_then_none_txn(client):
    """issues 排序：error 全部在 warning 前；error 内 transaction_id 升序，
    transaction_id 为 None 的 IDENTITY_BROKEN 排在最前（排序键 -1）。
    """
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0, currency="USD")

    t_warn = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=b["id"],
        amount_cents=1000,
    )
    t_err1 = await _raw_insert_transaction(
        type="weird_type", account_id=a["id"], amount_cents=100
    )
    t_err2 = await _raw_insert_transaction(
        type="weird_type", account_id=a["id"], amount_cents=200
    )
    # 制造恒等式破裂：悬空转入
    t_dangle = await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=999999,
        amount_cents=500,
    )

    payload = await _audit(client)

    severities = [i["severity"] for i in payload["issues"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "error" else 1)
    error_ids = [
        i["transaction_id"] for i in payload["issues"] if i["severity"] == "error"
    ]
    assert error_ids[0] is None
    assert error_ids == sorted(error_ids, key=lambda x: -1 if x is None else x)
    # 至少包含我们构造的三个 error 交易与 1 个 warning
    assert t_err1 in error_ids and t_err2 in error_ids and t_dangle in error_ids
    warn_ids = [
        i["transaction_id"] for i in payload["issues"] if i["severity"] == "warning"
    ]
    assert t_warn in warn_ids


async def test_totals_exact_values_and_identity(client):
    """正常四类交易下 totals 与 identity 必须给出精确整数。

    期初 10000 + 20000，收入 5000，支出 1200，转账 3000：expected = 33800。
    """
    a = await _make_account(client, "A", opening=10000)
    b = await _make_account(client, "B", opening=20000)
    inc_cat = await _pick_category(client, "income")
    exp_cat = await _pick_category(client, "expense")

    await _raw_insert_transaction(
        type="income", account_id=a["id"], category_id=inc_cat, amount_cents=5000
    )
    await _raw_insert_transaction(
        type="expense", account_id=a["id"], category_id=exp_cat, amount_cents=1200
    )
    await _raw_insert_transaction(
        type="transfer",
        account_id=a["id"],
        to_account_id=b["id"],
        amount_cents=3000,
    )

    payload = await _audit(client)

    totals = payload["totals"]
    assert totals["opening_sum_cents"] == 30000
    assert totals["income_sum_cents"] == 5000
    assert totals["expense_sum_cents"] == 1200
    assert totals["transfer_out_sum_cents"] == 3000
    assert totals["transfer_in_sum_cents"] == 3000
    assert payload["identity"]["holds"] is True
    assert payload["identity"]["balance_sum_cents"] == 33800
    assert payload["identity"]["expected_cents"] == 33800
    assert payload["identity"]["diff_cents"] == 0


async def test_mixed_counts_errors_and_warnings(client):
    """混合场景：悬空转入 + 2 笔跨币种转账时计数精确。

    悬空转入产出 2 个 error issue（TRANSFER_TO_ACCOUNT_NOT_FOUND 与
    IDENTITY_BROKEN），跨币种各 1 个 warning；error_count 与 warning_count
    必须与实际 severity 分布一致，ok 为 False。
    """
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0, currency="USD")
    c = await _make_account(client, "C", opening=0, currency="USD")

    # 两个跨币种 warning
    await _raw_insert_transaction(
        type="transfer", account_id=a["id"], to_account_id=b["id"], amount_cents=100
    )
    await _raw_insert_transaction(
        type="transfer", account_id=a["id"], to_account_id=c["id"], amount_cents=200
    )
    # 一个悬空转入 error
    await _raw_insert_transaction(
        type="transfer", account_id=a["id"], to_account_id=999999, amount_cents=300
    )

    payload = await _audit(client)

    assert payload["error_count"] == 2, payload
    assert payload["warning_count"] == 2, payload
    assert payload["ok"] is False


async def test_warning_does_not_break_ok(client):
    """仅跨币种转账（无 error）时 ok 应为 True，warning 计数为 1。

    跨币种仅是告警语义，恒等式仍然 holds。
    """
    a = await _make_account(client, "A", opening=0)
    b = await _make_account(client, "B", opening=0, currency="USD")
    await _raw_insert_transaction(
        type="transfer", account_id=a["id"], to_account_id=b["id"], amount_cents=800
    )

    payload = await _audit(client)

    assert payload["warning_count"] == 1, payload
    assert payload["error_count"] == 0, payload
    assert payload["ok"] is True
    cross = _issues_by_code(payload, "TRANSFER_CROSS_CURRENCY")
    assert len(cross) == 1
    assert cross[0]["severity"] == "warning"
    assert payload["identity"]["holds"] is True


async def test_category_not_found_reported(client):
    """收入交易的 category_id 悬空时应产出 CATEGORY_NOT_FOUND error。

    account 有效，唯一问题源为分类悬空。
    """
    acc = await _make_account(client, "A", opening=0)
    txn_id = await _raw_insert_transaction(
        type="income",
        account_id=acc["id"],
        category_id=999999,
        amount_cents=1000,
    )
    payload = await _audit(client)

    hits = _issues_by_code(payload, "CATEGORY_NOT_FOUND")
    assert len(hits) == 1, payload
    assert hits[0]["severity"] == "error"
    assert hits[0]["transaction_id"] == txn_id
    assert payload["ok"] is False


async def test_single_txn_multiple_issues_same_id(client):
    """同一交易同时未知类型且账户悬空：两个 error 携带相同 transaction_id。"""
    txn_id = await _raw_insert_transaction(
        type="weird", account_id=999999, amount_cents=100
    )
    payload = await _audit(client)

    unknown = _issues_by_code(payload, "UNKNOWN_TYPE")
    missing = _issues_by_code(payload, "ACCOUNT_NOT_FOUND")
    assert [h["transaction_id"] for h in unknown] == [txn_id]
    assert [h["transaction_id"] for h in missing] == [txn_id]
    assert unknown[0]["severity"] == "error"
    assert missing[0]["severity"] == "error"
    assert payload["ok"] is False


async def test_empty_ledger_with_seed_accounts(client):
    """仅有种子账户、无任何交易时：transactions==0、issues 为空、ok 为 True。

    恒等式退化为 Σ期初 == Σ期初，holds 必须为 True。
    """
    a = await _make_account(client, "A", opening=1000)
    b = await _make_account(client, "B", opening=2500)
    assert a["id"] != b["id"]

    payload = await _audit(client)

    assert payload["totals"]["transactions"] == 0
    assert payload["totals"]["accounts"] == 2
    assert payload["issues"] == []
    assert payload["ok"] is True
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0
    assert payload["identity"]["holds"] is True
    assert payload["identity"]["balance_sum_cents"] == 3500
    assert payload["identity"]["expected_cents"] == 3500
    assert payload["identity"]["diff_cents"] == 0
