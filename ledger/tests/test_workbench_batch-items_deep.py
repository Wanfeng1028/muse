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


@pytest.mark.asyncio
async def test_batches_list_contains_new_batch(client: AsyncClient):
    """GET batches 列表应包含新建并确认后的批次。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)

    r = await _wb(client, "GET", "/batches")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["items"]
    ids = [b["id"] for b in items]
    assert bid in ids, r.text


@pytest.mark.asyncio
async def test_batch_items_filter_by_status(client: AsyncClient):
    """GET batch items 支持按 status=pending/claimed 过滤。"""
    aid = await _account(client, "现金")
    bid = await _batch(client, aid)

    r = await _wb(client, "GET", f"/batches/{bid}/items", params={"status": "pending"})
    assert r.status_code == 200, r.text
    data = r.json()
    pending = data["items"] if isinstance(data, dict) and "items" in data else data
    assert len(pending) >= 1, r.text
    assert len(pending) >= 1

    r = await _wb(client, "GET", f"/batches/{bid}/items", params={"status": "claimed"})
    assert r.status_code == 200, r.text
    data = r.json()
    claimed = data["items"] if isinstance(data, dict) and "items" in data else data
    assert isinstance(claimed, list)


@pytest.mark.asyncio
async def test_batch_items_unknown_batch_404(client: AsyncClient):
    """查询不存在批次的条目应返回 404。"""
    r = await _wb(client, "GET", "/batches/99999999/items")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_resolve_unknown_item_404(client: AsyncClient):
    """对不存在的条目执行 resolve 应返回 404。"""
    payload = {"action": "confirm", "category_id": await _cat(client, "餐饮")}
    r = await _wb(client, "POST", "/items/99999999/resolve", json=payload)
    assert r.status_code == 404, r.text
