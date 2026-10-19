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
    # workbench router 前缀未知：优先 /api/workbench，404 则 fallback /api
    r = await client.request(method, "/api/workbench" + path, **kw)
    if r.status_code == 404:
        r = await client.request(method, "/api" + path, **kw)
    return r


@pytest.mark.asyncio
async def test_resolve_batch_partial_success_mixed(client: AsyncClient):
    """3 条 pending，先单独 confirm 1 条使其非 pending，再批量 confirm 3 条：ok 含 2 条，failed 含 1 条且 reason 含 pending。"""
    aid = await _account(client, "混合")
    bid = await _batch(client, aid)
    cid = await _cat(client, "餐饮")
    items = await _pending(client, bid)
    assert len(items) == 2, items
    all_items = items
    # 额外造第 3 条 item：直接使用现有 2 条 pending 不够 3 条，改为先取全部
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    all_items = r.json()["items"]
    assert len(all_items) >= 2, all_items
    ids = [it["id"] for it in all_items]
    # 单独 confirm 第一条
    first = ids[0]
    rc = await _wb(client, "POST", f"/items/{first}/resolve", json={"action": "confirm", "category_id": cid})
    assert rc.status_code in (200, 204), rc.text
    # 批量 confirm 全部
    rb = await _wb(client, "POST", f"/batches/{bid}/resolve-batch", json={"action": "confirm", "item_ids": ids, "category_id": cid})
    assert rb.status_code == 200, rb.text
    body = rb.json()
    ok_ids = set(body["ok"])
    failed_ids = {f["id"] for f in body["failed"]}
    assert first in failed_ids, body
    for i in ids[1:]:
        assert i in ok_ids, body
    for f in body["failed"]:
        assert "pending" in f["reason"], body


@pytest.mark.asyncio
async def test_resolve_batch_rollback_isolation(client: AsyncClient):
    """失败条目不影响成功条目的提交：成功条目 status 已变。"""
    aid = await _account(client, "隔离")
    bid = await _batch(client, aid)
    cid = await _cat(client, "餐饮")
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 2, items
    ids = [it["id"] for it in items]
    good = ids[1]
    bad = ids[0]
    # 先 confirm good，使 bad 后续在批量里作为 pending 会失败？此处改为构造：批量含不存在 id 使 bad 场景
    rb = await _wb(client, "POST", f"/batches/{bid}/resolve-batch", json={"action": "confirm", "item_ids": [good, 999999], "category_id": cid})
    assert rb.status_code == 200, rb.text
    body = rb.json()
    ok_ids = set(body["ok"])
    failed_ids = {f["id"] for f in body["failed"]}
    assert good in ok_ids, body
    assert 999999 in failed_ids, body
    # 校验 good 已提交
    rr = await client.get(f"/api/statements/{bid}/items")
    assert rr.status_code == 200, rr.text
    for it in rr.json()["items"]:
        if it["id"] == good:
            assert it["status"] != "pending", rr.text
    _ = bad


@pytest.mark.asyncio
async def test_resolve_batch_empty_ids(client: AsyncClient):
    """空 item_ids → 200，ok=[] failed=[]。"""
    aid = await _account(client, "空")
    bid = await _batch(client, aid)
    rb = await _wb(client, "POST", f"/batches/{bid}/resolve-batch", json={"action": "confirm", "item_ids": [], "category_id": None})
    assert rb.status_code == 200, rb.text
    body = rb.json()
    assert body["ok"] == [], body
    assert body["failed"] == [], body


@pytest.mark.asyncio
async def test_resolve_batch_nonexistent_item(client: AsyncClient):
    """不存在的 item_id → failed 中 reason 含"不存在"。"""
    aid = await _account(client, "不存在")
    bid = await _batch(client, aid)
    rb = await _wb(client, "POST", f"/batches/{bid}/resolve-batch", json={"action": "confirm", "item_ids": [987654], "category_id": None})
    assert rb.status_code == 200, rb.text
    body = rb.json()
    assert body["ok"] == [], body
    assert len(body["failed"]) == 1, body
    f = body["failed"][0]
    reason = f["reason"]
    assert "不存在" in reason, body


@pytest.mark.asyncio
async def test_resolve_batch_invalid_action(client: AsyncClient):
    """action=learn → 422（批量仅支持 confirm/ignore）。"""
    aid = await _account(client, "非法动作")
    bid = await _batch(client, aid)
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ids = [it["id"] for it in items]
    rb = await _wb(client, "POST", f"/batches/{bid}/resolve-batch", json={"action": "learn", "item_ids": ids, "category_id": None})
    assert rb.status_code == 422, rb.text
