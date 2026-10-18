import json
from decimal import Decimal, ROUND_HALF_UP

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

def test_decode_bytes_utf8_sig_strips_bom_deep2():
    raw = "交易时间,金额\n2024-01-01,10".encode("utf-8-sig")
    text, enc = decode_bytes(raw)
    assert enc == "utf-8-sig"
    assert text.startswith("交易时间")
    assert "\ufeff" not in text


def test_decode_bytes_plain_utf8_deep2():
    raw = "支付宝,微信".encode("utf-8")
    text, enc = decode_bytes(raw)
    assert enc == "utf-8-sig"
    assert text == "支付宝,微信"


def test_decode_bytes_gbk_chinese_deep2():
    raw = "招商银行交易摘要".encode("gbk")
    text, enc = decode_bytes(raw)
    assert enc == "gbk"
    assert text == "招商银行交易摘要"


def test_decode_bytes_invalid_fallback_replace_deep2():
    raw = b"\xff\xfe\xfa\xfb"
    text, enc = decode_bytes(raw)
    assert enc == "utf-8"
    assert "\ufffd" in text
    assert text == raw.decode("utf-8", errors="replace")


# ---------- parse_amount_cents ----------

def test_parse_amount_cents_parenthesized_is_positive_deep2():
    assert parse_amount_cents("(12.34)") == 1234


def test_parse_amount_cents_leading_minus_absolute_deep2():
    assert parse_amount_cents("-56.78") == 5678


def test_parse_amount_cents_symbols_and_separators_deep2():
    assert parse_amount_cents("¥1,234.50") == 123450
    assert parse_amount_cents("￥2,000元") == 200000
    assert parse_amount_cents("1 000.01") == 100001


def test_parse_amount_cents_round_half_up_deep2():
    expected = int(
        (Decimal("2.345").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
    )
    assert expected == 235
    assert parse_amount_cents("2.345") == 235


def test_parse_amount_cents_none_raises_deep2():
    with pytest.raises(ValueError):
        parse_amount_cents(None)


def test_parse_amount_cents_zero_raises_deep2():
    with pytest.raises(ValueError):
        parse_amount_cents("0.00")


def test_parse_amount_cents_negative_zero_raises_deep2():
    with pytest.raises(ValueError):
        parse_amount_cents("-0")


def test_parse_amount_cents_blank_raises_deep2():
    with pytest.raises(ValueError):
        parse_amount_cents("   ")


# ---------- parse_date ----------

def test_parse_date_dash_format_deep2():
    assert parse_date("2024-03-05") == "2024-03-05"


def test_parse_date_slash_format_deep2():
    assert parse_date("2024/03/05") == "2024-03-05"


def test_parse_date_compact_format_deep2():
    assert parse_date("20240305") == "2024-03-05"


def test_parse_date_chinese_format_deep2():
    assert parse_date("2024年3月5日") == "2024-03-05"


def test_parse_date_invalid_raises_deep2():
    with pytest.raises(ValueError):
        parse_date("05-03-2024")


def test_parse_date_none_raises_deep2():
    with pytest.raises(ValueError):
        parse_date(None)


# ---------- parse_direction ----------

def test_parse_direction_expense_with_both_keywords_deep2():
    assert parse_direction("100.00", "支出") == "out"


def test_parse_direction_income_with_both_keywords_deep2():
    assert parse_direction("100.00", "收入") == "in"


def test_parse_direction_debit_credit_markers_deep2():
    assert parse_direction("100.00", "借") == "out"
    assert parse_direction("100.00", "贷") == "in"


def test_parse_direction_parenthesized_amount_deep2():
    assert parse_direction("(50.00)", None) == "out"


def test_parse_direction_positive_no_direction_is_in_deep2():
    assert parse_direction("50.00", None) == "in"


def test_parse_direction_empty_amount_raises_deep2():
    with pytest.raises(ValueError):
        parse_direction("", None)


# ---------- apply_mapping ----------

def test_apply_mapping_missing_required_keys_raises_deep2():
    with pytest.raises(ValueError):
        apply_mapping([], {"date": "交易时间"})
    with pytest.raises(ValueError):
        apply_mapping([], {"amount": "金额(元)"})


def test_apply_mapping_empty_rows_returns_empty_deep2():
    result = apply_mapping([], {"date": "交易时间", "amount": "金额(元)"})
    assert result == ([], [])


def test_apply_mapping_missing_header_column_raises_deep2():
    rows = [{"交易时间": "2024-01-01", "金额(元)": "10.00"}]
    with pytest.raises(ValueError):
        apply_mapping(rows, {"date": "交易时间", "amount": "金额(元)", "summary": "商品"})


def test_apply_mapping_error_row_number_and_good_rows_kept_deep2():
    rows = [
        {"交易时间": "2024-01-01", "金额(元)": "10.00", "交易对方": "A"},
        {"交易时间": "bad-date", "金额(元)": "20.00", "交易对方": "B"},
        {"交易时间": "2024-01-03", "金额(元)": "30.00", "交易对方": "C"},
    ]
    mapping = {"date": "交易时间", "amount": "金额(元)", "counterparty": "交易对方"}
    records, errors = apply_mapping(rows, mapping)
    assert len(records) == 2
    assert len(errors) == 1
    assert errors[0]["row"] == 3
    assert "bad-date" in errors[0]["error"]
    assert records[0]["counterparty"] == "A"
    assert records[1]["counterparty"] == "C"


# ---------- _build_record ----------

def test_build_record_cmb_template_without_direction_deep2():
    row = {"交易日期": "2024-02-10", "交易摘要": "消费", "人民币金额": "-88.80"}
    mapping = {"date": "交易日期", "amount": "人民币金额", "summary": "交易摘要"}
    record = _build_record(row, mapping)
    assert record["occurred_on"] == "2024-02-10"
    assert record["amount_cents"] == 8880
    assert record["summary"] == "消费"
    assert record["counterparty"] == ""
    assert record["direction"] == "out"
    assert json.loads(record["raw_json"]) == row


# ---------- auto_detect_mapping ----------

def test_auto_detect_mapping_alipay_hit_deep2():
    headers = ["交易创建时间", "交易对方", "商品说明", "金额（元）", "收/支"]
    detected = auto_detect_mapping(headers)
    assert detected == {"date": "交易创建时间", "counterparty": "交易对方", "summary": "商品说明", "amount": "金额（元）", "direction": "收/支"}


def test_auto_detect_mapping_missing_one_column_deep2():
    headers = ["交易创建时间", "交易对方", "商品说明", "金额（元）"]
    assert auto_detect_mapping(headers) == {}


def test_auto_detect_mapping_empty_headers_deep2():
    assert auto_detect_mapping([]) == {}


def test_auto_detect_mapping_icbc_hit_deep2():
    headers = ["记账日期", "摘要", "对方户名", "交易金额（人民币）", "借贷标记"]
    detected = auto_detect_mapping(headers)
    assert detected == {"date": "记账日期", "summary": "摘要", "counterparty": "对方户名", "amount": "交易金额（人民币）", "direction": "借贷标记"}