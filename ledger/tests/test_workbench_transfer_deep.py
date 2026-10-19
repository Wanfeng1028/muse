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
async def test_transfer_to_other_account(client: AsyncClient):
    """transfer 到另一账户：条目 claimed 且生成 type=transfer 的交易。"""
    aid_a = await _account(client, "A账户")
    aid_b = await _account(client, "B账户")
    bid = await _batch(client, aid_a)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"期望有待处理条目: {items}"
    item_id = items[0]["id"]

    r = await _wb(
        client,
        "POST",
        f"/items/{item_id}/resolve",
        json={"action": "transfer", "to_account_id": aid_b},
    )
    assert r.status_code == 200, r.text

    r = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
    assert r.status_code == 200, r.text
    pending_ids = [it["id"] for it in r.json()["items"]]
    assert item_id not in pending_ids, f"条目应已 claimed: {r.text}"

    r = await client.get("/api/transactions")
    assert r.status_code == 200, r.text
    txs = r.json()
    if isinstance(txs, dict):
        txs = txs.get("items", txs.get("transactions", []))
    matched = [t for t in txs if t.get("type") == "transfer"]
    assert matched, f"应存在 type=transfer 的交易: {r.text}"


@pytest.mark.asyncio
async def test_transfer_missing_to_account_id(client: AsyncClient):
    """transfer 缺少 to_account_id → 400。"""
    aid_a = await _account(client, "A账户")
    bid = await _batch(client, aid_a)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"期望有待处理条目: {items}"
    item_id = items[0]["id"]

    r = await _wb(
        client,
        "POST",
        f"/items/{item_id}/resolve",
        json={"action": "transfer"},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_transfer_to_account_not_found(client: AsyncClient):
    """to_account_id 指向不存在的账户 → 404。"""
    aid_a = await _account(client, "A账户")
    bid = await _batch(client, aid_a)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"期望有待处理条目: {items}"
    item_id = items[0]["id"]

    r = await _wb(
        client,
        "POST",
        f"/items/{item_id}/resolve",
        json={"action": "transfer", "to_account_id": 999999},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_transfer_to_same_account(client: AsyncClient):
    """to_account_id 等于批次账户 → 400。"""
    aid_a = await _account(client, "A账户")
    bid = await _batch(client, aid_a)
    items = await _pending(client, bid)
    assert len(items) >= 1, f"期望有待处理条目: {items}"
    item_id = items[0]["id"]

    r = await _wb(
        client,
        "POST",
        f"/items/{item_id}/resolve",
        json={"action": "transfer", "to_account_id": aid_a},
    )
    assert r.status_code == 400, r.text
