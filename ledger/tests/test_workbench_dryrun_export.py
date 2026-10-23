import csv
from io import StringIO

import pytest
from httpx import AsyncClient

# ---------- fixtures / helpers (mirroring the ones already present) ----------
ALIPAY_CSV = (
    "支付宝交易记录明细查询\n交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
    "2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出\n"
    "2024-01-03 12:30:00,肯德基,午餐,45.00,支出\n"
)

async def _account(client: AsyncClient, name: str = "t") -> int:
    """创建一个现金账户并返回其 id。"""
    r = await client.post("/api/accounts", json={"name": name, "type": "cash", "opening_balance_cents": 0})
    assert r.status_code == 201, r.text
    return r.json()["id"]

async def _cat(client: AsyncClient, name: str, kind: str = "expense") -> str:
    """根据类别名称查找类别 ID（假设种子数据中存在）。"""
    r = await client.get("/api/categories", params={"kind": kind})
    assert r.status_code == 200, r.text
    for c in r.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(f"Category '{name}' (kind={kind}) not found")

async def _batch(client: AsyncClient, aid: int, csv: str = ALIPAY_CSV) -> str:
    """上传 CSV 创建账单并确认，返回批次 ID。"""
    files = {"file": ("a.csv", csv.encode("utf-8"), "text/csv")}
    r = await client.post("/api/statements/upload", files=files, data={"account_id": str(aid)})
    assert r.status_code == 200, r.text
    bid = r.json()["batch"]["id"]
    r = await client.post(f"/api/statements/{bid}/confirm")
    assert r.status_code == 200, r.text
    return bid

async def _pending_ids(client: AsyncClient, bid: str) -> list[str]:
    """返回指定批次当前处于 pending 状态的账单项 ID 列表。"""
    r = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
    assert r.status_code == 200, r.text
    return [it["id"] for it in r.json()["items"]]

