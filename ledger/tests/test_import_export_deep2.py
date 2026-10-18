from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from ledger.services import import_csv_rows


def _make_csv_bytes(rows: list[list[str]], header: list[str] | None = None) -> bytes:
    if header is None:
        header = ["date", "type", "account", "category", "amount"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


async def _create_account(client, name: str, type_: str = "cash") -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": name, "type": type_, "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _import(client, csv_bytes: bytes):
    return await client.post(
        "/api/import/csv",
        files={"file": ("import.csv", csv_bytes, "text/csv")},
    )


@pytest.mark.asyncio
async def test_import_two_rows_income_and_expense_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["2024-01-02", "支出", "现金", "餐饮", "30"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_header_missing_columns_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "100"]],
        header=["date", "type", "account", "amount"],
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert any("表头缺少必需列" in e for e in body["errors"])


@pytest.mark.asyncio
async def test_import_blank_lines_skipped_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["", "", "", "", ""],
            ["2024-01-01", "收入", "现金", "工资", "50"],
            ["", "", "", "", ""],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 2
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_bad_date_recorded_and_good_row_imported_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024/01/01", "收入", "现金", "工资", "100"],
            ["2024-01-02", "收入", "现金", "工资", "100"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
    assert any("日期格式无效" in e for e in body["errors"])
    assert any(e.startswith("第2行") for e in body["errors"])


@pytest.mark.asyncio
async def test_import_invalid_type_recorded_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "购物", "现金", "餐饮", "10"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert any("交易类型无效" in e for e in body["errors"])


@pytest.mark.asyncio
async def test_import_non_positive_amount_recorded_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "支出", "现金", "餐饮", "0"],
            ["2024-01-02", "支出", "现金", "餐饮", "-5"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 2
    assert sum(1 for e in body["errors"] if "金额必须大于 0" in e) == 2


@pytest.mark.asyncio
async def test_import_account_not_found_recorded_deep2(client):
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "支出", "不存在账户", "餐饮", "10"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert any("账户不存在" in e for e in body["errors"])


@pytest.mark.asyncio
async def test_import_category_missing_or_kind_mismatch_recorded_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "支出", "现金", "不存在分类", "10"],
            ["2024-01-02", "支出", "现金", "工资", "10"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 2
    assert sum(
        1 for e in body["errors"] if "分类不存在或类型不匹配" in e
    ) == 2


@pytest.mark.asyncio
async def test_import_transfer_uses_target_account_name_deep2(client):
    await _create_account(client, "现金")
    await _create_account(client, "银行")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "转账", "现金", "银行", "100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 0
    assert body["errors"] == []

    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    text = export.text
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["date", "type", "account", "category", "amount", "note"]
    data_rows = rows[1:]
    assert len(data_rows) == 1
    assert data_rows[0][1] == "转账"
    assert data_rows[0][2] == "现金->银行"
    assert data_rows[0][4] == "100"


@pytest.mark.asyncio
async def test_import_transfer_same_account_recorded_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "转账", "现金", "现金", "100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert any("转出与转入账户不能相同" in e for e in body["errors"])


@pytest.mark.asyncio
async def test_export_header_type_and_amount_format_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["2024-01-02", "支出", "现金", "餐饮", "30"],
            ["2024-01-03", "支出", "现金", "餐饮", "1.5"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 3

    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    assert (
        export.headers["content-disposition"]
        == 'attachment; filename="ledger-export.csv"'
    )
    rows = list(csv.reader(io.StringIO(export.text)))
    assert rows[0] == ["date", "type", "account", "category", "amount", "note"]
    data_rows = rows[1:]
    assert [r[0] for r in data_rows] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert [r[1] for r in data_rows] == ["收入", "支出", "支出"]
    assert [r[4] for r in data_rows] == ["100", "30", "1.5"]


@pytest.mark.asyncio
async def test_export_date_range_filter_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["2024-01-15", "支出", "现金", "餐饮", "30"],
            ["2024-02-01", "支出", "现金", "餐饮", "20"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 3

    export = await client.get(
        "/api/export/csv",
        params={"date_from": "2024-01-10", "date_to": "2024-01-31"},
    )
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    data_rows = rows[1:]
    assert [r[0] for r in data_rows] == ["2024-01-15"]


@pytest.mark.asyncio
async def test_import_export_roundtrip_deep2(client):
    await _create_account(client, "现金")
    await _create_account(client, "银行")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-03-01", "收入", "现金", "工资", "200"],
            ["2024-03-05", "支出", "现金", "餐饮", "45.5"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 2

    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    data_rows = rows[1:]
    assert len(data_rows) == 2
    assert data_rows[0][0] == "2024-03-01"
    assert data_rows[0][1] == "收入"
    assert data_rows[0][4] == "200"
    assert data_rows[1][0] == "2024-03-05"
    assert data_rows[1][1] == "支出"
    assert data_rows[1][4] == "45.5"


@pytest.mark.asyncio
async def test_import_csv_rows_direct_call_deep2(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "100"]]
    )
    resp = await client.post(
        "/api/import/csv",
        files={"file": ("import.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == []