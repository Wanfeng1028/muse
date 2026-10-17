"""OCR 提供商抽象层：Mock / Tesseract / 云服务桩三种实现。"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
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
    field_confidence: dict[str, float] = field(default_factory=dict)


class OcrError(Exception):
    """OCR 相关错误基类。"""


class OcrNotConfiguredError(OcrError):
    """真实 OCR 服务未配置。"""


class OcrFailedError(OcrError):
    """OCR 识别失败。"""


class OcrUnavailableError(OcrError):
    """OCR 能力不可用（缺 tesseract 二进制、执行失败或超时）。

    message 必须带安装指引，便于调用方直接展示给用户。
    """


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
            field_confidence={"merchant": 0.95, "amount_cents": 0.9, "occurred_on": 0.85},
        )

    async def ocr_lines(self, image: bytes) -> list[str]:
        """返回模拟的微信支付账单 CSV 风格文本行，供 statement 解析流消费。

        注意：这是编造的模拟数据，不反映真实图片内容，仅用于打通「账单图片 OCR 录入」
        到 statement 解析的链路。
        """
        if not image:
            raise OcrFailedError("图片内容为空")
        return [
            "交易时间,交易对方,商品,金额(元),收/支",
            "2026-10-15 08:32:11,肯德基,早餐套餐,18.50,支出",
            "2026-10-16 12:05:47,美团外卖,午餐,32.80,支出",
            "2026-10-16 19:21:03,全家便利店,日用品,45.60,支出",
            "2026-10-16 21:10:55,微信红包,收到红包,88.00,收入",
        ]


class TesseractOcrProvider:
    """基于本地 tesseract 可执行文件的真实 OCR 提供商。"""

    _AMOUNT_RE = re.compile(
        r"(?:￥|¥|RMB|CNY|合计|总计|实付|应付)?\s*"
        r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(?:元|块)?"
    )
    _DATE_FULL_RE = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})")
    _DATE_SHORT_RE = re.compile(r"(\d{1,2})[月/-](\d{1,2})")
    _INSTALL_HINT = (
        "未找到 tesseract 可执行文件。\n"
        "Debian/Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng\n"
        "macOS: brew install tesseract tesseract-lang\n"
        "安装后请确保 tesseract 在 PATH 中。"
    )

    def __init__(
        self,
        lang: str | None = None,
        timeout: int | None = None,
        psm: int = 6,
    ) -> None:
        if lang is None:
            lang = os.environ.get("LEDGER_OCR_LANG", "chi_sim+eng").strip() or "chi_sim+eng"
        if timeout is None:
            raw = os.environ.get("LEDGER_OCR_TIMEOUT", "").strip()
            parsed: int | None
            try:
                parsed = int(raw) if raw else None
            except ValueError:
                parsed = None
            timeout = parsed if parsed is not None and parsed >= 5 else 30
        self._lang = lang
        self._timeout = timeout
        self._psm = psm

    def _check_binary(self) -> None:
        if not shutil.which("tesseract"):
            raise OcrNotConfiguredError(self._INSTALL_HINT)

    def _preprocess(self, image: bytes) -> bytes:
        try:
            from PIL import Image, ImageOps
        except Exception:
            return image
        try:
            with Image.open(io.BytesIO(image)) as raw_img:
                img = ImageOps.exif_transpose(raw_img) or raw_img
                gray = img.convert("L")
                width, height = gray.size
                longest = max(width, height)
                if longest < 1600 and longest > 0:
                    scale = 1600 / longest
                    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                    gray = gray.resize(new_size, Image.LANCZOS)
                out = io.BytesIO()
                gray.save(out, format="PNG")
                return out.getvalue()
        except Exception:
            return image

    async def recognize(self, image: bytes, filename: str, content_type: str) -> OcrResult:
        if not image:
            raise OcrFailedError("图片内容为空")
        self._check_binary()
        payload = self._preprocess(image)
        try:
            proc = subprocess.run(
                [
                    "tesseract",
                    "stdin",
                    "stdout",
                    "-l",
                    self._lang,
                    "--psm",
                    str(self._psm),
                ],
                input=payload,
                capture_output=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrFailedError(f"OCR 识别超时（{self._timeout} 秒）") from exc
        if proc.returncode != 0:
            stderr_text = (proc.stderr or b"").decode("utf-8", errors="replace")
            tail = stderr_text[-300:]
            raise OcrFailedError(f"tesseract 退出码 {proc.returncode}：{tail}")
        text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        if not text:
            raise OcrFailedError("tesseract 未识别出任何文本")
        merchant, amount_cents, occurred_on, confidences = self._parse(text)
        return OcrResult(
            merchant=merchant,
            amount_cents=amount_cents,
            occurred_on=occurred_on,
            candidates=[],
            provider="tesseract",
            mock=False,
            raw_text=text,
            field_confidence=confidences,
        )

    async def ocr_lines(self, image: bytes) -> list[str]:
        """识别图片并返回按行切分的文本列表（已 strip、去除空行）。"""
        if not image:
            raise OcrFailedError("图片内容为空")
        if not shutil.which("tesseract"):
            raise OcrUnavailableError(self._INSTALL_HINT)
        payload = self._preprocess(image)
        try:
            proc = subprocess.run(
                [
                    "tesseract",
                    "stdin",
                    "stdout",
                    "-l",
                    self._lang,
                    "--psm",
                    str(self._psm),
                ],
                input=payload,
                capture_output=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrUnavailableError(f"tesseract 执行超时（{self._timeout} 秒）：{self._INSTALL_HINT}") from exc
        if proc.returncode != 0:
            stderr_text = (proc.stderr or b"").decode("utf-8", errors="replace")
            tail = stderr_text[-300:]
            raise OcrUnavailableError(f"tesseract 退出码 {proc.returncode}：{tail}\n{self._INSTALL_HINT}")
        raw = (proc.stdout or b"").decode("utf-8", errors="replace")
        lines = [line.strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            raise OcrFailedError("tesseract 未识别出任何文本")
        return lines

    def _mask_dates(self, text: str) -> str:
        """把文本中所有日期形态片段替换为等长空格，避免日期数字被金额正则误提取。"""
        spans = [m.span() for rx in (self._DATE_FULL_RE, self._DATE_SHORT_RE) for m in rx.finditer(text)]
        chars = list(text)
        for start, end in spans:
            for i in range(start, end):
                chars[i] = " "
        return "".join(chars)

    def _parse(self, text: str) -> tuple[str, int, str, dict[str, float]]:
        stripped = text.strip()
        merchant = ""
        merchant_conf = 0.0
        if stripped:
            for line in stripped.splitlines():
                candidate = line.strip()
                if candidate:
                    merchant = candidate[:60]
                    merchant_conf = 0.6
                    break

        amount_cents = 0
        amount_conf = 0.0
        best_value = -1.0
        amount_source = self._mask_dates(stripped)
        for match in self._AMOUNT_RE.finditer(amount_source):
            token = match.group(1).replace(",", "")
            try:
                value = float(token)
            except ValueError:
                continue
            if value > best_value:
                best_value = value
        if best_value >= 0:
            amount_cents = int(round(best_value * 100))
            amount_conf = 0.85

        today = datetime.now(UTC).date()
        occurred_on = today.isoformat()
        date_conf = 0.0
        found_date: date | None = None
        for match in self._DATE_FULL_RE.finditer(stripped):
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                found_date = date(year, month, day)
            except ValueError:
                continue
            break
        if found_date is None:
            for match in self._DATE_SHORT_RE.finditer(stripped):
                month = int(match.group(1))
                day = int(match.group(2))
                try:
                    found_date = date(today.year, month, day)
                except ValueError:
                    continue
                break
        if found_date is not None:
            occurred_on = found_date.isoformat()
            date_conf = 0.7

        return (
            merchant,
            amount_cents,
            occurred_on,
            {
                "merchant": merchant_conf,
                "amount_cents": amount_conf,
                "occurred_on": date_conf,
            },
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
    if name == "tesseract":
        return TesseractOcrProvider()
    if name == "env":
        return EnvOcrProvider()
    raise ValueError(f"未知的 OCR 提供商: {name!r}，允许 mock/tesseract/env")
