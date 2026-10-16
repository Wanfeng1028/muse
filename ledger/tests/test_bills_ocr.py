"""`POST /api/bills/ocr` 图片识别预填接口的测试。"""

from __future__ import annotations

import re

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


async def test_ocr_png_success(client):
    """正常 PNG 上传：返回 200 与 mock 预填结果。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["merchant"] == "星巴克臻选"
    assert data["amount_cents"] == 6800
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", data["occurred_on"])
    assert data["mock"] is True
    assert data["provider"] == "mock"
    first = data["candidates"][0]
    assert first["category_name"] == "餐饮"
    assert isinstance(first["category_id"], int)
    assert first["confidence"] == 0.92


async def test_ocr_rejects_non_image(client):
    """非图片文件（csv）被拒绝，422。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("bill.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert resp.status_code == 422
    assert "仅支持图片" in resp.json()["detail"]


async def test_ocr_rejects_oversized(client):
    """超过 5MB 的图片被拒绝，422。"""
    big = b"\x00" * (6 * 1024 * 1024)
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 422
    assert "超过 5MB" in resp.json()["detail"]


async def test_ocr_rejects_empty_file(client):
    """空文件被拒绝，422。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 422


async def test_ocr_env_without_key(client, monkeypatch):
    """LEDGER_OCR_PROVIDER=env 且未配置 key：422，诚实报错。"""
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "env")
    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 422
    assert "未配置真实 OCR 服务" in resp.json()["detail"]


async def test_ocr_env_with_key_not_implemented(client, monkeypatch):
    """LEDGER_OCR_PROVIDER=env 且配置了 key：501，真实提供商未接入。"""
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "env")
    monkeypatch.setenv("LEDGER_OCR_API_KEY", "dummy")
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 501


async def test_ocr_unknown_provider(client, monkeypatch):
    """LEDGER_OCR_PROVIDER=bogus：500，配置非法。"""
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "bogus")
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 500
    assert "配置非法" in resp.json()["detail"]


async def test_ocr_missing_file_field(client):
    """不带 file 字段：FastAPI 参数校验返回 422。"""
    resp = await client.post("/api/bills/ocr")
    assert resp.status_code == 422


async def test_ocr_no_extension_but_image_content_type(client):
    """无扩展名但 content_type 为 image/png：200。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200


async def test_ocr_empty_content_type_with_uppercase_ext(client):
    """content_type 为空但扩展名为 .JPG（大写）：200。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("photo.JPG", PNG_BYTES, "")},
    )
    assert resp.status_code == 200


async def test_ocr_confidence_in_range(client):
    """所有 candidates 的 confidence 落在 [0,1]。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    for cand in resp.json()["candidates"]:
        assert 0.0 <= cand["confidence"] <= 1.0


async def test_ocr_gif_success(client):
    """GIF（content_type image/gif）：200。"""
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.gif", PNG_BYTES, "image/gif")},
    )
    assert resp.status_code == 200
