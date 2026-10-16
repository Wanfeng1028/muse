"""币种与汇率换算工具。"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

ISO_CODE_RE = re.compile(r"^[A-Z]{3}$")


def validate_currency_code(v: str) -> str:
    """校验 ISO 4217 币种代码：三字母大写。返回规范化后的代码，非法抛 ValueError。"""
    if not isinstance(v, str):
        raise ValueError("币种代码必须为 ISO 4217 三字母大写")
    norm = v.strip().upper()
    if not ISO_CODE_RE.match(norm):
        raise ValueError("币种代码必须为 ISO 4217 三字母大写")
    return norm


def to_base_cents(amount_cents: int, rate_to_base) -> int:
    """将某币种的分金额按汇率折算为本位币分（Decimal 精确，四舍五入）。"""
    rate = Decimal(str(rate_to_base))
    if rate <= 0:
        raise ValueError("汇率必须大于 0")
    result = (Decimal(int(amount_cents)) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(result)
