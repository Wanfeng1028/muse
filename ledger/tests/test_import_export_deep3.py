from __future__ import annotations

import csv
import io

import pytest

from ledger.routers.import_export import _format_amount_yuan


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


def test_format_amount_yuan_zero():
    assert _format_amount_yuan(0) == "0"


def test_format_amount_yuan_negative():
    assert _format_amount_yuan(-12345) == "-123.45"


def test_format_amount_yuan_whole_number_no_decimal():
    assert _format_amount_yuan(100) == "1"


def test_format_amount_yuan_large_number_no_scientific_notation():
    text = _format_amount_yuan(100000000)
    assert "E" not in text
    assert text == "1000000"


def test_format_amount_yuan_small_fraction():
    assert _format_amount_yuan(1) == "0.01"


@pytest.mark.asyncio
async def test_import_utf8_bom_stripped(client):
    await _create_account(client, "现金")
    body = "\ufeffdate,type,account,category,amount\n2024-01-01,收入,现金,工资,100\n"
    csv_bytes = body.encode("utf-8")
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_import_invalid_utf8_bytes_replaced_not_crash(client):
    await _create_account(client, "现金")
    raw = b"date,type,account,category,amount\n2024-01-01,income,cash,cat,100\n\xff\xfe"
    resp = await _import(client, raw)
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    assert "skipped" in body


@pytest.mark.asyncio
async def test_import_empty_file_only_header(client):
    csv_bytes = _make_csv_bytes([])
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_completely_empty_payload(client):
    resp = await _import(client, b"")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_header_only_no_data_rows(client):
    csv_bytes = _make_csv_bytes([], header=["date", "type", "account", "category", "amount"])
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_amount_with_thousands_separator(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "1,000"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert len(body["errors"]) == 1


@pytest.mark.asyncio
async def test_import_amount_with_currency_symbol_rejected(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "$100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 1
    assert len(body["errors"]) == 1


@pytest.mark.asyncio
async def test_import_note_column_preserved_on_export(client):
    await _create_account(client, "现金")
    header = ["date", "type", "account", "category", "amount", "note"]
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "100", "月底工资"]],
        header=header,
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 1

    export = await client.get("/api/export/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    assert rows[1][5] == "月底工资"


@pytest.mark.asyncio
async def test_export_empty_db_returns_header_only(client):
    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    assert len(rows) == 1
    assert rows[0] == ["date", "type", "account", "category", "amount", "note"]


@pytest.mark.asyncio
async def test_export_date_from_after_date_to_returns_empty(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-05-01", "收入", "现金", "工资", "100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 1

    export = await client.get(
        "/api/export/csv",
        params={"date_from": "2024-06-01", "date_to": "2024-01-01"},
    )
    assert export.status_code == 200
    rows = list(csv.reader(io.StringIO(export.text)))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_export_ordering_by_date_then_id(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-03-01", "支出", "现金", "餐饮", "10"],
            ["2024-01-01", "收入", "现金", "工资", "20"],
            ["2024-02-01", "支出", "现金", "餐饮", "30"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 3

    export = await client.get("/api/export/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    dates = [r[0] for r in rows[1:]]
    assert dates == ["2024-01-01", "2024-02-01", "2024-03-01"]


@pytest.mark.asyncio
async def test_export_media_type_header(client):
    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "charset=utf-8" in export.headers["content-type"].lower()


@pytest.mark.asyncio
async def test_import_extra_unknown_columns_ignored(client):
    await _create_account(client, "现金")
    header = ["date", "type", "account", "category", "amount", "extra_col"]
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "100", "whatever"]],
        header=header,
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 0


@pytest.mark.asyncio
async def test_import_whitespace_padded_fields_trimmed(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["  2024-01-01  ", "  收入  ", "  现金  ", "  工资  ", "  100  "]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_missing_file_field_returns_422(client):
    resp = await client.post("/api/import/csv")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_duplicate_rows_both_created(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["2024-01-01", "收入", "现金", "工资", "100"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 0

    export = await client.get("/api/export/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    assert len(rows) - 1 == 2


@pytest.mark.asyncio
async def test_import_all_invalid_rows_created_zero_errors_count(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["bad-date", "收入", "现金", "工资", "100"],
            ["2024-01-01", "错误类型", "现金", "工资", "100"],
            ["2024-01-01", "支出", "现金", "工资", "0"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 3
    assert len(body["errors"]) == 3


@pytest.mark.asyncio
async def test_export_amount_whole_number_formatting(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "10000"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    assert resp.json()["created"] == 1

    export = await client.get("/api/export/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    amount_cell = rows[1][4]
    assert "E" not in amount_cell
    assert amount_cell == "10000"