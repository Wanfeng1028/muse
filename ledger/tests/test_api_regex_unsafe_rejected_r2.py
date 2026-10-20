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


async def _post_rule(client, keyword, category_id):
    return await client.post(
        "/api/match-rules",
        json={
            "keyword": keyword,
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "any",
            "priority": 0,
            "is_enabled": 1,
        },
    )


async def test_regex_catastrophic_backtracking_rejected(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "(a+)+", cat)
    assert resp.status_code == 400, resp.text
    assert "灾难性回溯" in resp.json()["detail"]


async def test_regex_backtracking_risk_rejected(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "a.*b.*c", cat)
    assert resp.status_code == 400, resp.text
    assert "回溯风险" in resp.json()["detail"]


async def test_regex_backreference_rejected(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "(a)\\1", cat)
    assert resp.status_code == 400, resp.text
    assert "回溯引用" in resp.json()["detail"]


async def test_regex_too_long_rejected(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "x" * 201, cat)
    assert resp.status_code == 400, resp.text
    assert "过长" in resp.json()["detail"]


async def test_regex_valid_pattern_accepted(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "abc\\d+", cat)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["keyword"] == "abc\\d+"
    assert body["pattern_type"] == "regex"
    assert body["category_id"] == cat


async def test_rejected_rule_not_persisted(client):
    cat = await _cat_id(client, "餐饮", "expense")
    resp = await _post_rule(client, "(a+)+", cat)
    assert resp.status_code == 400, resp.text
    listing = await client.get("/api/match-rules")
    assert listing.status_code == 200, listing.text
    keywords = [r["keyword"] for r in listing.json()]
    assert "(a+)+" not in keywords
