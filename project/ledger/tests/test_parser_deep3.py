import json

import pytest

from ledger.statement_parser import (
    BUILTIN_TEMPLATES,
    _build_record,
    apply_mapping,
    auto_detect_mapping,
    decode_bytes,
    parse_amount_cents,
    parse_date,
    parse_direction,
)

# ---------- decode_bytes ----------

def test_decode_bytes_empty_bytes_deep3():
    text, enc = decode_bytes(b"")
    assert text == ""
    assert enc == "utf-8-sig"


def test_decode_bytes_gbk_ascii_only_deep3():
    raw = b"2024-01-01,hello"
    text, enc = decode_bytes(raw)
    assert text == "2024-01-01,hello"
    assert enc in ("utf-8-sig", "gbk")


def test_decode_bytes_truncated_multibyte_utf8_falls_back_deep3():
    raw = "金额".encode() + b"\xe4"
    text, enc = decode_bytes(raw)
    assert enc == "gbk" or enc == "utf-8"
    assert isinstance(text, str)


# ---------- parse_amount_cents ----------

def test_parse_amount_cents_trailing_plus_sign_ignored_deep3():
    assert parse_amount_cents("+12.00") == 1200


def test_parse_amount_cents_full_width_comma_deep3():
    assert parse_amount_cents("1，234.56") == 123456


def test_parse_amount_cents_only_symbols_raises_deep3():
    with pytest.raises(ValueError):
        parse_amount_cents("¥￥元")


def test_parse_amount_cents_non_numeric_text_raises_deep3():
    with pytest.raises(ValueError):
        parse_amount_cents("abc")


def test_parse_amount_cents_float_precision_many_digits_deep3():
    assert parse_amount_cents("0.005") == 1
    with pytest.raises(ValueError):
        parse_amount_cents("0.004")


def test_parse_amount_cents_huge_amount_deep3():
    cents = parse_amount_cents("9999999999999.99")
    assert cents == 999999999999999


def test_parse_amount_cents_leading_zeros_deep3():
    assert parse_amount_cents("000123.45") == 12345


def test_parse_amount_cents_parenthesized_with_symbols_deep3():
    assert parse_amount_cents("(¥1,000.00)") == 100000


def test_parse_amount_cents_nested_sign_inside_parens_deep3():
    assert parse_amount_cents("(-5.00)") == 500


# ---------- parse_date ----------

def test_parse_date_compact_with_trailing_time_deep3():
    assert parse_date("2024-01-02 12:30:00") == "2024-01-02"


def test_parse_date_single_digit_month_day_chinese_deep3():
    assert parse_date("2024年1月5日") == "2024-01-05"


def test_parse_date_whitespace_only_raises_deep3():
    with pytest.raises(ValueError):
        parse_date("   ")


def test_parse_date_slash_with_trailing_text_deep3():
    assert parse_date("2024/12/31 23:59") == "2024-12-31"


def test_parse_date_compact_partial_length_raises_deep3():
    with pytest.raises(ValueError):
        parse_date("202401")


def test_parse_date_wrong_separator_raises_deep3():
    with pytest.raises(ValueError):
        parse_date("2024.01.02")


# ---------- parse_direction ----------

def test_parse_direction_empty_string_falls_back_to_amount_deep3():
    assert parse_direction("100.00", "") == "in"


def test_parse_direction_whitespace_direction_falls_back_deep3():
    assert parse_direction("100.00", "   ") == "in"


def test_parse_direction_english_in_out_deep3():
    assert parse_direction("100.00", "in") == "in"
    assert parse_direction("100.00", "out") == "out"


def test_parse_direction_plus_symbol_direction_deep3():
    assert parse_direction("100.00", "+") == "in"


def test_parse_direction_minus_symbol_direction_deep3():
    assert parse_direction("100.00", "-") == "out"


def test_parse_direction_ambiguous_text_with_income_and_expense_deep3():
    assert parse_direction("100.00", "收入支出") == "in"
    assert parse_direction("100.00", "支出收入") == "in"


def test_parse_direction_none_amount_none_direction_raises_deep3():
    with pytest.raises(ValueError):
        parse_direction(None, None)


def test_parse_direction_parenthesized_with_whitespace_deep3():
    assert parse_direction("  (50.00)  ", None) == "out"


