"""侦探"对不上标"（未匹配）路径深测。

覆盖：preview 解释链的未命中表达、skip 语义（幂等/404/pending_count）、
claim 的分类方向校验、人工标一次记住为规则后下次自动命中（侦探闭环）。
"""

UNKNOWN = "火星撞地球杂货铺"


async def _create_account(client, name):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _alipay_csv(rows):
    lines = ["交易创建时间,交易对方,商品说明,金额（元）,收/支"]
    lines.extend(rows)
    return "\n".join(lines).encode("utf-8")


async def _upload(client, aid, payload, name="u.csv"):
    resp = await client.post(
        "/api/statements/upload",
        files={"file": (name, payload, "text/csv")},
        data={"account_id": str(aid)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["batch"]["id"]


async def _confirm(client, bid):
    resp = await client.post(f"/api/statements/{bid}/confirm")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _pending(client, bid):
    resp = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def _category_ids(client):
    resp = await client.get("/api/categories")
    assert resp.status_code == 200, resp.text
    out = {}
    for c in resp.json():
        out.setdefault(c["kind"], c["id"])
    return out


async def test_preview_unmatched_chain(client):
    """完全陌生的商户：preview 明确表达无匹配，解释链结构完整。"""
    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": UNKNOWN, "summary": "不知名商品-1", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    hit = body["hit"]
    assert hit["category_id"] is None, hit
    assert hit["reason"] == "无匹配", hit
    chain = body["chain"]
    assert isinstance(chain, list) and chain, "chain 应为非空列表"
    for entry in chain:
        assert {"source", "reason", "matched"} <= set(entry), entry
    assert chain[-1]["source"] == "suggest", chain[-1]
    assert chain[-1]["matched"] is False, chain[-1]


async def test_unmatched_skip_semantics(client):
    """skip：成功减 pending_count；重复 skip 400；不存在的 id 404。"""
    aid = await _create_account(client, "跳过账户")
    bid = await _upload(
        client,
        aid,
        _alipay_csv(
            [
                f"2026-09-01 10:00:00,{UNKNOWN},商品a,100.00,支出",
                f"2026-09-02 10:00:00,{UNKNOWN},商品b,200.00,支出",
            ]
        ),
    )
    await _confirm(client, bid)
    items = await _pending(client, bid)
    assert len(items) == 2, items
    i1, i2 = items[0]["id"], items[1]["id"]

    resp = await client.post(f"/api/statements/items/{i1}/skip")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    resp = await client.post(f"/api/statements/items/{i1}/skip")
    assert resp.status_code == 400, resp.text

    resp = await client.post("/api/statements/items/99999999/skip")
    assert resp.status_code == 404, resp.text

    rest = await _pending(client, bid)
    assert [it["id"] for it in rest] == [i2], rest

    resp = await client.get(f"/api/statements/{bid}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["pending_count"] == 1, resp.json()


async def test_unmatched_claim_kind_guard(client):
    """claim 方向校验：收入分类认领支出条目 400；重复认领 400。"""
    aid = await _create_account(client, "认领账户")
    bid = await _upload(
        client,
        aid,
        _alipay_csv([f"2026-09-03 10:00:00,{UNKNOWN},商品c,50.00,支出"]),
    )
    await _confirm(client, bid)
    items = await _pending(client, bid)
    assert len(items) == 1, items
    iid = items[0]["id"]

    cats = await _category_ids(client)
    resp = await client.post(
        f"/api/statements/items/{iid}/claim",
        json={"category_id": cats["income"], "save_rule": False},
    )
    assert resp.status_code == 400, resp.text

    resp = await client.post(
        f"/api/statements/items/{iid}/claim",
        json={"category_id": cats["expense"], "save_rule": False},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"/api/statements/items/{iid}/claim",
        json={"category_id": cats["expense"], "save_rule": False},
    )
    assert resp.status_code == 400, resp.text


async def test_learn_once_then_auto_match(client):
    """对不上 -> 人工标一次记住为规则 -> 下批同商户自动命中。"""
    aid = await _create_account(client, "学习账户")
    merchant = "水星路边摊"

    resp = await client.post(
        "/api/match-rules/preview",
        json={"counterparty": merchant, "summary": "早餐", "direction": "out"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["hit"]["category_id"] is None, "先确认确实对不上"

    bid = await _upload(
        client,
        aid,
        _alipay_csv([f"2026-09-04 10:00:00,{merchant},早餐,30.00,支出"]),
    )
    await _confirm(client, bid)
    items = await _pending(client, bid)
    assert len(items) == 1, items

    cats = await _category_ids(client)
    resp = await client.post(
        f"/api/statements/items/{items[0]['id']}/claim",
        json={"category_id": cats["expense"], "save_rule": True},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/match-rules")
    assert resp.status_code == 200, resp.text
    assert any(
        r["keyword"] and merchant in r["keyword"] for r in resp.json()
    ), resp.json()

    bid2 = await _upload(
        client,
        aid,
        _alipay_csv([f"2026-09-05 10:00:00,{merchant},早餐,40.00,支出"]),
        name="u2.csv",
    )
    batch2 = await _confirm(client, bid2)
    assert batch2["auto_count"] >= 1, batch2
