
import pytest

from ledger import matching

ALIPAY_CSV = """支付宝交易记录明细查询
账号:[test@example.com]
起始日期:[2024-01-01 00:00:00]    终止日期:[2024-01-31 23:59:59]
---------------------------------交易记录明细列表------------------------------------
交易创建时间,交易对方,商品说明,金额（元）,收/支
2024-01-02 10:00:00,星巴克,拿铁咖啡,32.00,支出
2024-01-03 12:30:00,某公司,工资,8000.00,收入
"""


async def _create_account(client, name, opening=0):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": opening},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _get_category_id(client, name, kind="expense"):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    raise AssertionError(f"category not found: {name}")


async def _claim_counterparty(client, csv_text, counterparty, category_id, account_name):
    aid = await _create_account(client, account_name)
    files = {"file": ("alipay.csv", csv_text.encode("utf-8"), "text/csv")}
    resp = await client.post(
        "/api/statements/upload", files=files, data={"account_id": str(aid)}
    )
    assert resp.status_code == 200, resp.text
    bid = resp.json()["batch"]["id"]

    resp = await client.post(f"/api/statements/{bid}/confirm")
    assert resp.status_code == 200, resp.text

    resp = await client.get(
        f"/api/statements/{bid}/items", params={"status": "pending"}
    )
    assert resp.status_code == 200, resp.text
    pending = resp.json()["items"]
    target = next(
        it for it in pending if counterparty in (it.get("counterparty") or "")
    )
    iid = target["id"]

    resp = await client.post(
        f"/api/statements/items/{iid}/claim", json={"category_id": category_id}
    )
    assert resp.status_code == 200, resp.text


async def _claim_starbucks(client, account_name="别名账户"):
    cat_id = await _get_category_id(client, "餐饮", "expense")
    await _claim_counterparty(
        client, ALIPAY_CSV, "星巴克", cat_id, account_name
    )
    resp = await client.get("/api/merchant-aliases")
    assert resp.status_code == 200, resp.text
    aliases = resp.json()
    assert len(aliases) >= 1
    target = next(
        a for a in aliases if a["category_name"] == "餐饮" and a["direction"] == "out"
    )
    return target["id"], cat_id


class TestMerchantAliases:
    @pytest.mark.asyncio
    async def test_learn_then_list(self, client):
        await _claim_starbucks(client)
        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        aliases = resp.json()
        assert len(aliases) == 1
        a = aliases[0]
        assert isinstance(a["alias"], str) and a["alias"] != ""
        assert a["category_name"] == "餐饮"
        assert a["direction"] == "out"

    @pytest.mark.asyncio
    async def test_update_category(self, client):
        alias_id, _ = await _claim_starbucks(client)
        resp = await client.get("/api/categories", params={"kind": "expense"})
        assert resp.status_code == 200, resp.text
        cats = resp.json()
        other = next(c for c in cats if c["name"] == "交通") if any(
            c["name"] == "交通" for c in cats
        ) else next(c for c in cats if c["name"] != "餐饮")
        new_cat_id = other["id"]

        resp = await client.patch(
            f"/api/merchant-aliases/{alias_id}", json={"category_id": new_cat_id}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["category_id"] == new_cat_id
        assert body["category_name"] == other["name"]

        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        listed = next(a for a in resp.json() if a["id"] == alias_id)
        assert listed["category_id"] == new_cat_id
        assert listed["category_name"] == other["name"]

    @pytest.mark.asyncio
    async def test_rename_alias(self, client):
        alias_id, _ = await _claim_starbucks(client)
        new_alias = "星巴克咖啡"
        resp = await client.patch(
            f"/api/merchant-aliases/{alias_id}", json={"alias": new_alias}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["alias"] == matching.normalize(new_alias)

        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        listed = next(a for a in resp.json() if a["id"] == alias_id)
        assert listed["alias"] == matching.normalize(new_alias)

    @pytest.mark.asyncio
    async def test_update_404(self, client):
        cat_id = await _get_category_id(client, "餐饮", "expense")
        resp = await client.patch(
            "/api/merchant-aliases/999999", json={"category_id": cat_id}
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_update_400_empty(self, client):
        alias_id, _ = await _claim_starbucks(client)
        resp = await client.patch(f"/api/merchant-aliases/{alias_id}", json={})
        assert resp.status_code == 400, resp.text

        resp = await client.patch(
            f"/api/merchant-aliases/{alias_id}", json={"alias": "   "}
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_update_409_conflict(self, client):
        first_id, _ = await _claim_starbucks(client)
        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        first = next(a for a in resp.json() if a["id"] == first_id)
        first_alias = first["alias"]

        # 第二份：瑞幸
        cat_id = await _get_category_id(client, "餐饮", "expense")
        csv_text = ALIPAY_CSV.replace("星巴克", "瑞幸").replace(
            "2024-01-02 10:00:00", "2024-01-04 10:00:00"
        )
        await _claim_counterparty(client, csv_text, "瑞幸", cat_id, "别名账户2")

        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        aliases = resp.json()
        assert len(aliases) == 2
        second = next(a for a in aliases if a["id"] != first_id)

        resp = await client.patch(
            f"/api/merchant-aliases/{second['id']}", json={"alias": first_alias}
        )
        assert resp.status_code == 409, resp.text

    @pytest.mark.asyncio
    async def test_delete(self, client):
        first_id, _ = await _claim_starbucks(client)
        cat_id = await _get_category_id(client, "餐饮", "expense")
        csv_text = ALIPAY_CSV.replace("星巴克", "瑞幸").replace(
            "2024-01-02 10:00:00", "2024-01-04 10:00:00"
        )
        await _claim_counterparty(client, csv_text, "瑞幸", cat_id, "别名账户2")

        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        aliases = resp.json()
        assert len(aliases) == 2
        second = next(a for a in aliases if a["id"] != first_id)

        resp = await client.delete(f"/api/merchant-aliases/{second['id']}")
        assert resp.status_code == 200, resp.text
        assert resp.json().get("ok") is True

        resp = await client.get("/api/merchant-aliases")
        assert resp.status_code == 200, resp.text
        remaining = resp.json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == first_id

        resp = await client.delete(f"/api/merchant-aliases/{second['id']}")
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_update_bad_category(self, client):
        alias_id, _ = await _claim_starbucks(client)
        resp = await client.patch(
            f"/api/merchant-aliases/{alias_id}", json={"category_id": 999999}
        )
        assert resp.status_code == 404, resp.text