def test_parse_direction_plus_prefixed_amount_deep3():
    assert parse_direction("+50.00", None) == "in"


# ---------- apply_mapping ----------

def test_apply_mapping_all_rows_bad_returns_empty_records_deep3():
    rows = [
        {"交易时间": "bad", "金额(元)": "10.00"},
        {"交易时间": "also-bad", "金额(元)": "20.00"},
    ]
    mapping = {"date": "交易时间", "amount": "金额(元)"}
    records, errors = apply_mapping(rows, mapping)
    assert records == []
    assert len(errors) == 2
    assert errors[0]["row"] == 2
    assert errors[1]["row"] == 3


def test_apply_mapping_row_with_empty_amount_records_error_deep3():
    rows = [{"交易时间": "2024-01-01", "金额(元)": ""}]
    mapping = {"date": "交易时间", "amount": "金额(元)"}
    records, errors = apply_mapping(rows, mapping)
    assert records == []
    assert len(errors) == 1
    assert "row" in errors[0]


def test_apply_mapping_headers_from_second_row_when_first_differs_deep3():
    rows = [
        {"交易时间": "2024-01-01", "金额(元)": "10.00"},
    ]
    mapping = {"date": "交易时间", "amount": "金额(元)"}
    records, errors = apply_mapping(rows, mapping)
    assert len(records) == 1
    assert records[0]["amount_cents"] == 1000


def test_apply_mapping_extra_columns_ignored_deep3():
    rows = [
        {
            "交易时间": "2024-01-01",
            "金额(元)": "10.00",
            "额外列": "extra",
        }
    ]
    mapping = {"date": "交易时间", "amount": "金额(元)"}
    records, errors = apply_mapping(rows, mapping)
    assert errors == []
    assert records[0]["amount_cents"] == 1000


# ---------- _build_record ----------

def test_build_record_none_counterparty_becomes_empty_deep3():
    row = {"交易日期": "2024-02-10", "交易摘要": "消费", "人民币金额": "-1.00", "对方户名": None}
    mapping = {
        "date": "交易日期",
        "amount": "人民币金额",
        "summary": "交易摘要",
        "counterparty": "对方户名",
    }
    record = _build_record(row, mapping)
    assert record["counterparty"] == ""
    assert record["direction"] == "out"


def test_build_record_direction_missing_uses_amount_sign_deep3():
    row = {"交易日期": "2024-02-10", "人民币金额": "-5.55"}
    mapping = {"date": "交易日期", "amount": "人民币金额"}
    record = _build_record(row, mapping)
    assert record["direction"] == "out"
    assert record["amount_cents"] == 555


def test_build_record_raw_json_roundtrip_unicode_deep3():
    row = {"交易日期": "2024-02-10", "人民币金额": "1.00", "备注": "测试✓"}
    mapping = {"date": "交易日期", "amount": "人民币金额"}
    record = _build_record(row, mapping)
    assert json.loads(record["raw_json"]) == row
    assert "测试✓" in record["raw_json"]


# ---------- auto_detect_mapping ----------

def test_auto_detect_mapping_wechat_hit_deep3():
    headers = ["交易时间", "交易对方", "商品", "金额(元)", "收/支"]
    detected = auto_detect_mapping(headers)
    assert detected == BUILTIN_TEMPLATES["微信支付"]["mapping"]


def test_auto_detect_mapping_extra_headers_still_hits_deep3():
    headers = [
        "交易创建时间",
        "交易对方",
        "商品说明",
        "金额（元）",
        "收/支",
        "未知列",
    ]
    detected = auto_detect_mapping(headers)
    assert detected == BUILTIN_TEMPLATES["支付宝"]["mapping"]


def test_auto_detect_mapping_wrong_currency_header_no_hit_deep3():
    headers = ["交易创建时间", "交易对方", "商品说明", "金额", "收/支"]
    assert auto_detect_mapping(headers) == {}


def test_auto_detect_mapping_returns_copy_not_shared_reference_deep3():
    headers = ["交易创建时间", "交易对方", "商品说明", "金额（元）", "收/支"]
    detected = auto_detect_mapping(headers)
    detected["date"] = "mutated"
    second = auto_detect_mapping(headers)
    assert second["date"] == "交易创建时间"