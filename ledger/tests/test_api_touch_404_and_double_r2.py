from __future__ import annotations


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


async def _get_food_category_id(client) -> int:
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    items = resp.json()
    for item in items:
        if item.get("name") == "餐饮":
            return item["id"]
    raise AssertionError("未找到餐饮分类")


async def _make_tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_touch_missing_rule_returns_404(client):
    resp = await client.post("/api/match-rules/99999999/touch")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "匹配规则不存在"


async def test_touch_new_rule_returns_hit_count_one(client):
    category_id = await _get_food_category_id(client)
    created = await client.post(
        "/api/match-rules",
        json={"keyword": "星巴克", "category_id": category_id, "pattern_type": "keyword"},
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    touched = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert touched.status_code == 200, touched.text
    body = touched.json()
    assert body["ok"] is True
    assert body["hit_count"] == 1


async def test_touch_twice_accumulates_hit_count(client):
    category_id = await _get_food_category_id(client)
    created = await client.post(
        "/api/match-rules",
        json={"keyword": "瑞幸", "category_id": category_id, "pattern_type": "keyword"},
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    first = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert first.status_code == 200, first.text
    assert first.json()["hit_count"] == 1

    second = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert second.status_code == 200, second.text
    assert second.json()["hit_count"] == 2


async def test_touch_twice_list_hit_count_is_two(client):
    category_id = await _get_food_category_id(client)
    created = await client.post(
        "/api/match-rules",
        json={"keyword": "麦当劳", "category_id": category_id, "pattern_type": "keyword"},
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    first = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert first.status_code == 200, first.text
    assert first.json()["hit_count"] == 1

    second = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert second.status_code == 200, second.text
    assert second.json()["hit_count"] == 2

    listed = await client.get("/api/match-rules")
    assert listed.status_code == 200, listed.text
    matched = [r for r in listed.json() if r.get("id") == rule_id]
    assert len(matched) == 1
    assert matched[0].get("hit_count") == 2