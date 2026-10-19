import pytest
from httpx import AsyncClient

ALIPAY_CSV = "支付宝交易记录明细查询\n交易创建时间,交易对方,商品说明,金额（元）,收/支\n2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出\n2024-01-03 12:30:00,肯德基,午餐,45.00,支出\n"


async def _account(client, name="t"):
    r = await client.post("/api/accounts", json={"name": name, "type": "cash", "opening_balance_cents": 0})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _cat(client, name, kind="expense"):
    r = await client.get("/api/categories", params={"kind": kind})
    assert r.status_code == 200
    for c in r.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(name)


async def _batch(client, aid, csv=ALIPAY_CSV):
    files = {"file": ("a.csv", csv.encode("utf-8"), "text/csv")}
    r = await client.post("/api/statements/upload", files=files, data={"account_id": str(aid)})
    assert r.status_code == 200, r.text
    bid = r.json()["batch"]["id"]
    r = await client.post(f"/api/statements/{bid}/confirm")
    assert r.status_code == 200, r.text
    return bid


async def _pending(client, bid):
    r = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def _wb(client, method, path, **kw):
    r = await client.request(method, "/api/workbench" + path, **kw)
    if r.status_code == 404:
        r = await client.request(method, "/api" + path, **kw)
    return r


@pytest.mark.asyncio
async def test_confirm_saves_category(client: AsyncClient):
    """confirm 保存分类：条目状态离开 pending 且生成 transaction_id。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]
    cid = await _cat(client, "餐饮", "expense")

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": cid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") != "pending", f"status still pending: {body}"
    assert body.get("transaction_id"), f"missing transaction_id: {body}"


@pytest.mark.asyncio
async def test_confirm_save_rule_true_creates_rule(client: AsyncClient):
    """save_rule=True 时自动建立关键词匹配规则。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]
    cid = await _cat(client, "餐饮", "expense")
    counterparty = item.get("counterparty") or item.get("payee") or ""

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": cid, "save_rule": True})
    assert r.status_code == 200, r.text

    r = await client.get("/api/match-rules")
    assert r.status_code == 200, r.text
    rules = r.json()
    if isinstance(rules, dict):
        rules = rules.get("items", [])
    keywords = [str(rr.get("keyword", "")) for rr in rules]
    assert any(counterparty and counterparty in k for k in keywords), \
        f"no rule for {counterparty!r} in {keywords}"


@pytest.mark.asyncio
async def test_confirm_save_rule_false_no_rule(client: AsyncClient):
    """save_rule=False 时不建立关键词规则。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]
    cid = await _cat(client, "餐饮", "expense")
    counterparty = item.get("counterparty") or item.get("payee") or ""

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": cid, "save_rule": False})
    assert r.status_code == 200, r.text

    r = await client.get("/api/match-rules")
    assert r.status_code == 200, r.text
    rules = r.json()
    if isinstance(rules, dict):
        rules = rules.get("items", [])
    keywords = [str(rr.get("keyword", "")) for rr in rules]
    assert not any(counterparty and counterparty in k for k in keywords), \
        f"unexpected rule for {counterparty!r} in {keywords}"


@pytest.mark.asyncio
async def test_confirm_already_resolved_returns_400(client: AsyncClient):
    """重复 confirm 已处理条目应返回 400。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]
    cid = await _cat(client, "餐饮", "expense")

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": cid})
    assert r.status_code == 200, r.text

    r2 = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                  json={"action": "confirm", "category_id": cid})
    assert r2.status_code == 400, r2.text


@pytest.mark.asyncio
async def test_confirm_category_kind_mismatch_returns_400(client: AsyncClient):
    """expense 分类用于 income 条目应返回 400。"""
    aid = await _account(client, "现金")
    income_csv = "支付宝交易记录明细查询\n交易创建时间,交易对方,商品说明,金额（元）,收/支\n2024-01-05 09:00:00,某公司,工资,5000.00,收入\n"
    bid = await _batch(client, aid, csv=income_csv)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]
    cid = await _cat(client, "餐饮", "expense")

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": cid})
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_confirm_nonexistent_category_returns_400_or_404(client: AsyncClient):
    """category_id 不存在应返回 400 或 404。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"no pending items: {items}"
    item = items[0]

    r = await _wb(client, "POST", f"/items/{item['id']}/resolve",
                 json={"action": "confirm", "category_id": 999999})
    assert r.status_code in (400, 404), r.text
