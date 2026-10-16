"""OCR 提供商抽象层：定义统一接口，提供 Mock 实现；真实 OCR 需用户配置外部服务 key。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass
class OcrResult:
    """OCR 识别结果。amount_cents 为金额（分），occurred_on 为 YYYY-MM-DD 字符串。"""

    merchant: str
    amount_cents: int
    occurred_on: str
    candidates: list[dict]
    provider: str
    mock: bool
    raw_text: str


class OcrError(Exception):
    """OCR 相关错误基类。"""


class OcrNotConfiguredError(OcrError):
    """真实 OCR 服务未配置。"""


class OcrFailedError(OcrError):
    """OCR 识别失败。"""


class OcrProvider(Protocol):
    """OCR 提供商协议。"""

    async def recognize(self, image: bytes, filename: str, content_type: str) -> OcrResult:
        """识别图片，返回结构化结果。"""
        ...


class MockOcrProvider:
    """Mock 提供商：返回固定结果，忽略输入图片内容（仍要求图片非空）。"""

    async def recognize(self, image: bytes, filename: str, content_type: str) -> OcrResult:
        if not image:
            raise OcrFailedError("图片内容为空")
        today = datetime.now(UTC).date().isoformat()
        return OcrResult(
            merchant="星巴克臻选",
            amount_cents=6800,
            occurred_on=today,
            candidates=[
                {"category_name": "餐饮", "confidence": 0.92},
                {"category_name": "购物", "confidence": 0.41},
            ],
            provider="mock",
            mock=True,
            raw_text="星巴克臻选\n拿铁 68.00\n2026-10-16",
        )


class EnvOcrProvider:
    """真实 OCR 提供商桩：读取 LEDGER_OCR_API_KEY，未配置或未接入时诚实报错。"""

    async def recognize(self, image: bytes, filename: str, content_type: str) -> OcrResult:
        api_key = os.environ.get("LEDGER_OCR_API_KEY", "").strip()
        if not api_key:
            raise OcrNotConfiguredError(
                "未配置真实 OCR 服务：请设置环境变量 LEDGER_OCR_API_KEY 后再使用真实 OCR"
                "（当前版本仅提供抽象层与 Mock 实现）"
            )
        raise NotImplementedError("真实 OCR 提供商接入尚未实现：当前版本仅提供抽象层与 Mock 实现")


def get_provider() -> OcrProvider:
    """根据 LEDGER_OCR_PROVIDER 返回提供商实例，默认 mock。"""
    name = os.environ.get("LEDGER_OCR_PROVIDER", "mock").strip().lower()
    if name == "mock":
        return MockOcrProvider()
    if name == "env":
        return EnvOcrProvider()
    raise ValueError(f"未知的 OCR 提供商: {name!r}，允许 mock/env")
