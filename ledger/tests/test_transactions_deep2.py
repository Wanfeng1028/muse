from __future__ import annotations

import pytest


async def _make_account(client, name: str, type_: str = "cash", opening: int = 0) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": opening},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_category_id(client, kind: str) -> int:
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200
    cats = resp.json()
    assert isinstance(cats, list) and len(cats) > 0
    for c in cats:
        if c.get("kind") == kind:
            return c["id"]
    raise AssertionError(f"no category of kind {kind}")


async def _make_tx(client, **kwargs) -> int:
    resp = await client.post("/api/transactions", json=kwargs)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_invalid_type_returns_400_deep2(client):
    acc = await _make_account(client, "d2-invalid-type")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "bogus",
            "account_id": acc,
            "to_account_id": None,
            "category_id": None,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "非法的交易类型"


@pytest.mark.asyncio
async def test_create_account_not_exist_returns_400_deep2(client):
    exp_cat = await _get_category_id(client, "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": 99999999,
            "to_account_id": None,
            "category_id": exp_cat,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "账户不存在"


@pytest.mark.asyncio
async def test_create_transfer_same_account_returns_400_deep2(client):
    acc = await _make_account(client, "d2-same-acc")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": acc,
            "to_account_id": acc,
            "category_id": None,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "转入账户不能与转出账户相同"


@pytest.mark.asyncio
async def test_create_transfer_without_to_account_returns_400_deep2(client):
    acc = await _make_account(client, "d2-tr-no-to")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": acc,
            "to_account_id": None,
            "category_id": None,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "转账必须指定转入账户"


@pytest.mark.asyncio
async def test_create_transfer_with_category_returns_400_deep2(client):
    acc = await _make_account(client, "d2-tr-a")
    acc2 = await _make_account(client, "d2-tr-b")
    exp_cat = await _get_category_id(client, "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "transfer",
            "account_id": acc,
            "to_account_id": acc2,
            "category_id": exp_cat,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "转账不能指定分类"


@pytest.mark.asyncio
async def test_create_expense_without_category_returns_400_deep2(client):
    acc = await _make_account(client, "d2-exp-no-cat")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": acc,
            "to_account_id": None,
            "category_id": None,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "收入/支出必须指定分类"


@pytest.mark.asyncio
async def test_create_expense_with_to_account_returns_400_deep2(client):
    acc = await _make_account(client, "d2-exp-a")
    acc2 = await _make_account(client, "d2-exp-b")
    exp_cat = await _get_category_id(client, "expense")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": acc,
            "to_account_id": acc2,
            "category_id": exp_cat,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "收入/支出不能指定转入账户"


@pytest.mark.asyncio
async def test_create_expense_with_income_category_returns_400_deep2(client):
    acc = await _make_account(client, "d2-exp-mismatch")
    inc_cat = await _get_category_id(client, "income")
    resp = await client.post(
        "/api/transactions",
        json={
            "type": "expense",
            "account_id": acc,
            "to_account_id": None,
            "category_id": inc_cat,
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
            "currency": "CNY",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "分类类型与交易类型不一致"


@pytest.mark.asyncio
async def test_list_filter_by_account_includes_both_transfer_sides_deep2(client):
    a = await _make_account(client, "d2-list-a")
    b = await _make_account(client, "d2-list-b")
    c = await _make_account(client, "d2-list-c")
    exp_cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="transfer",
        account_id=a,
        to_account_id=b,
        category_id=None,
        amount_cents=500,
        occurred_on="2024-03-01",
        note="tr-ab",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="transfer",
        account_id=c,
        to_account_id=a,
        category_id=None,
        amount_cents=700,
        occurred_on="2024-03-02",
        note="tr-ca",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=a,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-03-03",
        note="exp-a",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=b,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-03-04",
        note="exp-b",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"account_id": a})
    assert resp.status_code == 200
    data = resp.json()
    notes = {item["note"] for item in data["items"]}
    assert "tr-ab" in notes
    assert "tr-ca" in notes
    assert "exp-a" in notes
    assert "exp-b" not in notes
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_list_q_search_note_deep2(client):
    acc = await _make_account(client, "d2-q")
    exp_cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-04-01",
        note="grocery shopping",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=200,
        occurred_on="2024-04-02",
        note="coffee beans",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=300,
        occurred_on="2024-04-03",
        note="bookstore",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"q": "coffee"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["note"] == "coffee beans"


@pytest.mark.asyncio
async def test_list_date_range_inclusive_deep2(client):
    acc = await _make_account(client, "d2-date")
    exp_cat = await _get_category_id(client, "expense")
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-05-01",
        note="d1",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-05-15",
        note="d15",
        currency="CNY",
    )
    await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-05-31",
        note="d31",
        currency="CNY",
    )
    resp = await client.get(
        "/api/transactions",
        params={"date_from": "2024-05-01", "date_to": "2024-05-31"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 3
    resp2 = await client.get(
        "/api/transactions",
        params={"date_from": "2024-05-02", "date_to": "2024-05-30"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1
    assert resp2.json()["items"][0]["note"] == "d15"


@pytest.mark.asyncio
async def test_list_sort_occurred_on_desc_then_id_desc_deep2(client):
    acc = await _make_account(client, "d2-sort")
    exp_cat = await _get_category_id(client, "expense")
    id1 = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-06-01",
        note="first",
        currency="CNY",
    )
    id2 = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-06-01",
        note="second",
        currency="CNY",
    )
    id3 = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=1,
        occurred_on="2024-06-02",
        note="third",
        currency="CNY",
    )
    resp = await client.get("/api/transactions", params={"account_id": acc})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids[0] == id3
    assert ids[1] == id2
    assert ids[2] == id1


@pytest.mark.asyncio
async def test_update_type_field_ignored_deep2(client):
    acc = await _make_account(client, "d2-upd-type")
    exp_cat = await _get_category_id(client, "expense")
    tx_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-07-01",
        note="orig",
        currency="CNY",
    )
    resp = await client.put(
        f"/api/transactions/{tx_id}",
        json={"type": "income", "note": "changed"},
    )
    assert resp.status_code == 422

    resp2 = await client.get(f"/api/transactions/{tx_id}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["type"] == "expense"
    assert body["note"] == "orig"


@pytest.mark.asyncio
async def test_update_nonexistent_returns_404_deep2(client):
    resp = await client.put(
        "/api/transactions/99999999",
        json={"note": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "交易不存在"


@pytest.mark.asyncio
async def test_update_to_invalid_combination_returns_400_deep2(client):
    acc = await _make_account(client, "d2-upd-invalid")
    exp_cat = await _get_category_id(client, "expense")
    tx_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-08-01",
        note="ok",
        currency="CNY",
    )
    resp = await client.put(
        f"/api/transactions/{tx_id}",
        json={"category_id": None},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "收入/支出必须指定分类"


@pytest.mark.asyncio
async def test_delete_then_get_returns_404_deep2(client):
    acc = await _make_account(client, "d2-del")
    exp_cat = await _get_category_id(client, "expense")
    tx_id = await _make_tx(
        client,
        type="expense",
        account_id=acc,
        to_account_id=None,
        category_id=exp_cat,
        amount_cents=100,
        occurred_on="2024-09-01",
        note="todelete",
        currency="CNY",
    )
    del_resp = await client.delete(f"/api/transactions/{tx_id}")
    assert del_resp.status_code == 204
    get_resp = await client.get(f"/api/transactions/{tx_id}")
    assert get_resp.status_code == 404
    assert get_resp.json()["detail"] == "交易不存在"


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404_deep2(client):
    resp = await client.delete("/api/transactions/99999999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "交易不存在"