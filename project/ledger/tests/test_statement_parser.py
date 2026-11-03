# tests/test_statement_parser.py
"""账单解析单元测试：decode_bytes / parse_amount_cents / parse_date /
parse_direction / apply_mapping / auto_detect_mapping。"""
import pytest

from ledger.statement_parser import (  # type: ignore
    BUILTIN_TEMPLATES,
    apply_mapping,
    auto_detect_mapping,
    decode_bytes,
    parse_amount_cents,
    parse_date,
    parse_direction,
)


class TestDecodeBytes:
    """decode_bytes：utf-8-sig → gbk → utf-8(replace)。"""

    def test_utf8_sig_strips_bom(self):
        """UTF-8 BOM 应被剥离，编码标记为 utf-8-sig。"""
        text, encoding = decode_bytes("交易时间,金额".encode("utf-8-sig"))
        assert not text.startswith("\ufeff")
        assert "交易时间" in text

    def test_gbk_chinese(self):
        """GBK 编码中文应正确解码。"""
        text, encoding = decode_bytes("交易时间,金额".encode("gbk"))
        assert "交易时间" in text
        assert encoding.lower() in {"gbk", "gb18030", "gb2312"}

    def test_invalid_bytes_fallback(self):
        """非法字节应 fallback 到 utf-8(replace)，不抛异常。"""
        text, encoding = decode_bytes(b"\xff\xfe\x00bad\xff")
        assert isinstance(text, str)
        assert isinstance(encoding, str)


class TestParseAmountCents:
    """parse_amount_cents：符号/括号/逗号/单位处理。"""

    def test_yuan_with_comma(self):
        """"¥1,234.56" → 123456 分。"""
        assert parse_amount_cents("¥1,234.56") == 123456

    def test_parentheses_absolute(self):
        """"(100)" → 10000 分（取绝对值）。"""
        assert parse_amount_cents("(100)") == 10000

    def test_leading_minus_absolute(self):
        """"-50" → 5000 分（取绝对值）。"""
        assert parse_amount_cents("-50") == 5000

    def test_zero_raises(self):
        """"0" 抛 ValueError。"""
        with pytest.raises(ValueError):
            parse_amount_cents("0")

    def test_invalid_raises(self):
        """"abc" 抛 ValueError。"""
        with pytest.raises(ValueError):
            parse_amount_cents("abc")

    def test_fullwidth_yuan_and_spaces(self):
        """全角￥与空格应被剥离。"""
        assert parse_amount_cents("￥ 88.00") == 8800

    def test_trailing_yuan_unit(self):
        """结尾 "元" 应被剥离。"""
        assert parse_amount_cents("12元") == 1200


class TestParseDate:
    """parse_date：5 种格式支持，非法抛 ValueError。"""

    def test_iso_dash(self):
        assert parse_date("2024-01-02") == "2024-01-02"

    def test_slash(self):
        assert parse_date("2024/01/02") == "2024-01-02"

    def test_compact(self):
        assert parse_date("20240102") == "2024-01-02"

    def test_chinese(self):
        assert parse_date("2024年01月02日") == "2024-01-02"

    def test_datetime_suffix(self):
        assert parse_date("2024-01-02 13:45:00") == "2024-01-02"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestParseDirection:
    """parse_direction：文字方向与金额符号。"""

    def test_out_keyword(self):
        assert parse_direction("12.00", "支出") == "out"

    def test_in_keyword(self):
        assert parse_direction("12.00", "收入") == "in"

    def test_borrow_is_out(self):
        assert parse_direction("12.00", "借") == "out"

    def test_loan_is_in(self):
        assert parse_direction("12.00", "贷") == "in"

    def test_negative_amount_out(self):
        assert parse_direction("-12", "") == "out"

    def test_positive_amount_in(self):
        assert parse_direction("12", "") == "in"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_direction("", "")


class TestApplyMapping:
    """apply_mapping：正常行、错误行收集、缺列抛。"""

    def _mapping(self):
        return {
            "date": "交易时间",
            "amount": "金额",
            "counterparty": "对方",
            "summary": "备注",
            "direction": "方向",
        }

    def test_normal_rows(self):
        """正常行解析为 records。"""
        rows = [
            {"交易时间": "2024-01-02 10:00:00", "金额": "¥12.00", "对方": "星巴克",
             "备注": "咖啡", "方向": "支出"},
        ]
        records, errors = apply_mapping(rows, self._mapping())
        assert errors == []
        assert len(records) == 1
        rec = records[0]
        assert rec["occurred_on"] == "2024-01-02"
        assert rec["amount_cents"] == 1200
        assert rec["direction"] == "out"
        assert "raw_json" in rec

    def test_error_rows_collected(self):
        """非法金额行应进入 errors 而不是抛异常。"""
        rows = [
            {"交易时间": "2024-01-02", "金额": "abc", "对方": "x", "备注": "y", "方向": "支出"},
        ]
        records, errors = apply_mapping(rows, self._mapping())
        assert records == []
        assert len(errors) == 1
        assert "row" in errors[0] and "error" in errors[0]

    def test_missing_date_raises(self):
        """mapping 缺 date 抛 ValueError。"""
        mapping = self._mapping()
        mapping.pop("date")
        with pytest.raises(ValueError):
            apply_mapping([], mapping)

    def test_missing_amount_raises(self):
        """mapping 缺 amount 抛 ValueError。"""
        mapping = self._mapping()
        mapping.pop("amount")
        with pytest.raises(ValueError):
            apply_mapping([], mapping)


class TestAutoDetectMapping:
    """auto_detect_mapping：命中内置模板。"""

    def test_alipay_headers_hit(self):
        """支付宝表头应命中内置模板，mapping 含 交易创建时间。"""
        headers = ["交易创建时间", "交易对方", "商品说明", "金额（元）", "收/支"]
        mapping = auto_detect_mapping(headers)
        assert mapping
        assert any("交易创建时间" == v for v in mapping.values())

    def test_unknown_headers_empty(self):
        """陌生表头返回 {}。"""
        assert auto_detect_mapping(["col_a", "col_b", "col_c"]) == {}

    def test_builtin_templates_keys(self):
        """内置模板包含 4 家。"""
        for key in ("支付宝", "微信支付", "招商银行", "工商银行"):
            assert key in BUILTIN_TEMPLATES
