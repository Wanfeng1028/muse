"""匹配规则 API 测试。"""

from __future__ import annotations


async def _get_food_category_id(client) -> int:
    """从分类列表里取出餐饮分类 id。"""
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    items = resp.json()
    for item in items:
        if item.get("name") == "餐饮":
            return item["id"]
    raise AssertionError("未找到餐饮分类")


async def test_create_regex_rule_and_invalid_regex(client):
    """创建正则规则成功，非法正则返回 400。"""
    category_id = await _get_food_category_id(client)

    ok = await client.post(
        "/api/match-rules",
        json={
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "out",
            "priority": 5,
        },
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["keyword"] == "星巴克.*"
    assert body["pattern_type"] == "regex"
    assert body["is_enabled"] in (0, 1)
    assert "hit_count" in body

    bad = await client.post(
        "/api/match-rules",
        json={
            "keyword": "([a-z",
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "out",
            "priority": 5,
        },
    )
    assert bad.status_code == 400


async def test_duplicate_rule_returns_409(client):
    """三元组重复返回 409，不同 pattern_type 不冲突。"""
    category_id = await _get_food_category_id(client)

    first = await client.post(
        "/api/match-rules",
        json={
            "keyword": "肯德基",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "out",
            "priority": 3,
        },
    )
    assert first.status_code == 201

    dup = await client.post(
        "/api/match-rules",
        json={
            "keyword": "肯德基",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "out",
            "priority": 9,
        },
    )
    assert dup.status_code == 409

    diff_type = await client.post(
        "/api/match-rules",
        json={
            "keyword": "肯德基",
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "out",
            "priority": 9,
        },
    )
    assert diff_type.status_code == 201


async def test_update_rule_and_errors(client):
    """更新规则字段生效，异常分支返回正确状态码。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "麦当劳",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "out",
            "priority": 1,
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    updated = await client.put(
        f"/api/match-rules/{rule_id}",
        json={"priority": 10, "is_enabled": 0},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["priority"] == 10
    assert body["is_enabled"] == 0

    missing = await client.put(
        "/api/match-rules/999999",
        json={"priority": 10},
    )
    assert missing.status_code == 404

    bad_regex = await client.put(
        f"/api/match-rules/{rule_id}",
        json={"pattern_type": "regex", "keyword": "([a-z"},
    )
    assert bad_regex.status_code == 400


async def test_preview_hits_regex_rule(client):
    """preview 命中正则规则并返回链路。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "星巴克.*",
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "out",
            "priority": 5,
        },
    )
    assert created.status_code == 201

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "星巴克静安寺店", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hit"]["source"] == "rule_regex"
    assert body["hit"]["category_id"] == category_id
    assert isinstance(body["chain"], list)
    assert len(body["chain"]) > 0


async def test_preview_direction_filter(client):
    """direction 为 in 的规则不会在 out 预览中命中。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "工资",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "in",
            "priority": 5,
        },
    )
    assert created.status_code == 201

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "工资发放", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hit"]["source"] != "rule_keyword"
    for node in body["chain"]:
        if node["source"] == "rule_keyword":
            assert node["matched"] is False


async def test_touch_increments_hit_count(client):
    """touch 两次后 hit_count 为 2，不存在返回 404。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "汉堡王",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "out",
            "priority": 2,
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    first = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert first.status_code == 200
    assert first.json()["hit_count"] == 1

    second = await client.post(f"/api/match-rules/{rule_id}/touch")
    assert second.status_code == 200
    assert second.json()["hit_count"] == 2

    missing = await client.post("/api/match-rules/999999/touch")
    assert missing.status_code == 404


async def test_delete_rule_removed_from_list(client):
    """删除后规则不再出现在列表中。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "必胜客",
            "pattern_type": "keyword",
            "category_id": category_id,
            "direction": "out",
            "priority": 2,
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    deleted = await client.delete(f"/api/match-rules/{rule_id}")
    assert deleted.status_code == 200

    listed = await client.get("/api/match-rules")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert rule_id not in ids


async def test_disabled_rule_not_matched_in_preview(client):
    """禁用规则在预览中不命中。"""
    category_id = await _get_food_category_id(client)

    created = await client.post(
        "/api/match-rules",
        json={
            "keyword": "海底捞.*",
            "pattern_type": "regex",
            "category_id": category_id,
            "direction": "out",
            "priority": 8,
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    updated = await client.put(
        f"/api/match-rules/{rule_id}",
        json={"is_enabled": 0},
    )
    assert updated.status_code == 200

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "海底捞火锅店", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hit"]["source"] != "rule_regex"
    for node in body["chain"]:
        if node["source"] == "rule_regex" and node["rule_id"] == rule_id:
            assert node["matched"] is False
