import pytest


async def _get_category_id(client, name="餐饮"):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    resp2 = await client.post(
        "/api/categories", json={"name": name, "type": "expense"}
    )
    assert resp2.status_code in (200, 201)
    return resp2.json()["id"]


async def _create_rule(
    client,
    keyword,
    category_id,
    *,
    pattern_type="keyword",
    direction="any",
    priority=100,
    is_enabled=1,
):
    body = {
        "keyword": keyword,
        "pattern_type": pattern_type,
        "category_id": category_id,
        "direction": direction,
        "priority": priority,
        "is_enabled": is_enabled,
    }
    resp = await client.post("/api/match-rules", json=body)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _find_chain_entry(chain, rule_id):
    for entry in chain:
        if entry.get("rule_id") == rule_id:
            return entry
    return None


@pytest.mark.asyncio
async def test_preview_skip_reasons_direction_and_disabled(client):
    cat_id = await _get_category_id(client)

    r1 = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=1, priority=10
    )
    r2 = await _create_rule(
        client, "星巴克", cat_id, direction="in", is_enabled=1, priority=20
    )
    r3 = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=0, priority=30,
        pattern_type="regex",
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "星巴克", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    chain = data["chain"]

    e1 = _find_chain_entry(chain, r1["id"])
    assert e1 is not None
    assert e1["matched"] is True

    e2 = _find_chain_entry(chain, r2["id"])
    assert e2 is not None
    assert e2["matched"] is False
    assert "方向不匹配" in e2["reason"]

    e3 = _find_chain_entry(chain, r3["id"])
    assert e3 is not None
    assert e3["matched"] is False
    assert "停用" in e3["reason"]


@pytest.mark.asyncio
async def test_preview_invalid_regex_does_not_crash(client, app):
    cat_id = await _get_category_id(client)

    from sqlalchemy import select
    from ledger.models import MatchRule

    from ledger.database import get_session_factory
    async with get_session_factory()() as session:
        rule = MatchRule(
            keyword="([a-z",
            pattern_type="regex",
            category_id=cat_id,
            direction="both",
            priority=1,
            is_enabled=1,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        bad_rule_id = rule.id

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "abc", "summary": "abc", "direction": "both"},
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]

    entry = _find_chain_entry(chain, bad_rule_id)
    assert entry is not None
    assert entry["matched"] is False
    assert ("非法" in entry["reason"]) or ("跳过" in entry["reason"])


@pytest.mark.asyncio
async def test_preview_unmatched_reason(client):
    cat_id = await _get_category_id(client)
    r = await _create_rule(
        client, "不存在的关键词xyz", cat_id, direction="any", is_enabled=1
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "完全无关", "summary": "无关", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]

    entry = _find_chain_entry(chain, r["id"])
    assert entry is not None
    assert entry["matched"] is False
    assert "未命中" in entry["reason"]


@pytest.mark.asyncio
async def test_preview_chain_order_preserved(client):
    cat_id = await _get_category_id(client)

    r1 = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=1, priority=30
    )
    r2 = await _create_rule(
        client, "星巴克", cat_id, direction="in", is_enabled=1, priority=20
    )
    r3 = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=0, priority=10,
        pattern_type="regex",
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "星巴克", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]

    rule_ids = [e["rule_id"] for e in chain if e.get("rule_id") is not None]
    present = [rid for rid in rule_ids if rid in (r1["id"], r2["id"], r3["id"])]
    sorted_ids = sorted([r1["id"], r2["id"], r3["id"]])
    assert set(present) == set(sorted_ids)
    # 链条按优先级降序排列（命中规则可能在 hit 与 chain 中各出现一次，只校验集合与相对顺序）
    seen = []
    for rid in rule_ids:
        if rid in sorted_ids and rid not in seen:
            seen.append(rid)
    assert seen == sorted(seen, key=lambda i: -{r1["id"]: 30, r2["id"]: 20, r3["id"]: 10}[i])


@pytest.mark.asyncio
async def test_preview_chain_entry_fields(client):
    cat_id = await _get_category_id(client)
    r = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=1, priority=10
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "星巴克", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]

    entry = _find_chain_entry(chain, r["id"])
    assert entry is not None
    for field in ("source", "rule_id", "category_id", "confidence", "reason", "matched"):
        assert field in entry, f"missing field {field}"
    assert isinstance(entry["source"], str)
    assert isinstance(entry["confidence"], (int, float))
    assert isinstance(entry["matched"], bool)


@pytest.mark.asyncio
async def test_preview_fuzzy_chain_entry_has_detail(client):
    cat_id = await _get_category_id(client)
    fuzzy_rule = await _create_rule(
        client, "星巴克", cat_id, direction="out", is_enabled=1, priority=10,
        pattern_type="fuzzy",
    )
    keyword_rule = await _create_rule(client, "麦当劳", cat_id, direction="out", is_enabled=1, priority=20)
    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "星巴客咖啡", "summary": "", "direction": "out"},
    )
    assert resp.status_code == 200
    chain = resp.json()["chain"]
    fuzzy_entry = _find_chain_entry(chain, fuzzy_rule["id"])
    assert fuzzy_entry is not None
    assert fuzzy_entry["matched"] is True
    assert fuzzy_entry["detail"] == {"matched": True, "distance": 1, "window": "星巴", "threshold": 1}
    keyword_entry = _find_chain_entry(chain, keyword_rule["id"])
    assert keyword_entry is not None
    assert "detail" not in keyword_entry
