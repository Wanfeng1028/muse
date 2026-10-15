# tests/test_statements_api.py
"""银行账单侦探 API 集成测试：模板 CRUD / 预览 / 上传确认 / 认领学习 / 转账 / 去重 / 错误。"""
import pytest


async def _create_account(client, name, opening=0):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": opening},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_ewallet_account(client, name):
    resp = await client.post("/api/accounts", json={"name": name, "type": "ewallet"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _get_category_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for item in resp.json():
        if item["name"] == name:
            return item["id"]
    raise AssertionError(f"category not found: {name}/{kind}")


ALIPAY_CSV = """支付宝交易记录明细查询
账号:[test@example.com]
起始日期:[2024-01-01 00:00:00]    终止日期:[2024-01-31 23:59:59]
---------------------------------交易记录明细列表------------------------------------
交易创建时间,交易对方,商品说明,金额（元）,收/支
2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出
2024-01-03 12:30:00,某公司,工资,8000.00,收入
"""


class TestTemplatesBuiltinAndCrud:
    """模板内置与增删。"""

    @pytest.mark.asyncio
    async def test_builtin_and_crud(self, client):
        # 1. 4 个内置
        resp = await client.get("/api/statement-templates")
        assert resp.status_code == 200, resp.text
        builtins = [t for t in resp.json() if t.get("builtin")]
        assert len(builtins) == 4

        # 2. 建自定义 → 201
        payload = {
            "name": "我的银行",
            "source": "custom",
            "mapping": {"date": "日期", "amount": "金额", "counterparty": "对方", "summary": "备注"},
        }
        resp = await client.post("/api/statement-templates", json=payload)
        assert resp.status_code == 201, resp.text
        new_id = resp.json()["id"]

        # 3. 重名 → 409
        resp = await client.post("/api/statement-templates", json=payload)
        assert resp.status_code == 409, resp.text

        # 4. 缺 date 的 mapping → 422
        bad = {"name": "坏模板", "source": "custom", "mapping": {"amount": "金额"}}
        resp = await client.post("/api/statement-templates", json=bad)
        assert resp.status_code == 422, resp.text

        # 5. 删内置 → 404
        builtin_id = builtins[0]["id"]
        resp = await client.delete(f"/api/statement-templates/{builtin_id}")
        assert resp.status_code == 404, resp.text

        # 6. 删自定义 → 200 {"ok": true}
        resp = await client.delete(f"/api/statement-templates/{new_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("ok") is True


class TestParsePreviewAlipay:
    """支付宝 CSV 预览：自动识别模板并抽样。"""

    @pytest.mark.asyncio
    async def test_parse_preview_alipay(self, client):
        files = {"file": ("alipay.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}
        resp = await client.post("/api/statements/parse-preview", files=files)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "encoding" in data
        assert "headers" in data
        assert "mapping" in data
        assert "template_name" in data
        assert "total_rows" in data
        assert "sample" in data
        assert "errors" in data

        assert data["total_rows"] == 2
        assert any(v == "交易创建时间" for v in data["mapping"].values())
        assert data["template_name"]

        # sample 中 direction 应为 'out' / 'in'
        directions = {s.get("direction") for s in data["sample"]}
        assert "out" in directions or "in" in directions


class TestUploadConfirmRuleAuto:
    """上传 + 确认：规则命中条目自动入账。"""

    @pytest.mark.asyncio
    async def test_upload_confirm_rule_auto(self, client):
        aid = await _create_account(client, "规则账户")
        cat_id = await _get_category_id(client, "餐饮", "expense")

        # 建规则：星巴克 → 餐饮
        rule = {"keyword": "星巴克", "category_id": cat_id, "direction": "out", "priority": 1}
        resp = await client.post("/api/match-rules", json=rule)
        assert resp.status_code == 201, resp.text

        # 上传
        files = {"file": ("alipay.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        up = resp.json()
        bid = up["batch"]["id"]
        assert up["parsed"] == 2

        # 确认
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text
        conf = resp.json()
        assert conf["auto_count"] >= 1
        assert conf["pending_count"] >= 1

        # 规则命中的条目 status=auto
        resp = await client.get(f"/api/statements/{bid}/items")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        auto_items = [it for it in items if it["status"] == "auto"]
        assert len(auto_items) >= 1

        # 交易已建：查 /api/transactions
        resp = await client.get("/api/transactions")
        assert resp.status_code == 200, resp.text
        txs = resp.json()
        assert len(txs) >= 1


class TestClaimAndLearn:
    """认领即学习闭环。"""

    @pytest.mark.asyncio
    async def test_claim_and_learn(self, client):
        aid = await _create_account(client, "学习账户")
        cat_id = await _get_category_id(client, "餐饮", "expense")

        # 第一份账单
        files = {"file": ("alipay.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        bid = resp.json()["batch"]["id"]

        await client.post(f"/api/statements/{bid}/confirm")

        resp = await client.get(
            f"/api/statements/{bid}/items", params={"status": "pending"}
        )
        assert resp.status_code == 200, resp.text
        pending = resp.json()["items"]
        target = next(it for it in pending if "星巴克" in (it.get("counterparty") or ""))
        iid = target["id"]

        # 认领并保存规则
        resp = await client.post(
            f"/api/statements/items/{iid}/claim",
            json={"category_id": cat_id, "save_rule": True},
        )
        assert resp.status_code == 200, resp.text

        # 规则表应多一条
        resp = await client.get("/api/match-rules")
        assert resp.status_code == 200, resp.text
        rules = resp.json()
        assert any(r["keyword"] and "星巴克" in r["keyword"] for r in rules)

        # 再上传同商户新账单（注意：日期不同才是新交易，完全相同的行会被去重）
        second = ALIPAY_CSV.replace("2024-01-02 10:00:00", "2024-01-04 10:00:00")
        files = {"file": ("alipay2.csv", second.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        bid2 = resp.json()["batch"]["id"]

        resp = await client.post(f"/api/statements/{bid2}/confirm")
        assert resp.status_code == 200, resp.text
        assert resp.json()["auto_count"] >= 1


class TestClaimTransfer:
    """账户名匹配 → 转账认领。"""

    @pytest.mark.asyncio
    async def test_claim_transfer(self, client):
        aid = await _create_account(client, "主账户")
        other = await _create_ewallet_account(client, "支付宝")

        csv = (
            "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
            "2024-01-05 09:00:00,支付宝,提现,-500.00,支出\n"
        )
        files = {"file": ("t.csv", csv.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        bid = resp.json()["batch"]["id"]

        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/statements/{bid}/items")
        items = resp.json()["items"]
        assert items
        target = items[0]
        assert target.get("suggested_action") == "transfer"

        resp = await client.post(
            f"/api/statements/items/{target['id']}/claim-transfer",
            json={"to_account_id": other},
        )
        assert resp.status_code == 200, resp.text

        resp = await client.get("/api/transactions")
        assert resp.status_code == 200, resp.text
        txs = resp.json()["items"]
        assert any(t["type"] == "transfer" for t in txs)


class TestDuplicates:
    """同一文件二次上传应去重。"""

    @pytest.mark.asyncio
    async def test_duplicates(self, client):
        aid = await _create_account(client, "去重账户")
        files = {"file": ("d.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}

        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        first = resp.json()
        bid = first["batch"]["id"]
        await client.post(f"/api/statements/{bid}/confirm")

        files = {"file": ("d.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        second = resp.json()
        assert second["duplicates_skipped"] > 0
        assert second["parsed"] == 0


class TestClaimErrors:
    """认领错误分支。"""

    @pytest.mark.asyncio
    async def test_claim_errors(self, client):
        aid = await _create_account(client, "错误账户")
        cat_id = await _get_category_id(client, "餐饮", "expense")
        income_cat = await _get_category_id(client, "工资", "income")

        files = {"file": ("e.csv", ALIPAY_CSV.encode("utf-8"), "text/csv")}
        resp = await client.post(
            "/api/statements/upload", files=files, data={"account_id": str(aid)}
        )
        assert resp.status_code == 200, resp.text
        bid = resp.json()["batch"]["id"]
        await client.post(f"/api/statements/{bid}/confirm")

        resp = await client.get(f"/api/statements/{bid}/items", params={"status": "pending"})
        pending = resp.json()["items"]
        assert pending
        iid = pending[0]["id"]

        # 方向不匹配：支出条目用收入分类
        resp = await client.post(
            f"/api/statements/items/{iid}/claim",
            json={"category_id": income_cat, "save_rule": False},
        )
        assert resp.status_code == 400, resp.text

        # 正确认领一次
        resp = await client.post(
            f"/api/statements/items/{iid}/claim",
            json={"category_id": cat_id, "save_rule": False},
        )
        assert resp.status_code == 200, resp.text

        # 重复 claim → 400
        resp = await client.post(
            f"/api/statements/items/{iid}/claim",
            json={"category_id": cat_id, "save_rule": False},
        )
        assert resp.status_code == 400, resp.text

        # 不存在的条目 → 404
        resp = await client.post(
            "/api/statements/items/999999/claim",
            json={"category_id": cat_id, "save_rule": False},
        )
        assert resp.status_code == 404, resp.text
