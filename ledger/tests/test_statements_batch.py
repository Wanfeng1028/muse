# tests/test_statements_batch.py
"""v2.4 批量处理与别名学习/转账配对集成测试。"""
import pytest


async def _create_account(client, name, opening=0):
    resp = await client.post("/api/accounts", json={"name": name, "type": "cash", "opening_balance_cents": opening})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _get_category_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


async def _upload(client, account_id, csv_text, filename="t.csv"):
    files = {"file": (filename, csv_text.encode("utf-8"), "text/csv")}
    resp = await client.post("/api/statements/upload", files=files, data={"account_id": str(account_id)})
    assert resp.status_code == 200, resp.text
    return resp.json()["batch"]["id"]


async def _pending_ids(client, batch_id):
    resp = await client.get(f"/api/statements/{batch_id}/items", params={"status": "pending"})
    assert resp.status_code == 200, resp.text
    return [it["id"] for it in resp.json()["items"]]


def _csv(rows):
    header = "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
    return header + "".join(rows)


class TestBatchClaim:
    @pytest.mark.asyncio
    async def test_batch_claim_ok(self, client):
        """批量认领全部成功：processed=3，pending 清空，pending_count=0。"""
        aid = await _create_account(client, "批认账户")
        csv_text = _csv(
            [
                "2024-02-01 10:00:00,淘宝商城,订单A,88.50,支出\n",
                "2024-02-02 11:00:00,京东,订单B,66.00,支出\n",
                "2024-02-03 12:00:00,拼多多,订单C,12.30,支出\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        ids = await _pending_ids(client, bid)
        assert len(ids) == 3
        cid = await _get_category_id(client, "购物", "expense")
        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": ids, "category_id": cid, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 3
        assert data["failed"] == []
        assert await _pending_ids(client, bid) == []
        resp = await client.get(f"/api/statements/{bid}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_batch_claim_partial(self, client):
        """批量认领部分成功：已认领条目失败。"""
        aid = await _create_account(client, "批认部分账户")
        csv_text = _csv(
            [
                "2024-02-01 10:00:00,淘宝商城,订单A,88.50,支出\n",
                "2024-02-02 11:00:00,京东,订单B,66.00,支出\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        ids = await _pending_ids(client, bid)
        assert len(ids) == 2
        cid = await _get_category_id(client, "购物", "expense")
        first_id = ids[0]
        resp = await client.post(f"/api/statements/items/{first_id}/claim", json={"category_id": cid})
        assert resp.status_code == 200, resp.text
        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": ids, "category_id": cid, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 1
        assert len(data["failed"]) == 1
        assert data["failed"][0]["item_id"] == first_id
        assert "不允许" in data["failed"][0]["error"]

    @pytest.mark.asyncio
    async def test_batch_claim_direction_mismatch(self, client):
        """批量认领方向不匹配：失败明细含方向。"""
        aid = await _create_account(client, "批认方向账户")
        csv_text = _csv(["2024-02-01 10:00:00,淘宝商城,订单A,88.50,支出\n"])
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        ids = await _pending_ids(client, bid)
        cid = await _get_category_id(client, "工资", "income")
        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": ids, "category_id": cid, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 0
        assert len(data["failed"]) == 1
        assert "方向" in data["failed"][0]["error"]

    @pytest.mark.asyncio
    async def test_batch_claim_empty_ids(self, client):
        """批量认领空列表：422 校验失败。"""
        cid = await _get_category_id(client, "购物", "expense")
        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": [], "category_id": cid, "save_rule": False},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_claim_nonexistent_item(self, client):
        """批量认领不存在的条目：失败明细含不存在。"""
        cid = await _get_category_id(client, "购物", "expense")
        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": [999999], "category_id": cid, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 0
        assert len(data["failed"]) == 1
        assert "不存在" in data["failed"][0]["error"]


class TestBatchSkip:
    @pytest.mark.asyncio
    async def test_batch_skip_ok(self, client):
        """批量忽略全部成功：processed=2，pending 清空，pending_count=0。"""
        aid = await _create_account(client, "批跳账户")
        csv_text = _csv(
            [
                "2024-02-01 10:00:00,淘宝商城,订单A,88.50,支出\n",
                "2024-02-02 11:00:00,京东,订单B,66.00,支出\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        ids = await _pending_ids(client, bid)
        assert len(ids) == 2
        resp = await client.post("/api/statements/items/batch-skip", json={"item_ids": ids})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 2
        assert data["failed"] == []
        assert await _pending_ids(client, bid) == []
        resp = await client.get(f"/api/statements/{bid}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["pending_count"] == 0

    @pytest.mark.asyncio
    async def test_batch_skip_partial(self, client):
        """批量忽略部分成功：已忽略条目失败。"""
        aid = await _create_account(client, "批跳部分账户")
        csv_text = _csv(
            [
                "2024-02-01 10:00:00,淘宝商城,订单A,88.50,支出\n",
                "2024-02-02 11:00:00,京东,订单B,66.00,支出\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        ids = await _pending_ids(client, bid)
        assert len(ids) == 2
        first_id = ids[0]
        resp = await client.post(f"/api/statements/items/{first_id}/skip")
        assert resp.status_code == 200, resp.text
        resp = await client.post("/api/statements/items/batch-skip", json={"item_ids": ids})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["processed"] == 1
        assert len(data["failed"]) == 1
        assert data["failed"][0]["item_id"] == first_id


class TestAliasLearning:
    @pytest.mark.asyncio
    async def test_claim_correction_learns_alias(self, client):
        """手工认领一次后，下次同对方名自动按别名命中（match_source=alias）。"""
        aid = await _create_account(client, "别名学习账户")
        cid = await _get_category_id(client, "购物", "expense")
        csv1 = _csv(["2024-03-01 10:00:00,淘宝商城,订单A,88.50,支出\n"])
        bid1 = await _upload(client, aid, csv1)
        resp = await client.post(f"/api/statements/{bid1}/confirm")
        assert resp.status_code == 200, resp.text
        ids1 = await _pending_ids(client, bid1)
        assert len(ids1) == 1
        resp = await client.post(f"/api/statements/items/{ids1[0]}/claim", json={"category_id": cid})
        assert resp.status_code == 200, resp.text

        csv2 = _csv(["2024-03-05 10:00:00,淘宝商城,订单B,33.20,支出\n"])
        bid2 = await _upload(client, aid, csv2)
        resp = await client.post(f"/api/statements/{bid2}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid2}/items", params={"status": "auto"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["match_source"] == "alias"

    @pytest.mark.asyncio
    async def test_alias_learned_on_batch_claim(self, client):
        """批量认领同样触发别名学习：下次同商户账单被别名自动命中。"""
        aid = await _create_account(client, "批量别名账户")
        cid_shop = await _get_category_id(client, "购物", "expense")

        csv1 = _csv([
            "2024-03-01 10:00:00,淘宝商城,订单A,88.50,支出\n",
            "2024-03-01 11:00:00,京东商城,订单B,44.40,支出\n",
        ])
        bid1 = await _upload(client, aid, csv1)
        resp = await client.post(f"/api/statements/{bid1}/confirm")
        assert resp.status_code == 200, resp.text
        ids1 = await _pending_ids(client, bid1)
        assert len(ids1) == 2

        resp = await client.post(
            "/api/statements/items/batch-claim",
            json={"item_ids": ids1, "category_id": cid_shop, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["processed"] == 2
        assert resp.json()["failed"] == []

        csv2 = _csv(["2024-03-06 10:00:00,淘宝商城,订单C,55.50,支出\n"])
        bid2 = await _upload(client, aid, csv2)
        resp = await client.post(f"/api/statements/{bid2}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid2}/items", params={"status": "auto"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["match_source"] == "alias"
        assert items[0]["suggested_category_id"] == cid_shop

    @pytest.mark.asyncio
    async def test_rule_beats_alias(self, client):
        """关键词规则优先级 95 高于别名 85，规则胜出。"""
        aid = await _create_account(client, "规则胜别名账户")
        cid_shop = await _get_category_id(client, "购物", "expense")
        cid_daily = await _get_category_id(client, "日用", "expense")

        csv1 = _csv(["2024-03-01 10:00:00,淘宝商城,订单A,88.50,支出\n"])
        bid1 = await _upload(client, aid, csv1)
        resp = await client.post(f"/api/statements/{bid1}/confirm")
        assert resp.status_code == 200, resp.text
        ids1 = await _pending_ids(client, bid1)
        resp = await client.post(f"/api/statements/items/{ids1[0]}/claim", json={"category_id": cid_shop})
        assert resp.status_code == 200, resp.text

        resp = await client.post(
            "/api/match-rules",
            json={"keyword": "淘宝商城", "category_id": cid_daily, "direction": "out", "priority": 0},
        )
        assert resp.status_code in (200, 201), resp.text

        csv2 = _csv(["2024-03-06 10:00:00,淘宝商城,订单C,55.50,支出\n"])
        bid2 = await _upload(client, aid, csv2)
        resp = await client.post(f"/api/statements/{bid2}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid2}/items", params={"status": "auto"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["match_source"] == "rule"


class TestTransferPair:
    @pytest.mark.asyncio
    async def test_transfer_pair_marks_both(self, client):
        """一出一入金额/日期容差内且对方名为自有账户：双方标记 transfer-pair，置信度 90。"""
        aid = await _create_account(client, "支付宝")
        await _create_account(client, "招商银行")
        csv_text = _csv(
            [
                "2024-04-01 10:00:00,招商银行,提现,5000.00,支出\n",
                "2024-04-02 10:00:00,招商银行,转入,4999.50,收入\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        for it in items:
            assert it["match_source"] == "transfer-pair"
            assert it["confidence"] == 90
            assert it["suggested_action"] == "transfer"

    @pytest.mark.asyncio
    async def test_transfer_pair_amount_beyond_tol(self, client):
        """金额超容差：不配对，回退 match_source=none。"""
        aid = await _create_account(client, "支付宝2")
        await _create_account(client, "招商银行2")
        csv_text = _csv(
            [
                "2024-04-01 10:00:00,招商银行2,提现,5000.00,支出\n",
                "2024-04-02 10:00:00,招商银行2,转入,4900.00,收入\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        for it in items:
            assert it["match_source"] == "none"
            assert it["suggested_action"] == "transfer"

    @pytest.mark.asyncio
    async def test_transfer_pair_date_beyond_window(self, client):
        """日期超窗口：不配对，match_source=none。"""
        aid = await _create_account(client, "支付宝3")
        await _create_account(client, "招商银行3")
        csv_text = _csv(
            [
                "2024-04-01 10:00:00,招商银行3,提现,5000.00,支出\n",
                "2024-04-10 10:00:00,招商银行3,转入,4999.50,收入\n",
            ]
        )
        bid = await _upload(client, aid, csv_text)
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        for it in items:
            assert it["match_source"] == "none"
