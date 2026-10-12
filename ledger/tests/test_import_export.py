from datetime import date


async def _create_account(client, name):
    resp = await client.post("/api/accounts", json={"name": name, "type": "cash"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def test_import_csv(client):
    await _create_account(client, "现金")
    today = date.today().isoformat()
    lines = [
        "date,type,account,category,amount,note",
        f"{today},支出,现金,餐饮,12.50,午餐",
        f"{today},收入,现金,工资,5000,工资到账",
        f"{today},支出,不存在的账户,餐饮,10,坏行",
    ]
    text = "\n".join(lines) + "\n"
    resp = await client.post(
        "/api/import/csv",
        files={"file": ("t.csv", text.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] == 2
    assert data["errors"]

    resp2 = await client.get("/api/transactions")
    assert resp2.status_code == 200
    assert resp2.json()["total"] >= 2


async def test_import_type_alias(client):
    await _create_account(client, "现金")
    today = date.today().isoformat()
    lines = [
        "date,type,account,category,amount,note",
        f"{today},expense,现金,餐饮,20,午饭",
        f"{today},income,现金,工资,3000,工资",
    ]
    text = "\n".join(lines) + "\n"
    resp = await client.post(
        "/api/import/csv",
        files={"file": ("t.csv", text.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] == 2


async def test_export_csv(client):
    acc = await _create_account(client, "现金")
    account_id = acc["id"]
    resp = await client.get("/api/categories", params={"kind": "expense"})
    category_id = next(c["id"] for c in resp.json() if c["name"] == "餐饮")
    today = date.today().isoformat()
    resp_create = await client.post(
        "/api/transactions",
        json={
            "occurred_on": today,
            "type": "expense",
            "account_id": account_id,
            "category_id": category_id,
            "amount_cents": 990,
            "note": "导出测试",
        },
    )
    assert resp_create.status_code in (200, 201), resp_create.text

    resp = await client.get("/api/export/csv")
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers.get("content-type", "")
    text = resp.text
    assert "导出测试" in text
    assert "date" in text
