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
        if c["name"] == name: return c["id"]
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
    # workbench router 前缀未知：优先 /api/workbench，404 则 fallback /api
    r = await client.request(method, "/api/workbench" + path, **kw)
    if r.status_code == 404:
        r = await client.request(method, "/api" + path, **kw)
    return r


async def _create_rule(client, keyword, category_id, enabled=True):
    payload = {"keyword": keyword, "category_id": category_id}
    if not enabled:
        payload["enabled"] = False
    r = await client.post("/api/match-rules", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _find_rule(client, rule_id):
    r = await client.get("/api/match-rules")
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"] if isinstance(body, dict) and "items" in body else body
    for it in items:
        if it.get("id") == rule_id:
            return it
    return None


@pytest.mark.asyncio
async def test_suggested_rule_id_lifecycle(client: AsyncClient):
    """建 keyword 规则「星巴克」→餐饮；上传含星巴克的账单并 confirm，pending 条目应带 suggested_rule_id 且 match_source 以 rule 开头。"""
    aid = await _account(client, "现金")
    cat_id = await _cat(client, "餐饮", "expense")

    rule = await _create_rule(client, "星巴克", cat_id)
    rule_id = rule["id"]

    bid = await _batch(client, aid)
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "confirm 后应有 pending 条目"

    target = None
    for it in items:
        desc = (it.get("counterparty") or "") + (it.get("summary") or "")
        if "星巴克" in desc:
            target = it
            break
    assert target is not None, f"未找到含星巴克的条目: {items}"

    assert target.get("suggested_rule_id") == rule_id, target
    ms = target.get("match_source") or ""
    assert isinstance(ms, str) and ms.startswith("rule"), target




@pytest.mark.asyncio
async def test_disabled_rule_not_suggested_for_new_batch(client: AsyncClient):
    """停用规则后，新上传批次的 pending 条目不再建议该规则。"""
    aid = await _account(client, "现金")
    cat_id = await _cat(client, "餐饮", "expense")

    rule = await _create_rule(client, "星巴克", cat_id)
    rule_id = rule["id"]

    r = await client.put(f"/api/match-rules/{rule_id}", json={"is_enabled": 0})
    assert r.status_code == 200, r.text

    bid = await _batch(client, aid)
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    for it in items:
        assert it.get("suggested_rule_id") != rule_id, it
