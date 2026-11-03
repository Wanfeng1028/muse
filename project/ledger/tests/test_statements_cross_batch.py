"""跨批次转账配对（transfer-pair-xbatch）的 API 级集成测试。

覆盖：跨批次回标、与同批次配对互斥、金额容差、同批次优先、幂等性。
"""

import io


def _csv_bytes(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    """把 (时间, 对方, 摘要, 金额, 收支) 行拼成上传用 CSV 字节。"""
    header = "交易创建时间,交易对方,商品说明,金额（元）,收/支\n"
    body = "".join(",".join(r) + "\n" for r in rows)
    return (header + body).encode("utf-8")


async def _new_account(client, name: str) -> int:
    """创建现金账户并返回 id。"""
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _upload(client, account_id: int, filename: str, rows) -> int:
    """上传账单 CSV 并返回批次 id。"""
    resp = await client.post(
        "/api/statements/upload",
        files={"file": (filename, io.BytesIO(_csv_bytes(rows)), "text/csv")},
        data={"account_id": str(account_id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["batch"]["id"]


async def _confirm(client, batch_id: int) -> None:
    """确认批次。"""
    resp = await client.post(f"/api/statements/{batch_id}/confirm")
    assert resp.status_code == 200, resp.text


async def _items(client, batch_id: int, status: str = "pending") -> list[dict]:
    """取批次下指定状态的条目。"""
    resp = await client.get(f"/api/statements/{batch_id}/items?status={status}")
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_cross_batch_pair_marks_both(client):
    """跨批次配对：新批次条目与老批次条目都被标记为 transfer-pair-xbatch。"""
    acc_a = await _new_account(client, "支付宝X")
    acc_b = await _new_account(client, "招商银行X")

    bid1 = await _upload(
        client,
        acc_a,
        "b1.csv",
        [("2024-04-01 10:00:00", "招商银行X", "提现", "5000.00", "支出")],
    )
    await _confirm(client, bid1)
    items1 = await _items(client, bid1)
    assert len(items1) == 1
    # 批次内无对手方，先标 none
    assert items1[0]["match_source"] == "none"

    bid2 = await _upload(
        client,
        acc_b,
        "b2.csv",
        [("2024-04-02 09:00:00", "支付宝X", "转入", "4999.50", "收入")],
    )
    await _confirm(client, bid2)
    items2 = await _items(client, bid2)
    assert len(items2) == 1
    assert items2[0]["match_source"] == "transfer-pair-xbatch"
    assert items2[0]["confidence"] == 90

    # 老批次条目被回标，但 status 仍为 pending
    items1_after = await _items(client, bid1, status="pending")
    assert len(items1_after) == 1
    assert items1_after[0]["match_source"] == "transfer-pair-xbatch"
    assert items1_after[0]["confidence"] == 90
    assert items1_after[0]["status"] == "pending"


async def test_cross_batch_paired_items_excluded(client):
    """跨批次互斥：同批次已配对占用的条目不再被跨批次认领。"""
    acc_a = await _new_account(client, "支付宝Y")
    acc_b = await _new_account(client, "招商银行Y")

    # 批次1：同批次一出一入可自配（对方名互指自有账户）
    bid1 = await _upload(
        client,
        acc_a,
        "b1.csv",
        [
            ("2024-05-01 10:00:00", "招商银行Y", "转出", "3000.00", "支出"),
            ("2024-05-01 12:00:00", "招商银行Y", "转入", "3000.00", "收入"),
        ],
    )
    await _confirm(client, bid1)
    items1 = await _items(client, bid1)
    assert len(items1) == 2
    assert all(it["match_source"] == "transfer-pair" for it in items1)

    # 批次2：再来一条 in，金额/日期与批次1的 out 可配，但对方已被占用
    bid2 = await _upload(
        client,
        acc_b,
        "b2.csv",
        [("2024-05-01 11:00:00", "支付宝Y", "转入", "3000.00", "收入")],
    )
    await _confirm(client, bid2)
    items2 = await _items(client, bid2)
    assert len(items2) == 1
    assert items2[0]["match_source"] == "none"

    items1_after = await _items(client, bid1)
    assert all(it["match_source"] == "transfer-pair" for it in items1_after)


async def test_cross_batch_amount_beyond_tol(client):
    """跨批次金额差超容差：不配对，双方均为 none。"""
    acc_a = await _new_account(client, "支付宝Z")
    acc_b = await _new_account(client, "招商银行Z")

    bid1 = await _upload(
        client,
        acc_a,
        "b1.csv",
        [("2024-06-01 10:00:00", "招商银行Z", "提现", "5000.00", "支出")],
    )
    await _confirm(client, bid1)

    bid2 = await _upload(
        client,
        acc_b,
        "b2.csv",
        [("2024-06-02 09:00:00", "支付宝Z", "转入", "4000.00", "收入")],
    )
    await _confirm(client, bid2)

    items2 = await _items(client, bid2)
    assert len(items2) == 1
    assert items2[0]["match_source"] == "none"

    items1 = await _items(client, bid1)
    assert len(items1) == 1
    assert items1[0]["match_source"] == "none"


async def test_same_batch_takes_precedence(client):
    """同批次优先：同批次能配上时，不抢用老批次条目。"""
    acc_a = await _new_account(client, "支付宝W")
    acc_b = await _new_account(client, "招商银行W")

    # 批次1：一个旧 out
    bid1 = await _upload(
        client,
        acc_a,
        "b1.csv",
        [("2024-07-01 10:00:00", "招商银行W", "转出", "2000.00", "支出")],
    )
    await _confirm(client, bid1)
    items1 = await _items(client, bid1)
    assert items1[0]["match_source"] == "none"

    # 批次2：本批次内 out+in 可自配，同时 in 也能与批次1旧 out 配对
    bid2 = await _upload(
        client,
        acc_b,
        "b2.csv",
        [
            ("2024-07-01 11:00:00", "支付宝W", "转入", "2000.00", "收入"),
            ("2024-07-01 12:00:00", "支付宝W", "转出", "2000.00", "支出"),
        ],
    )
    await _confirm(client, bid2)
    items2 = await _items(client, bid2)
    assert len(items2) == 2
    assert all(it["match_source"] == "transfer-pair" for it in items2)

    # 批次1旧条目保持 none
    items1_after = await _items(client, bid1)
    assert len(items1_after) == 1
    assert items1_after[0]["match_source"] == "none"


async def test_cross_batch_idempotent(client):
    """幂等性：重复读取两批次条目，标记与状态均稳定。"""
    acc_a = await _new_account(client, "支付宝V")
    acc_b = await _new_account(client, "招商银行V")

    bid1 = await _upload(
        client,
        acc_a,
        "b1.csv",
        [("2024-08-01 10:00:00", "招商银行V", "提现", "1500.00", "支出")],
    )
    await _confirm(client, bid1)

    bid2 = await _upload(
        client,
        acc_b,
        "b2.csv",
        [("2024-08-02 09:00:00", "支付宝V", "转入", "1500.00", "收入")],
    )
    await _confirm(client, bid2)

    first2 = await _items(client, bid2)
    first1 = await _items(client, bid1)
    assert first2[0]["match_source"] == "transfer-pair-xbatch"
    assert first1[0]["match_source"] == "transfer-pair-xbatch"

    # 再次读取，标记稳定；批次2条目 status 仍为 pending
    again2 = await _items(client, bid2)
    again1 = await _items(client, bid1)
    assert again2[0]["match_source"] == "transfer-pair-xbatch"
    assert again2[0]["confidence"] == 90
    assert again2[0]["status"] == "pending"
    assert again1[0]["match_source"] == "transfer-pair-xbatch"
    assert again1[0]["confidence"] == 90
    assert again1[0]["status"] == "pending"
