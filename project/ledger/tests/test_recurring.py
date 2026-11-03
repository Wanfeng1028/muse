async def _create_account(client, name):
    resp = await client.post("/api/accounts", json={"name": name, "type": "cash"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    if isinstance(data, dict):
        data = data.get("items", [])
    for c in data:
        if c.get("name") == name and c.get("kind") == kind:
            return c["id"]
    raise AssertionError(f"category {name}/{kind} not found")


async def test_crud(client):
    acc_id = await _create_account(client, "现金账户")
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "房租",
            "type": "expense",
            "account_id": acc_id,
            "category_id": cat_id,
            "amount_cents": 300000,
            "day_of_month": 5,
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    rid = created["id"]
    assert created["name"] == "房租"
    assert created["amount_cents"] == 300000
    assert created["day_of_month"] == 5

    resp = await client.get("/api/recurring")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    if isinstance(data, dict):
        data = data.get("items", [])
    assert any(r["id"] == rid and r["name"] == "房租" for r in data)

    resp = await client.put(f"/api/recurring/{rid}", json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    resp = await client.delete(f"/api/recurring/{rid}")
    assert resp.status_code == 204, resp.text


async def test_day_out_of_range(client):
    acc_id = await _create_account(client, "现金账户2")
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "超范围",
            "type": "expense",
            "account_id": acc_id,
            "category_id": cat_id,
            "amount_cents": 1000,
            "day_of_month": 31,
        },
    )
    assert resp.status_code == 422, resp.text


async def test_missing_account_404(client):
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "缺账户",
            "type": "expense",
            "account_id": 999999,
            "category_id": cat_id,
            "amount_cents": 1000,
            "day_of_month": 1,
        },
    )
    assert resp.status_code in (400, 404), resp.text


async def test_upcoming(client):
    acc_id = await _create_account(client, "现金账户3")
    cat_id = await _cat_id(client, "餐饮", "expense")

    resp = await client.post(
        "/api/recurring",
        json={
            "name": "月初固定",
            "type": "expense",
            "account_id": acc_id,
            "category_id": cat_id,
            "amount_cents": 50000,
            "day_of_month": 1,
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.get("/api/recurring/upcoming", params={"days": 60})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    if isinstance(data, dict):
        data = data.get("items", [])
    match = [r for r in data if r.get("name") == "月初固定"]
    assert match, data
    next_date = match[0]["next_date"]
    assert isinstance(next_date, str)
    assert len(next_date) == 10
