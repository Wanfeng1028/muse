import pytest

ALIPAY_CSV = """支付宝交易记录明细查询
账号:[test@example.com]
起始日期:[2024-01-01 00:00:00]    终止日期:[2024-01-31 23:59:59]
---------------------------------交易记录明细列表------------------------------------
交易创建时间,交易对方,商品说明,金额（元）,收/支
2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出
2024-01-03 12:30:00,某公司,工资,8000.00,收入
"""


async def _create_account(client) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": "校验账户", "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload(client, account_id: int) -> int:
    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("alipay.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert resp.status_code == 200
    return resp.json()["batch"]["id"]


class TestStatementItemsStatusValidation:
    @pytest.mark.asyncio
    async def test_bogus_status_400(self, client):
        aid = await _create_account(client)
        batch_id = await _upload(client, aid)
        resp = await client.get(f"/api/statements/{batch_id}/items", params={"status": "bogus"})
        assert resp.status_code == 400
        assert "status" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_status_means_no_filter(self, client):
        aid = await _create_account(client)
        batch_id = await _upload(client, aid)
        baseline = await client.get(f"/api/statements/{batch_id}/items")
        assert baseline.status_code == 200
        assert baseline.json()["total"] == 2
        resp = await client.get(f"/api/statements/{batch_id}/items", params={"status": ""})
        assert resp.status_code == 200
        assert resp.json()["total"] == baseline.json()["total"]

    @pytest.mark.asyncio
    async def test_preview_filter(self, client):
        aid = await _create_account(client)
        batch_id = await _upload(client, aid)
        resp = await client.get(f"/api/statements/{batch_id}/items", params={"status": "preview"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
        for item in resp.json()["items"]:
            assert item["status"] == "preview"

    @pytest.mark.asyncio
    async def test_all_legal_statuses_200(self, client):
        aid = await _create_account(client)
        batch_id = await _upload(client, aid)
        for status in ("pending", "auto", "claimed", "skipped", "duplicate"):
            resp = await client.get(f"/api/statements/{batch_id}/items", params={"status": status})
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_batch_bogus_status_404(self, client):
        resp = await client.get("/api/statements/999999/items", params={"status": "bogus"})
        assert resp.status_code == 404
