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
async def test_import_empty_file_deep(client):
    resp = await _import(client, b"")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_header_only_deep(client):
    resp = await _import(client, _make_csv_bytes([]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_missing_amount_column_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资"]],
        header=["date", "type", "account", "category"],
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert any("表头缺少必需列" in e for e in body["errors"])


@pytest.mark.asyncio
async def test_import_amount_with_thousand_separator_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "1,234.56"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "金额无效" in body["errors"][0]


@pytest.mark.asyncio
async def test_import_negative_amount_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "-5"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "金额必须大于 0" in body["errors"][0]


@pytest.mark.asyncio
async def test_import_parenthesized_amount_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024-01-01", "收入", "现金", "工资", "(100)"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "金额无效" in body["errors"][0]


@pytest.mark.asyncio
async def test_import_slash_date_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["2024/01/01", "收入", "现金", "工资", "100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "日期格式无效" in body["errors"][0]


@pytest.mark.asyncio
async def test_import_dash_date_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["01-02-2024", "收入", "现金", "工资", "100"]]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "日期格式无效" in body["errors"][0]


@pytest.mark.asyncio
async def test_import_blank_line_between_rows_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["", "", "", "", ""],
            ["2024-01-02", "支出", "现金", "餐饮", "30"],
        ]
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 1
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_shuffled_header_order_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [["100", "买早饭", "工资", "现金", "收入", "2024-01-01"]],
        header=["amount", "note", "category", "account", "type", "date"],
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_gbk_encoded_file_deep(client):
    await _create_account(client, "现金")
    text = "date,type,account,category,amount\n2024-01-01,收入,现金,工资,100\n"
    raw = text.encode("gbk")
    resp = await _import(client, raw)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["errors"]) > 0


@pytest.mark.asyncio
async def test_import_same_file_twice_is_idempotent_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100"],
            ["2024-01-02", "支出", "现金", "餐饮", "30"],
        ]
    )
    first = await _import(client, csv_bytes)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["created"] == 2
    assert first_body["skipped"] == 0
    assert first_body["errors"] == []

    second = await _import(client, csv_bytes)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["created"] == 0
    assert second_body["skipped"] == 2
    assert second_body["errors"] == []

    export = await client.get("/api/export/csv")
    assert export.status_code == 200
    lines = [ln for ln in export.text.splitlines() if ln.strip()]
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_import_duplicate_rows_within_file_deep(client):
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
    assert body["created"] == 1
    assert body["skipped"] == 1
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_import_different_note_is_different_txn_deep(client):
    await _create_account(client, "现金")
    csv_bytes = _make_csv_bytes(
        [
            ["2024-01-01", "收入", "现金", "工资", "100", "第一条"],
            ["2024-01-01", "收入", "现金", "工资", "100", "第二条"],
        ],
        header=["date", "type", "account", "category", "amount", "note"],
    )
    resp = await _import(client, csv_bytes)
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 0
    assert body["errors"] == []
