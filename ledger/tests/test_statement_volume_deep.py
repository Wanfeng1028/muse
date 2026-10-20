"""真实银行流水大批量导入深测。

背景：CHANGELOG v2.11 诚实记录"冒烟未覆盖真实银行流水大批量场景，相关验证待后续执行"。
本文件用程序生成的 1500 行支付宝账单与 800 行 GBK 招行账单（含表尾脏行、千分位、
括号退款），走 parse-preview -> upload -> confirm 全链路，验证记录/错误拆分、
行号、指纹去重与耗时。
"""


import time

ALIPAY_HEADERS = "交易创建时间,交易对方,商品说明,金额（元）,收/支"
MERCHANTS = ["星巴克", "美团外卖", "滴滴出行", "京东", "盒马鲜生"]


def _build_alipay_csv(n=1500):
    lines = [ALIPAY_HEADERS]
    for i in range(n):
        day = (i % 28) + 1
        merchant = MERCHANTS[i % len(MERCHANTS)]
        amount = 10 + i * 1.37
        if i % 2 == 0:
            amount_text = f'"{amount:,.2f}"'
        else:
            amount_text = f"{amount:.2f}"
        direction = "收入" if i % 3 == 0 else "支出"
        line = f"2026-09-{day:02d} 12:00:00,{merchant},商品-{i},{amount_text},{direction}"
        lines.append(line)
    return "\n".join(lines).encode("utf-8")


def _build_cmb_gbk_csv(n=800):
    lines = ["交易日期,交易摘要,人民币金额"]
    summaries = ["工资", "房租", "餐饮", "交通", "退款"]
    for i in range(n):
        day = (i % 28) + 1
        summary = summaries[i % len(summaries)]
        amount = 100 + i * 2.33
        if i % 5 == 4:
            amount_text = f"({amount:.2f})"
        elif i % 2 == 0:
            amount_text = f'"-{amount:,.2f}"'
        else:
            amount_text = f'"{amount:,.2f}"'
        lines.append(f"202609{day:02d},{summary},{amount_text}")
    # 真实导出常见的表尾脏行：空行、合计行、查询时间行
    lines.append("")
    lines.append('合计,800笔,"-12,345.67"')
    lines.append("查询时间：2026-10-01 10:00:00,,")
    return "\n".join(lines).encode("gbk")


async def _create_account(client, name):
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_alipay_large_volume_pipeline(client):
    """1500 行支付宝账单全链路：预览 -> 上传 -> 确认，记录数/方向/耗时断言。"""
    aid = await _create_account(client, "体积账户")
    payload = _build_alipay_csv(1500)

    t0 = time.monotonic()
    resp = await client.post(
        "/api/statements/parse-preview",
        files={"file": ("alipay-big.csv", payload, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["total_rows"] == 1500, preview["total_rows"]
    assert preview["errors"] == [], preview["errors"][:3]
    assert preview["template_name"] == "支付宝", preview["template_name"]

    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("alipay-big.csv", payload, "text/csv")},
        data={"account_id": str(aid)},
    )
    assert resp.status_code == 200, resp.text
    up = resp.json()
    assert up["parsed"] == 1500, up
    assert up["duplicates_skipped"] == 0, up
    assert up["batch"]["total_count"] == 1500
    bid = up["batch"]["id"]

    resp = await client.post(f"/api/statements/{bid}/confirm")
    assert resp.status_code == 200, resp.text
    batch = resp.json()
    assert batch["auto_count"] + batch["pending_count"] == 1500, batch
    elapsed = time.monotonic() - t0
    print(f"\n1500-row pipeline took {elapsed:.1f}s")
    assert elapsed < 60, f"pipeline too slow: {elapsed:.1f}s"


async def test_cmb_gbk_with_footer_rows(client):
    """GBK 招行账单：编码识别、表尾脏行进 errors（不 500）、行号指向脏行。"""
    aid = await _create_account(client, "招行账户")
    payload = _build_cmb_gbk_csv(800)

    resp = await client.post(
        "/api/statements/parse-preview",
        files={"file": ("cmb-big.csv", payload, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    preview = resp.json()
    assert preview["encoding"] == "gbk", preview["encoding"]
    assert preview["errors"], "footer rows should be collected as errors"
    assert preview["total_rows"] >= 801, preview["total_rows"]

    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("cmb-big.csv", payload, "text/csv")},
        data={"account_id": str(aid)},
    )
    assert resp.status_code == 200, resp.text
    up = resp.json()
    assert up["parsed"] == 800, up
    for e in up["errors"]:
        assert "row" in e and e["row"] > 800, e

    # 方向抽查：括号退款与负号金额应为支出
    dir_csv = (
        "交易日期,交易摘要,人民币金额\n"
        "20260901,退款,(200.00)\n"
        '20260902,消费,"-1,234.56"\n'
        '20260903,工资,"5,000.00"\n'
    ).encode("gbk")
    resp = await client.post(
        "/api/statements/parse-preview",
        files={"file": ("cmb-dir.csv", dir_csv, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    sample = resp.json()["sample"]
    got = [(r["amount_cents"], r["direction"]) for r in sample]
    assert got == [(20000, "out"), (123456, "out"), (500000, "in")], got


async def test_reimport_dedup(client):
    """同一份账单重复上传：第二次全部判重，parsed 为 0。"""
    aid = await _create_account(client, "去重账户")
    payload = _build_cmb_gbk_csv(800)

    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("cmb-dedup.csv", payload, "text/csv")},
        data={"account_id": str(aid)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["parsed"] == 800

    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("cmb-dedup.csv", payload, "text/csv")},
        data={"account_id": str(aid)},
    )
    assert resp.status_code == 200, resp.text
    up = resp.json()
    assert up["parsed"] == 0, up
    assert up["duplicates_skipped"] == 800, up


async def test_parenthesized_refund_direction(client):
    """括号负数退款的方向与金额解析（支付宝模板）。"""
    aid = await _create_account(client, "方向账户")
    csv = (
        "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
        "2026-09-01 10:00:00,某商户,退款,(200.00),支出\n"
        "2026-09-02 10:00:00,某商户,消费,300.00,支出\n"
        '2026-09-03 10:00:00,公司,工资,"5,000.00",收入\n'
    ).encode()
    resp = await client.post(
        "/api/statements/parse-preview",
        files={"file": ("refund.csv", csv, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    sample = resp.json()["sample"]
    got = [(r["amount_cents"], r["direction"]) for r in sample]
    assert got == [(20000, "out"), (30000, "out"), (500000, "in")], got
    assert aid > 0