# ---------- test cases ----------
@pytest.mark.asyncio
async def test_dry_run_confirm_no_writes(client: AsyncClient):
    """
    测试批量对账 dry-run 确认时不会实际落库。
    创建一个批次，其中包含 2 条待处理账单项，使用有效的 expense 分类执行干运行确认，
    应返回 dry_run=True，ok 包含两个 ID，failed 为空。
    验证 pending 状态仍为 2 条，且交易列表没有新增记录。
    """
    aid = await _account(client)
    bid = await _batch(client, aid)

    pending_before = await _pending_ids(client, bid)
    assert len(pending_before) == 2, f"Expected 2 pending items, got {len(pending_before)}"

    # 获取一个有效的 expense 分类 ID
    expense_cat_id = await _cat(client, "餐饮", kind="expense")

    r = await client.post(
        f"/api/workbench/batches/{bid}/resolve-batch",
        json={"action": "confirm", "category_id": expense_cat_id, "item_ids": pending_before, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert set(body["ok"]) == set(pending_before)
    assert body["failed"] == []

    # 确认 pending 状态未改变
    pending_after = await _pending_ids(client, bid)
    assert len(pending_after) == 2

    # 确保没有新交易产生（交易总数保持 0）
    r_tx = await client.get("/api/transactions")
    assert r_tx.status_code == 200, r_tx.text
    assert r_tx.json()["total"] == 0, r_tx.text


@pytest.mark.asyncio
async def test_dry_run_reports_failures(client: AsyncClient):
    """
    测试批量对账 dry-run 时使用不存在的分类 ID 会报告失败明细。
    验证每个失败项包含 ID 和“分类不存在”的错误信息，
    同时账单项仍保持 pending 状态。
    """
    aid = await _account(client)
    bid = await _batch(client, aid)

    pending_before = await _pending_ids(client, bid)
    assert len(pending_before) == 2

    # 使用不存在的分类 ID（999999）
    r = await client.post(
        f"/api/workbench/batches/{bid}/resolve-batch",
        json={"action": "confirm", "category_id": 999999, "item_ids": pending_before, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["ok"] == []
    assert len(body["failed"]) == 2

    for fail in body["failed"]:
        assert "id" in fail
        assert "reason" in fail
        assert "分类不存在" in fail["reason"]
        assert fail["id"] in pending_before

    # 确认 pending 状态未改变
    pending_after = await _pending_ids(client, bid)
    assert len(pending_after) == 2


@pytest.mark.asyncio
async def test_dry_run_direction_mismatch(client: AsyncClient):
    """
    测试批量对账 dry-run 时使用收入分类处理支出账单项会报告方向不匹配错误。
    验证失败原因中包含“分类类型与收支方向不匹配”。
    """
    aid = await _account(client)
    bid = await _batch(client, aid)

    pending_before = await _pending_ids(client, bid)
    assert len(pending_before) == 2

    # 获取一个 income 分类（如“工资”）来触发方向不匹配
    income_cat_id = await _cat(client, "工资", kind="income")

    r = await client.post(
        f"/api/workbench/batches/{bid}/resolve-batch",
        json={"action": "confirm", "category_id": income_cat_id, "item_ids": pending_before, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["ok"] == []
    assert len(body["failed"]) == 2

    for fail in body["failed"]:
        assert "id" in fail
        assert "reason" in fail
        assert "分类类型与收支方向不匹配" in fail["reason"]
        assert fail["id"] in pending_before

    # 确认 pending 状态未改变
    pending_after = await _pending_ids(client, bid)
    assert len(pending_after) == 2


@pytest.mark.asyncio
async def test_dry_run_invalid_action(client: AsyncClient):
    """
    测试批量对账 dry-run 时使用无效的 action 参数应返回 422 并包含错误信息。
    """
    aid = await _account(client)
    bid = await _batch(client, aid)

    # 使用一个有效的分类 ID（仅为满足参数要求）
    expense_cat_id = await _cat(client, "餐饮", kind="expense")

    r = await client.post(
        f"/api/workbench/batches/{bid}/resolve-batch",
        json={"action": "learn", "category_id": expense_cat_id, "item_ids": [], "dry_run": True},
    )
    # 预期为 422
    assert r.status_code == 422, r.text
    body = r.json()
    assert "批量仅支持 confirm 或 ignore" in body.get("detail", "")


@pytest.mark.asyncio
async def test_export_csv_failures(client: AsyncClient):
    """
    测试失败明细 CSV 导出功能。
    1) 构建一个包含两个账单项的批次，然后用无效的分类 ID（999999）调用 failures-export，
       预期返回 CSV，包含两行失败数据，每行均包含“分类不存在”原因，
       金额列分别为 32.00 和 45.00。
    2) 再次调用 failures-export，但使用有效的分类 ID，
       此时 CSV 应仅包含表头，无数据行。
    """
    aid = await _account(client)
    bid = await _batch(client, aid)

    # 获取两个 pending 项的详细信息
    r_items = await client.get(f"/api/statements/{bid}/items")
    assert r_items.status_code == 200, r_items.text
    all_items = r_items.json()["items"]
    pending_items = [it for it in all_items if it.get("status") == "pending"]
    assert len(pending_items) == 2

    pending_by_id = {it["id"]: it for it in pending_items}
    ids = list(pending_by_id.keys())

    # ----- 第一步：使用不存在的分类 ID 导出失败 -----
    r = await client.post(
        f"/api/workbench/batches/{bid}/failures-export",
        json={"action": "confirm", "category_id": 999999, "item_ids": ids},
    )
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert "filename=workbench-failures-" in r.headers.get("content-disposition", "")
    text = r.text
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(StringIO(text))
    rows = list(reader)

    # 表头校验
    expected_header = ["id", "occurred_on", "counterparty", "summary", "amount_yuan", "direction", "reason"]
    assert reader.fieldnames == expected_header

    # 校验两行数据
    assert len(rows) == 2

    for row in rows:
        item_id = row["id"]
        item = pending_by_id[int(item_id)]
        assert row["occurred_on"] == item["occurred_on"]
        assert row["counterparty"] == item["counterparty"]
        assert row["summary"] == item["summary"]
        assert row["amount_yuan"] == f"{item['amount_cents']/100:.2f}"
        assert row["direction"] == item["direction"]
        assert "分类不存在" in row["reason"]

    # ----- 第二步：使用有效的分类 ID 导出失败 -----
    valid_cat_id = await _cat(client, "餐饮", kind="expense")
    r2 = await client.post(
        f"/api/workbench/batches/{bid}/failures-export",
        json={"action": "confirm", "category_id": valid_cat_id, "item_ids": ids},
    )
    assert r2.status_code == 200, r2.text
    text2 = r2.text
    if text2.startswith("\ufeff"):
        text2 = text2[1:]
    reader2 = csv.DictReader(StringIO(text2))
    rows2 = list(reader2)
    # 此时应无失败行，仅表头
    assert rows2 == []


@pytest.mark.asyncio
async def test_export_batch_404(client: AsyncClient):
    """
    测试对不存在的批次 ID 调用 failures-export 时应返回 404。
    """
    r = await client.post("/api/workbench/batches/999999/failures-export", json={"action": "confirm", "item_ids": []})
    assert r.status_code == 404, r.text
