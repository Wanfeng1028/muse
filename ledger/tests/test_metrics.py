"""指标与就绪探针测试。"""

from __future__ import annotations

import re
from datetime import date

PROM_LINE = re.compile(r"^[a-z_]+(\{[^}]*\})? [0-9.eE+-]+$")


async def test_metrics_endpoint(client):
    resp = await client.get("/api/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text

    for name in (
        "ledger_statement_batches_total",
        "ledger_statement_items_total",
        "ledger_detective_pending",
        "ledger_auto_match_rate",
        "ledger_transactions_total",
        "ledger_accounts_total",
    ):
        assert name in body

    assert "ledger_detective_pending 0" in body

    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        assert PROM_LINE.match(line), line


async def test_metrics_transactions_total_after_create(client):
    # 字段名以 tests/test_transactions.py 为准：amount_cents / occurred_on
    acc_resp = await client.post(
        "/api/accounts",
        json={"name": "metrics账户", "type": "cash", "opening_balance_cents": 0},
    )
    assert acc_resp.status_code == 201, acc_resp.text
    account_id = acc_resp.json()["id"]

    cat_resp = await client.get("/api/categories", params={"kind": "expense"})
    assert cat_resp.status_code == 200
    category_id = next(c["id"] for c in cat_resp.json() if c["name"] == "餐饮")

    txn_resp = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "type": "expense",
            "amount_cents": 12050,
            "occurred_on": date.today().isoformat(),
            "note": "metrics test",
        },
    )
    assert txn_resp.status_code == 201, txn_resp.text

    resp = await client.get("/api/metrics")
    assert resp.status_code == 200
    assert "ledger_transactions_total 1" in resp.text


async def test_ready_ok(client):
    resp = await client.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json() == {"ready": True}


async def test_ready_db_down(client, monkeypatch):
    import ledger.routers.health as health_module

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(health_module, "get_session_factory", _boom)

    resp = await client.get("/api/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ready"] is False
    assert body["error"] == "RuntimeError"


async def test_health_version(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["version"] == "2.1.0"
