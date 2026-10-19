"""Deep tests for ledger.statement_parser: dirty bank statement import edge cases."""

from __future__ import annotations

import pytest

from ledger.statement_parser import (
    BUILTIN_TEMPLATES,
    apply_mapping,
    auto_detect_mapping,
    decode_bytes,
    parse_amount_cents,
    parse_date,
    parse_direction,
)


# ---------------------------------------------------------------------------
# decode_bytes
# ---------------------------------------------------------------------------


def test_decode_bytes_utf8_no_bom():
    text, encoding = decode_bytes("交易 100".encode("utf-8"))
    assert text == "交易 100"
    assert encoding == "utf-8-sig"


def test_decode_bytes_utf8_sig_strips_bom():
    raw = "\ufeff交易时间".encode("utf-8")
    text, encoding = decode_bytes(raw)
    assert text == "交易时间"
    assert not text.startswith("\ufeff")
    assert encoding == "utf-8-sig"


def test_decode_bytes_gbk_chinese():
    raw = "支付宝账单".encode("gbk")
    text, encoding = decode_bytes(raw)
    assert text == "支付宝账单"
    assert encoding == "gbk"


def test_decode_bytes_empty_returns_empty_string():
    text, encoding = decode_bytes(b"")
    assert text == ""
    assert encoding == "utf-8-sig"


# ---------------------------------------------------------------------------
# parse_amount_cents
# ---------------------------------------------------------------------------


def test_parse_amount_cents_thousands_separator():
    assert parse_amount_cents("1,234.56") == 123456


def test_parse_amount_cents_currency_symbol_thousands():
    assert parse_amount_cents("¥1,234") == 123400


def test_parse_amount_cents_parentheses_negative():
    assert parse_amount_cents("(100)") == 10000


def test_parse_amount_cents_leading_minus():
    assert parse_amount_cents("-5.5") == 550


def test_parse_amount_cents_whitespace_stripped():
    assert parse_amount_cents(" 200 ") == 20000


def test_parse_amount_cents_invalid_raises_value_error():
    with pytest.raises(ValueError):
        parse_amount_cents("abc")


def test_parse_amount_cents_three_decimal_rounds_half_up():
    assert parse_amount_cents("1.234") == 123
    assert parse_amount_cents("1.235") == 124


def test_parse_amount_cents_zero_raises():
    with pytest.raises(ValueError):
        parse_amount_cents("0")


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


def test_parse_date_iso_dashes():
    assert parse_date("2024-01-05") == "2024-01-05"


def test_parse_date_slashes_single_digits():
    with pytest.raises(ValueError):
        parse_date("2024/1/5")


def test_parse_date_dots_raises():
    with pytest.raises(ValueError):
        parse_date("2024.01.05")


def test_parse_date_compact():
    assert parse_date("20240105") == "2024-01-05"


def test_parse_date_us_style_raises():
    with pytest.raises(ValueError):
        parse_date("1/5/2024")


def test_parse_date_invalid_month_raises():
    with pytest.raises(ValueError):
        parse_date("2024-13-01")


def test_parse_date_empty_raises():
    with pytest.raises(ValueError):
        parse_date("")


# ---------------------------------------------------------------------------
# parse_direction
# ---------------------------------------------------------------------------


def test_parse_direction_amount_minus_out():
    assert parse_direction("-100", None) == "out"


def test_parse_direction_amount_positive_in():
    assert parse_direction("100", None) == "in"


def test_parse_direction_chinese_expense():
    assert parse_direction("100", "支出") == "out"


def test_parse_direction_chinese_income():
    assert parse_direction("-100", "收入") == "in"


def test_parse_direction_direction_column_wins_over_amount_sign():
    # direction_text "支出" -> has_expense True, has_income False -> "out"
    # despite positive amount sign
    assert parse_direction("+100", "支出") == "out"


def test_parse_direction_empty_both_raises():
    with pytest.raises(ValueError):
        parse_direction("", None)


# ---------------------------------------------------------------------------
# auto_detect_mapping
# ---------------------------------------------------------------------------


def test_auto_detect_mapping_wechat_headers():
    headers = ["交易时间", "交易对方", "商品", "金额(元)", "收/支"]
    mapping = auto_detect_mapping(headers)
    assert mapping == BUILTIN_TEMPLATES["微信支付"]["mapping"]


def test_auto_detect_mapping_unknown_headers_returns_empty():
    assert auto_detect_mapping(["foo", "bar", "baz"]) == {}


# ---------------------------------------------------------------------------
# apply_mapping / _build_record
# ---------------------------------------------------------------------------


def test_apply_mapping_builds_record_fields():
    mapping = {
        "date": "交易时间",
        "counterparty": "交易对方",
        "summary": "商品",
        "amount": "金额(元)",
        "direction": "收/支",
    }
    rows = [
        {
            "交易时间": "2024-01-05",
            "交易对方": "商户A",
            "商品": "午餐",
            "金额(元)": "12.34",
            "收/支": "支出",
        }
    ]
    records, errors = apply_mapping(rows, mapping)
    assert errors == []
    assert len(records) == 1
    rec = records[0]
    assert rec["occurred_on"] == "2024-01-05"
    assert rec["amount_cents"] == 1234
    assert rec["direction"] == "out"
    assert rec["counterparty"] == "商户A"
    assert rec["summary"] == "午餐"
    assert isinstance(rec["raw_json"], str)


def test_apply_mapping_collects_row_errors():
    mapping = {
        "date": "交易时间",
        "amount": "金额(元)",
    }
    rows = [
        {"交易时间": "2024-01-05", "金额(元)": "10.00"},
        {"交易时间": "not-a-date", "金额(元)": "20.00"},
        {"交易时间": "2024-01-07", "金额(元)": "abc"},
    ]
    records, errors = apply_mapping(rows, mapping)
    assert len(records) == 1
    assert len(errors) == 2
    assert errors[0]["row"] == 3
    assert errors[1]["row"] == 4
    assert records[0]["amount_cents"] == 1000


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_apply_mapping_idempotent_across_calls():
    mapping = {
        "date": "交易时间",
        "counterparty": "交易对方",
        "summary": "商品",
        "amount": "金额(元)",
        "direction": "收/支",
    }
    rows = [
        {
            "交易时间": "2024-01-05",
            "交易对方": "商户A",
            "商品": "午餐",
            "金额(元)": "12.34",
            "收/支": "支出",
        },
        {
            "交易时间": "2024-01-06",
            "交易对方": "商户B",
            "商品": "晚餐",
            "金额(元)": "56.78",
            "收/支": "支出",
        },
    ]
    first_records, first_errors = apply_mapping(rows, mapping)
    second_records, second_errors = apply_mapping(rows, mapping)
    assert first_errors == second_errors == []
    assert first_records == second_records
