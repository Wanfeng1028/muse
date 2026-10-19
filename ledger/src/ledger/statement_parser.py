"""银行账单解析：编码识别、金额/日期/方向解析与模板映射。"""

from __future__ import annotations

import datetime
import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

BUILTIN_TEMPLATES: dict[str, dict] = {
    "支付宝": {
        "name": "支付宝",
        "source": "alipay",
        "mapping": {
            "date": "交易创建时间",
            "counterparty": "交易对方",
            "summary": "商品说明",
            "amount": "金额（元）",
            "direction": "收/支",
        },
    },
    "微信支付": {
        "name": "微信支付",
        "source": "wechat",
        "mapping": {
            "date": "交易时间",
            "counterparty": "交易对方",
            "summary": "商品",
            "amount": "金额(元)",
            "direction": "收/支",
        },
    },
    "招商银行": {
        "name": "招商银行",
        "source": "cmb",
        "mapping": {
            "date": "交易日期",
            "summary": "交易摘要",
            "amount": "人民币金额",
        },
    },
    "工商银行": {
        "name": "工商银行",
        "source": "icbc",
        "mapping": {
            "date": "记账日期",
            "summary": "摘要",
            "counterparty": "对方户名",
            "amount": "交易金额（人民币）",
            "direction": "借贷标记",
        },
    },
}


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """尝试多种编码解码字节串，返回 (文本, 编码名)。"""
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def parse_amount_cents(text: str) -> int:
    """解析金额文本为分（正整数）。

    支持括号负数、前导正负号、货币符号与千分位；负数取绝对值
    （收支方向由 parse_direction 另行判定，招行等账单金额自带符号）。
    """
    if text is None:
        raise ValueError(f"金额无法解析：{text}")
    original = text
    cleaned = str(text).strip()
    if not cleaned:
        raise ValueError(f"金额无法解析：{original}")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1]
    if cleaned[:1] in ("-", "+"):
        cleaned = cleaned[1:]
    cleaned = cleaned.replace("¥", "").replace("￥", "").replace("元", "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    cleaned = cleaned.replace("，", "")
    if not cleaned:
        raise ValueError(f"金额无法解析：{original}")
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError(f"金额无法解析：{original}") from None
    cents = int(abs(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)
    if cents <= 0:
        raise ValueError(f"金额必须为正数：{original}")
    return cents


_DATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"^(\d{4})/(\d{2})/(\d{2})"),
    re.compile(r"^(\d{4})(\d{2})(\d{2})$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日"),
]


def parse_date(text: str) -> str:
    """解析日期文本为 ISO 字符串 YYYY-MM-DD。"""
    if text is None:
        raise ValueError(f"日期无法解析：{text}")
    cleaned = str(text).strip()
    if not cleaned:
        raise ValueError(f"日期无法解析：{text}")
    for pattern in _DATE_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            year, month, day = match.groups()
            try:
                datetime.date(int(year), int(month), int(day))
            except ValueError:
                raise ValueError(f"日期无法解析：{text}")
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    raise ValueError(f"日期无法解析：{text}")


def parse_direction(amount_text: str, direction_text: str | None) -> str:
    """判断收支方向，返回 'in' 或 'out'。"""
    if direction_text is not None:
        text = str(direction_text).strip()
        if text:
            has_income = any(token in text for token in ("收", "入", "in", "贷", "+"))
            has_expense = any(token in text for token in ("支", "出", "out", "借", "-"))
            if has_income and "支出" not in text:
                return "in"
            if has_expense and "收入" not in text:
                return "out"
    amount = str(amount_text) if amount_text is not None else ""
    stripped = amount.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return "out"
    if stripped.startswith("-"):
        return "out"
    if stripped.startswith("+"):
        return "in"
    # 无符号的正数金额且无方向列时，视为收入（如招行账单：支出带负号、收入为正数）
    if stripped:
        return "in"
    raise ValueError(f"无法判断收支方向：{amount_text} / {direction_text}")


def apply_mapping(
    rows: list[dict],
    mapping: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """按模板映射解析 CSV 行，返回 (records, errors)。"""
    records: list[dict] = []
    errors: list[dict] = []
    for key in ("date", "amount"):
        if key not in mapping:
            raise ValueError(f"映射缺少必填列：{key}")
    if not rows:
        return records, errors
    headers = set(rows[0].keys())
    for key, header in mapping.items():
        if header not in headers:
            raise ValueError(f"模板列缺失：{header}")
    for index, row in enumerate(rows):
        row_no = index + 2
        try:
            record = _build_record(row, mapping)
        except ValueError as exc:
            errors.append({"row": row_no, "error": str(exc)})
            continue
        records.append(record)
    return records, errors


def _build_record(row: dict, mapping: dict[str, str]) -> dict:
    """根据映射构造单条记录，任一字段失败抛 ValueError。"""
    raw_json = json.dumps(row, ensure_ascii=False)
    occurred_on = parse_date(row.get(mapping.get("date", ""), ""))
    counterparty = ""
    if "counterparty" in mapping:
        counterparty = str(row.get(mapping["counterparty"]) or "").strip()
    summary = ""
    if "summary" in mapping:
        summary = str(row.get(mapping["summary"]) or "").strip()
    amount_text = row.get(mapping.get("amount", ""), "")
    amount_cents = parse_amount_cents(amount_text)
    direction_text = None
    if "direction" in mapping:
        direction_text = row.get(mapping["direction"])
    direction = parse_direction(str(amount_text), direction_text)
    return {
        "occurred_on": occurred_on,
        "counterparty": counterparty,
        "summary": summary,
        "amount_cents": amount_cents,
        "direction": direction,
        "raw_json": raw_json,
    }


def auto_detect_mapping(headers: list[str]) -> dict:
    """自动识别模板映射，命中则返回 mapping，否则返回空字典。"""
    header_set = set(headers)
    for template in BUILTIN_TEMPLATES.values():
        mapping = template["mapping"]
        if all(header in header_set for header in mapping.values()):
            return dict(mapping)
    return {}
