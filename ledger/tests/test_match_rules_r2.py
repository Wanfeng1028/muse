"""match_by_rules / preview 链的回归测试（v2.11 停用规则仍生效 bug）。"""


async def _get_expense_category_id(client) -> int:
    """取一个 expense 类型分类的 id。"""
    resp = await client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.json()
    if isinstance(cats, dict):
        cats = cats.get("items", cats.get("categories", []))
    for c in cats:
        if c.get("kind") == "expense":
            return c["id"]
    raise AssertionError("未找到 expense 分类")


async def _create_account(client, name: str) -> int:
    """创建一个 cash 账户并返回 id。"""
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_rule(client, **kwargs) -> dict:
    """创建匹配规则并返回响应体。"""
    payload = {
        "pattern_type": "keyword",
        "direction": "any",
        "priority": 100,
        "is_enabled": 1,
    }
    payload.update(kwargs)
    resp = await client.post("/api/match-rules", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _upload_and_confirm(client, account_id: int, counterparty: str, summary: str):
    """上传一条支出明细并执行 confirm，返回 batch id。"""
    csv_text = (
        "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
        f"2024-05-01 10:00:00,{counterparty},{summary},45.00,支出\n"
    )
    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("stmt.csv", csv_text.encode("utf-8"), "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert resp.status_code == 200, resp.text
    bid = resp.json()["batch"]["id"]
    confirm = await client.post(f"/api/statements/{bid}/confirm")
    assert confirm.status_code == 200, confirm.text
    return bid


async def _items(client, bid: int, status: str) -> list:
    """按状态拉取批次条目。"""
    resp = await client.get(f"/api/statements/{bid}/items", params={"status": status})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_disabled_rule_not_applied_in_confirm(client):
    """停用规则在真实 confirm 流程中不生效：条目应留在 pending 且非 rule 来源。"""
    cat_id = await _get_expense_category_id(client)
    keyword = "停用回归咖啡A"
    await _create_rule(
        client,
        keyword=keyword,
        category_id=cat_id,
        is_enabled=0,
        priority=1,
    )
    account_id = await _create_account(client, "停用回归账户A")
    bid = await _upload_and_confirm(client, account_id, f"商户{keyword}", "拿铁")

    auto_items = await _items(client, bid, "auto")
    assert auto_items == [], f"停用规则不应产生 auto 条目: {auto_items}"

    pending_items = await _items(client, bid, "pending")
    assert len(pending_items) == 1, pending_items
    item = pending_items[0]
    assert item["status"] == "pending"
    assert item.get("match_source") != "rule"


async def test_enabled_rule_still_applies(client):
    """对照：启用规则在 confirm 后应命中并生成 auto 条目，match_source 为 rule。"""
    cat_id = await _get_expense_category_id(client)
    keyword = "启用回归咖啡B"
    await _create_rule(
        client,
        keyword=keyword,
        category_id=cat_id,
        is_enabled=1,
        priority=1,
    )
    account_id = await _create_account(client, "启用回归账户B")
    bid = await _upload_and_confirm(client, account_id, f"商户{keyword}", "拿铁")

    auto_items = await _items(client, bid, "auto")
    assert len(auto_items) == 1, auto_items
    item = auto_items[0]
    assert item["status"] == "auto"
    assert item["match_source"] == "rule"
    assert item["suggested_category_id"] == cat_id


async def test_disabled_and_enabled_same_keyword(client):
    """同关键词下停用规则（高优先级）不生效，仅启用规则命中其分类。"""
    cat_disabled = await _get_expense_category_id(client)
    # 另取一个不同分类，避免两者混同；若只有一个分类则复用但用不同规则 id 校验
    resp = await client.get("/api/categories")
    cats = resp.json()
    if isinstance(cats, dict):
        cats = cats.get("items", cats.get("categories", []))
    expenses = [c for c in cats if c.get("kind") == "expense"]
    cat_enabled = expenses[-1]["id"] if len(expenses) > 1 else cat_disabled

    # 唯一约束是 (keyword, pattern_type, direction) 精确匹配：用"长短包含"的两个
    # 不同 keyword 达到"同文本命中两条规则"的效果；停用规则优先级更高，
    # 若 is_enabled 过滤退化，停用规则会抢赢——这正是要防的回归。
    keyword_long = "同关键词停启C完整"
    keyword_short = "同关键词停启C"
    disabled_rule = await _create_rule(
        client,
        keyword=keyword_long,
        category_id=cat_disabled,
        is_enabled=0,
        priority=999,
    )
    enabled_rule = await _create_rule(
        client,
        keyword=keyword_short,
        category_id=cat_enabled,
        is_enabled=1,
        priority=1,
    )
    assert disabled_rule["id"] != enabled_rule["id"]

    account_id = await _create_account(client, "同关键词账户C")
    bid = await _upload_and_confirm(client, account_id, f"商户{keyword_long}", "拿铁")

    auto_items = await _items(client, bid, "auto")
    assert len(auto_items) == 1, auto_items
    item = auto_items[0]
    assert item["status"] == "auto"
    assert item["match_source"] == "rule"
    assert item["suggested_category_id"] == cat_enabled


async def test_preview_chain_disabled_keyword_reason(client):
    """preview 中停用的关键词规则条目 reason 为“规则已停用”且 matched 为 False。"""
    cat_id = await _get_expense_category_id(client)
    keyword = "停用预览关键词D"
    rule = await _create_rule(
        client,
        keyword=keyword,
        category_id=cat_id,
        is_enabled=0,
        priority=1,
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={
            "counterparty": f"商户{keyword}",
            "summary": "拿铁",
            "direction": "out",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    chain = body["chain"]
    hit = body["hit"]

    matched_entries = [e for e in chain if e.get("rule_id") == rule["id"]]
    assert len(matched_entries) == 1, matched_entries
    entry = matched_entries[0]
    assert entry["reason"] == "规则已停用"
    assert entry["matched"] is False
    assert entry["category_id"] is None
    assert hit.get("rule_id") != rule["id"]


async def test_preview_chain_disabled_regex_reason(client):
    """preview 中停用的正则规则条目 reason 为“规则已停用”且 matched 为 False。"""
    cat_id = await _get_expense_category_id(client)
    pattern = "停用预览正则E.*"
    rule = await _create_rule(
        client,
        keyword=pattern,
        pattern_type="regex",
        category_id=cat_id,
        is_enabled=0,
        priority=1,
    )

    resp = await client.post(
        "/api/match-rules/preview",
        json={
            "counterparty": "停用预览正则E商户",
            "summary": "拿铁",
            "direction": "out",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    chain = body["chain"]

    entries = [e for e in chain if e.get("rule_id") == rule["id"]]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry["source"] == "rule_regex"
    assert entry["reason"] == "规则已停用"
    assert entry["matched"] is False
    assert entry["category_id"] is None


async def test_match_by_rules_include_rule_id_skips_disabled(client):
    """纯函数：同关键词下停用规则被跳过，返回启用规则的 (category_id, 95, rule_id)。"""
    from ledger.matching import match_by_rules

    cat_disabled = await _get_expense_category_id(client)
    resp = await client.get("/api/categories")
    cats = resp.json()
    if isinstance(cats, dict):
        cats = cats.get("items", cats.get("categories", []))
    expenses = [c for c in cats if c.get("kind") == "expense"]
    cat_enabled = expenses[-1]["id"] if len(expenses) > 1 else cat_disabled

    # 纯函数测试直接构造规则 dict（不经 API，避免唯一约束 409）；
    # 停用规则优先级更高，若过滤退化它会抢赢。
    keyword_long = "纯函数停启F完整"
    keyword_short = "纯函数停启F"
    rules = [
        {
            "id": 901,
            "keyword": keyword_long,
            "pattern_type": "keyword",
            "category_id": cat_disabled,
            "direction": "any",
            "priority": 999,
            "is_enabled": 0,
        },
        {
            "id": 902,
            "keyword": keyword_short,
            "pattern_type": "keyword",
            "category_id": cat_enabled,
            "direction": "any",
            "priority": 1,
            "is_enabled": 1,
        },
    ]

    result = match_by_rules(
        f"商户{keyword_long}", "拿铁", "out", rules, include_rule_id=True
    )
    assert result is not None
    assert len(result) == 3, result
    category_id, confidence, rule_id = result
    assert category_id == cat_enabled
    assert confidence == 95
    assert rule_id == 902


async def test_preview_chain_order_alias_first_suggest_last(client):
    """preview 链顺序：首条 alias，末条 suggest，规则条目数与创建数一致。"""
    cat_id = await _get_expense_category_id(client)
    created = []
    for i in range(2):
        r = await _create_rule(
            client,
            keyword=f"链顺序G{i}",
            category_id=cat_id,
            is_enabled=1,
            priority=10 + i,
        )
        created.append(r)

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": "无关文本", "summary": "无关", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    chain = resp.json()["chain"]

    assert chain[0]["source"] == "alias"
    assert chain[-1]["source"] == "suggest"

    rule_entries = [
        e for e in chain if e["source"] in ("rule_keyword", "rule_regex")
    ]
    assert len(rule_entries) == len(created)
    rule_ids_in_chain = [e["rule_id"] for e in rule_entries]
    for r in created:
        assert r["id"] in rule_ids_in_chain


async def test_preview_hit_consistent_with_chain(client):
    """命中时 hit.rule_id 与链中唯一 matched=True 条目一致；未命中时 hit 分类为空且无命中条目。"""
    cat_id = await _get_expense_category_id(client)
    keyword = "一致性H"
    rule = await _create_rule(
        client,
        keyword=keyword,
        category_id=cat_id,
        is_enabled=1,
        priority=1,
    )

    hit_resp = await client.post(
        "/api/match-rules/preview",
        json={
            "counterparty": f"商户{keyword}",
            "summary": "拿铁",
            "direction": "out",
        },
    )
    assert hit_resp.status_code == 200, hit_resp.text
    hit_body = hit_resp.json()
    hit = hit_body["hit"]
    chain = hit_body["chain"]

    assert hit.get("rule_id")
    assert hit["rule_id"] == rule["id"]
    matched_entries = [
        e
        for e in chain
        if e.get("source") in ("rule_keyword", "rule_regex")
        and e.get("rule_id") == hit["rule_id"]
        and e.get("matched")
    ]
    assert len(matched_entries) == 1, matched_entries

    miss_resp = await client.post(
        "/api/match-rules/preview",
        json={
            "counterparty": "完全无关的商户ZZZ",
            "summary": "完全无关的商品",
            "direction": "out",
        },
    )
    assert miss_resp.status_code == 200, miss_resp.text
    miss_body = miss_resp.json()
    miss_hit = miss_body["hit"]
    miss_chain = miss_body["chain"]

    assert miss_hit.get("category_id") is None
    rule_entries = [
        e for e in miss_chain if e["source"] in ("rule_keyword", "rule_regex")
    ]
    assert all(e.get("matched") is False for e in rule_entries)
