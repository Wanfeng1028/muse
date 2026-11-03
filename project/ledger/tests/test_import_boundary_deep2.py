"""导入边界深度测试：解码、金额、日期与上传端到端。

覆盖 decode_bytes、parse_amount_cents、parse_date 的边界，
以及 POST /api/statements/upload 的真实 multipart 端到端行为。
"""

import pytest
from httpx import AsyncClient

from ledger.statement_parser import (
    decode_bytes,
    parse_amount_cents,
    parse_date,
)


# ---------------------------------------------------------------------------
# A. decode_bytes 解码优先级
# ---------------------------------------------------------------------------


def test_decode_bytes_gbk_real_bytes():
    """真实 GBK 字节应被识别为 gbk，且文本含中文表头。"""
    raw = "交易日期,人民币金额\n2026-09-01,100.00".encode("gbk")
    text, encoding = decode_bytes(raw)
    assert encoding == "gbk"
    assert "交易日期" in text
    assert "2026-09-01,100.00" in text


def test_decode_bytes_utf8_bom_stripped():
    """带 BOM 的 UTF-8 字节应识别为 utf-8-sig，且文本不含 BOM 字符。"""
    raw = "\ufeff交易日期".encode("utf-8")
    text, encoding = decode_bytes(raw)
    assert encoding == "utf-8-sig"
    assert "\ufeff" not in text
    assert text == "交易日期"


def test_decode_bytes_pure_ascii():
    """纯 ASCII 文本按首选编码 utf-8-sig 解码，内容保持一致。"""
    raw = b"date,amount\n2026-09-01,100.00"
    text, encoding = decode_bytes(raw)
    assert encoding == "utf-8-sig"
    assert text == "date,amount\n2026-09-01,100.00"


# ---------------------------------------------------------------------------
# B. parse_amount_cents 金额解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234.56", 123456),
        ("(1,234.56)", 123456),
        ("¥1,234.56", 123456),
        ("￥2,000", 200000),
        ("1,234.56元", 123456),
        ("-88.5", 8850),
        ("+100", 10000),
        ("0.01", 1),
        ("  66.60  ", 6660),
        ("1，234.56", 123456),
    ],
)
def test_parse_amount_cents_valid(raw, expected):
    """各种合法金额格式应精确解析为整数分。"""
    assert parse_amount_cents(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "",
        "0",
        "12.34.56",
    ],
)
def test_parse_amount_cents_invalid(raw):
    """非法金额文本应抛出 ValueError。"""
    with pytest.raises(ValueError):
        parse_amount_cents(raw)


# ---------------------------------------------------------------------------
# C. parse_date 日期解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026年9月5日", "2026-09-05"),
        ("20260905", "2026-09-05"),
        ("2026/09/05", "2026-09-05"),
    ],
)
def test_parse_date_valid(raw, expected):
    """多种日期写法应归一化为 YYYY-MM-DD。"""
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "2026-13-01",
        "",
    ],
)
def test_parse_date_invalid(raw):
    """非法日期文本应抛出 ValueError。"""
    with pytest.raises(ValueError):
        parse_date(raw)


# ---------------------------------------------------------------------------
# D. 上传接口端到端
# ---------------------------------------------------------------------------


MAPPING = {
    "date": "交易日期",
    "summary": "交易摘要",
    "amount": "人民币金额",
}

CSV_HEADER = "交易日期,交易摘要,人民币金额"

CSV_ROWS = [
    "2026-09-01,财付通-美团,\"1,234.56\"",
    "2026-09-02,消费退款,(200.00)",
    "2026-09-03,扫码支付,￥88.50",
    "2026-09-04,超市购物,66.60",
    "2026年9月5日,餐饮,100.00",
]


async def _create_savings_account(client: AsyncClient) -> int:
    """创建储蓄账户并返回其 id。"""
    resp = await client.post(
        "/api/accounts",
        json={"name": "招商储蓄", "type": "savings"},
    )
    assert resp.status_code in (200, 201)
    return resp.json()["id"]


def _build_cmb_csv_bytes() -> bytes:
    """构造招商银行风格 CSV 的 GBK 字节，含 5 行数据。"""
    lines = [CSV_HEADER, *CSV_ROWS]
    return ("\n".join(lines) + "\n").encode("gbk")


async def _upload_csv(
    client: AsyncClient,
    account_id: int,
    raw: bytes,
):
    """以真实 multipart 上传 CSV 字节（显式 mapping，不传 template_id）。"""
    files = {"file": ("cmb.csv", raw, "text/csv")}
    data = {
        "account_id": str(account_id),
        "mapping": __import__("json").dumps(MAPPING),
    }
    return await client.post("/api/statements/upload", files=files, data=data)


async def test_upload_cmb_gbk_parsed_five(client: AsyncClient):
    """GBK 招商账单上传成功，解析 5 行且无错误。"""
    account_id = await _create_savings_account(client)
    raw = _build_cmb_csv_bytes()
    resp = await _upload_csv(client, account_id, raw)
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"] == 5
    assert body["errors"] == []


async def test_upload_same_file_twice_dedup(client: AsyncClient):
    """同文件二次上传，全部行被判重，parsed 为 0。"""
    account_id = await _create_savings_account(client)
    raw = _build_cmb_csv_bytes()
    first = await _upload_csv(client, account_id, raw)
    assert first.status_code == 200
    assert first.json()["parsed"] == 5

    second = await _upload_csv(client, account_id, raw)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["duplicates_skipped"] == 5
    assert second_body["parsed"] == 0


async def test_upload_account_not_found(client: AsyncClient):
    """上传到不存在的账户应返回 404。"""
    raw = _build_cmb_csv_bytes()
    resp = await _upload_csv(client, 999999999, raw)
    assert resp.status_code == 404


async def test_upload_duplicate_rows_within_batch(client: AsyncClient):
    """同批次内除行号外完全相同的两行，第二行被判重。

    依据：fingerprint 由业务字段（账户、日期、摘要、金额等）计算，
    行号不参与指纹，因此完全相同的两行只有一行计入 parsed，
    另一行计入 duplicates_skipped。
    """
    account_id = await _create_savings_account(client)
    duplicate_row = "2026-09-10,重复消费,50.00"
    lines = [CSV_HEADER, duplicate_row, duplicate_row]
    raw = ("\n".join(lines) + "\n").encode("gbk")

    resp = await _upload_csv(client, account_id, raw)
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"] == 1
    assert body["duplicates_skipped"] == 1
