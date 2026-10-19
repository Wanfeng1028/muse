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


async def _items_all(client, bid):
    r = await client.get(f"/api/statements/{bid}/items")
    assert r.status_code == 200, r.text
    return r.json()["items"]


@pytest.mark.asyncio
async def test_ignore_marks_item_skipped(client: AsyncClient):
    """ignore 后条目 status=skipped。"""
    aid = await _account(client, "现金A")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, "confirm 后应有 pending 条目"
    item_id = items[0]["id"]

    r = await _wb(client, "POST", f"/items/{item_id}/resolve", json={"action": "ignore"})
    assert r.status_code == 200, r.text

    all_items = await _items_all(client, bid)
    target = [it for it in all_items if it["id"] == item_id]
    assert target, f"条目 {item_id} 应仍存在, items={all_items}"
    assert target[0]["status"] == "skipped", f"期望 skipped, got {target[0]['status']}, r={all_items}"


@pytest.mark.asyncio
async def test_ignore_decrements_pending_count(client: AsyncClient):
    """ignore 后 batch 的 pending_count 减 1（或 pending 列表长度减 1）。"""
    aid = await _account(client, "现金B")
    bid = await _batch(client, aid)

    pending_before = await _pending(client, bid)
    n_before = len(pending_before)
    assert n_before >= 1, "confirm 后应有 pending 条目"

    # 尝试读取 workbench batches 列表中的 pending_count（字段名未知时回退）
    pending_count_before = None
    rb = await _wb(client, "GET", "/batches")
    if rb.status_code == 200:
        body = rb.json()
        batches = body.get("batches", body) if isinstance(body, dict) else body
        if isinstance(batches, list):
            for b in batches:
                if b.get("id") == bid and "pending_count" in b:
                    pending_count_before = b["pending_count"]
                    break

    item_id = pending_before[0]["id"]
    r = await _wb(client, "POST", f"/items/{item_id}/resolve", json={"action": "ignore"})
    assert r.status_code == 200, r.text

    pending_after = await _pending(client, bid)
    assert len(pending_after) == n_before - 1, (
        f"pending 数量应从 {n_before} 减到 {n_before - 1}, got {len(pending_after)}, r={pending_after}"
    )

    if pending_count_before is not None:
        rb2 = await _wb(client, "GET", "/batches")
        assert rb2.status_code == 200, rb2.text
        body2 = rb2.json()
        batches2 = body2.get("batches", body2) if isinstance(body2, dict) else body2
        pending_count_after = None
        for b in batches2:
            if b.get("id") == bid:
                pending_count_after = b.get("pending_count")
                break
        assert pending_count_after == pending_count_before - 1, (
            f"pending_count 应从 {pending_count_before} 减到 {pending_count_before - 1}, "
            f"got {pending_count_after}, r={batches2}"
        )


@pytest.mark.asyncio
async def test_ignore_already_processed_returns_400(client: AsyncClient):
    """ignore 已处理条目 → 400。"""
    aid = await _account(client, "现金C")
    bid = await _batch(client, aid)
    items = await _pending(client, bid)
    assert len(items) >= 1, "confirm 后应有 pending 条目"
    item_id = items[0]["id"]

    # 先 ignore 使其变为 skipped（已处理）
    r1 = await _wb(client, "POST", f"/items/{item_id}/resolve", json={"action": "ignore"})
    assert r1.status_code == 200, r1.text

    # 再次 ignore 同一已处理条目应 400
    r2 = await _wb(client, "POST", f"/items/{item_id}/resolve", json={"action": "ignore"})
    assert r2.status_code == 400, f"期望 400, got {r2.status_code}, r={r2.text}"
