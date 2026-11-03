from __future__ import annotations

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


async def _make_account(client) -> int:
    resp = await client.post(
        "/api/accounts",
        json={"name": "现金钱包", "type": "cash", "opening_balance_cents": 0},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_food_category_id(client) -> int:
    resp = await client.get("/api/categories", params={"kind": "expense"})
    assert resp.status_code == 200
    for cat in resp.json():
        if cat["name"] == "餐饮":
            return cat["id"]
    raise AssertionError("未找到餐饮分类")


async def _upload_ocr(client, filename="receipt.png", content=PNG_BYTES, ctype="image/png") -> int:
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": (filename, content, ctype)},
    )
    assert resp.status_code == 200
    return resp.json()["review_id"]


# ---------- ocr.py 纯函数 / 纯逻辑 ----------


def test_classify_reason_unknown_status_falls_to_internal():
    from ledger.routers.bills import _classify_bills_ocr_reason

    assert _classify_bills_ocr_reason(418, "whatever") == "internal"
    assert _classify_bills_ocr_reason(200, "ok") == "internal"


def test_classify_reason_501_is_unavailable():
    from ledger.routers.bills import _classify_bills_ocr_reason

    assert _classify_bills_ocr_reason(501, "not implemented") == "unavailable"


def test_classify_reason_422_detail_mapping():
    from ledger.routers.bills import _classify_bills_ocr_reason

    assert _classify_bills_ocr_reason(422, "仅支持图片文件（PNG/JPG/WebP/GIF/BMP）") == "unsupported"
    assert _classify_bills_ocr_reason(422, "图片超过 5MB 限制") == "oversize"
    assert _classify_bills_ocr_reason(422, "文件名为空") == "invalid"
    assert _classify_bills_ocr_reason(422, "图片内容为空") == "invalid"
    assert _classify_bills_ocr_reason(422, "完全没见过的 detail") == "invalid"


def test_classify_reason_500_is_invalid():
    from ledger.routers.bills import _classify_bills_ocr_reason

    assert _classify_bills_ocr_reason(500, "OCR 提供商配置非法：xxx") == "invalid"


def test_get_provider_unknown_name_raises_value_error(monkeypatch):
    from ledger.ocr import get_provider

    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "totally-unknown")
    with pytest.raises(ValueError):
        get_provider()


def test_get_provider_default_is_mock(monkeypatch):
    from ledger.ocr import MockOcrProvider, get_provider

    monkeypatch.delenv("LEDGER_OCR_PROVIDER", raising=False)
    provider = get_provider()
    assert isinstance(provider, MockOcrProvider)


def test_get_provider_env_returns_env_provider(monkeypatch):
    from ledger.ocr import EnvOcrProvider, get_provider

    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "  Env  ")
    provider = get_provider()
    assert isinstance(provider, EnvOcrProvider)


def test_serialize_review_bad_confidence_json_gives_empty_dict():
    from ledger.routers.bills import _serialize_review

    class Row:
        id = 1
        merchant = "m"
        amount_cents = 100
        occurred_on = "2024-01-01"
        provider = "mock"
        mock = 1
        status = "pending"
        category_id = None
        transaction_id = None
        created_at = "now"
        field_confidence = "not-json"

    out = _serialize_review(Row())
    assert out["field_confidence"] == {}


def test_serialize_review_non_dict_json_gives_empty_dict():
    from ledger.routers.bills import _serialize_review

    class Row:
        id = 2
        merchant = "m"
        amount_cents = 100
        occurred_on = "2024-01-01"
        provider = "mock"
        mock = 0
        status = "rejected"
        category_id = 5
        transaction_id = None
        created_at = "now"
        field_confidence = "[1, 2, 3]"

    out = _serialize_review(Row())
    assert out["field_confidence"] == {}
    assert out["mock"] == 0
    assert out["category_id"] == 5


def test_validate_date_accepts_valid_format():
    from ledger.routers.bills import _validate_date

    assert _validate_date("2024-02-29") == "2024-02-29"


def test_validate_date_rejects_non_iso():
    from fastapi import HTTPException

    from ledger.routers.bills import _validate_date

    with pytest.raises(HTTPException) as exc_info:
        _validate_date("2024/05/01")
    assert exc_info.value.status_code == 422


def test_mask_dates_blanks_out_full_and_short_dates():
    from ledger.ocr import TesseractOcrProvider

    provider = TesseractOcrProvider.__new__(TesseractOcrProvider)
    masked = provider._mask_dates("2024年10月16日 消费 12.34")
    assert "2024" not in masked
    assert "10" not in masked
    assert "12.34" in masked


def test_parse_extracts_amount_and_date_from_text():
    from ledger.ocr import TesseractOcrProvider

    provider = TesseractOcrProvider.__new__(TesseractOcrProvider)
    merchant, amount_cents, occurred_on, conf = provider._parse(
        "全家便利店\n合计 45.60 元\n2024-05-06"
    )
    assert merchant == "全家便利店"
    assert amount_cents == 4560
    assert occurred_on == "2024-05-06"
    assert conf["occurred_on"] == pytest.approx(0.7)


def test_parse_empty_text_defaults():
    from ledger.ocr import TesseractOcrProvider

    provider = TesseractOcrProvider.__new__(TesseractOcrProvider)
    merchant, amount_cents, occurred_on, conf = provider._parse("")
    assert merchant == ""
    assert amount_cents == 0
    assert conf["merchant"] == 0.0


def test_word_confidence_avg_returns_none_on_empty_payload_gracefully():
    from ledger.ocr import TesseractOcrProvider

    provider = TesseractOcrProvider.__new__(TesseractOcrProvider)
    provider._lang = "eng"
    provider._timeout = 5
    provider._psm = 6
    # 不可解析为图片时 tesseract 会失败，函数应返回 None 而不抛错
    assert provider._word_confidence_avg(b"") is None


def test_tesseract_provider_timeout_env_invalid_falls_back(monkeypatch):
    from ledger.ocr import TesseractOcrProvider

    monkeypatch.setenv("LEDGER_OCR_TIMEOUT", "abc")
    provider = TesseractOcrProvider()
    assert provider._timeout == 30


def test_tesseract_provider_timeout_env_too_small_falls_back(monkeypatch):
    from ledger.ocr import TesseractOcrProvider

    monkeypatch.setenv("LEDGER_OCR_TIMEOUT", "2")
    provider = TesseractOcrProvider()
    assert provider._timeout == 30


def test_tesseract_provider_lang_env_blank_falls_back(monkeypatch):
    from ledger.ocr import TesseractOcrProvider

    monkeypatch.setenv("LEDGER_OCR_LANG", "   ")
    provider = TesseractOcrProvider()
    assert provider._lang == "chi_sim+eng"


# ---------- ocr.py 异步提供商行为 ----------


async def test_mock_provider_empty_image_raises_failed():
    from ledger.ocr import MockOcrProvider, OcrFailedError

    with pytest.raises(OcrFailedError):
        await MockOcrProvider().recognize(b"", "a.png", "image/png")


async def test_mock_provider_ocr_lines_empty_image_raises():
    from ledger.ocr import MockOcrProvider, OcrFailedError

    with pytest.raises(OcrFailedError):
        await MockOcrProvider().ocr_lines(b"")


async def test_env_provider_without_api_key_raises_not_configured(monkeypatch):
    from ledger.ocr import EnvOcrProvider, OcrNotConfiguredError

    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)
    with pytest.raises(OcrNotConfiguredError):
        await EnvOcrProvider().recognize(b"x", "a.png", "image/png")


async def test_env_provider_with_api_key_raises_not_implemented(monkeypatch):
    from ledger.ocr import EnvOcrProvider

    monkeypatch.setenv("LEDGER_OCR_API_KEY", "secret-key")
    with pytest.raises(NotImplementedError):
        await EnvOcrProvider().recognize(b"x", "a.png", "image/png")


async def test_tesseract_ocr_lines_missing_binary_raises_unavailable(monkeypatch):
    from ledger.ocr import OcrUnavailableError, TesseractOcrProvider

    monkeypatch.setattr("ledger.ocr.shutil.which", lambda name: None)
    with pytest.raises(OcrUnavailableError):
        await TesseractOcrProvider().ocr_lines(PNG_BYTES)


# ---------- HTTP 边界 ----------


async def test_ocr_empty_filename_returns_422(client):
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert len(detail) > 0
    assert "file" in detail[0]["loc"]


async def test_ocr_unsupported_extension_and_content_type_returns_422(client):
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "仅支持图片文件（PNG/JPG/WebP/GIF/BMP）"


async def test_ocr_allowed_extension_without_image_content_type_accepted(client):
    # 扩展名在允许列表内即可，content_type 非 image/ 也放行
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.JPG", PNG_BYTES, "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "mock"


async def test_ocr_empty_body_returns_422(client):
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "图片内容为空"


async def test_ocr_oversize_returns_422(client):
    from ledger.routers.bills import MAX_IMAGE_BYTES

    big = PNG_BYTES + b"\x00" * (MAX_IMAGE_BYTES + 1 - len(PNG_BYTES))
    assert len(big) > MAX_IMAGE_BYTES
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "图片超过 5MB 限制"


async def test_ocr_exact_max_bytes_accepted(client):
    from ledger.routers.bills import MAX_IMAGE_BYTES

    exact = PNG_BYTES + b"\x00" * (MAX_IMAGE_BYTES - len(PNG_BYTES))
    assert len(exact) == MAX_IMAGE_BYTES
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("exact.png", exact, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["mock"] is True


async def test_ocr_unknown_provider_returns_500(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "no-such-provider")
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 500
    assert "OCR 提供商配置非法" in resp.json()["detail"]


async def test_ocr_env_provider_not_configured_returns_422(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "env")
    monkeypatch.delenv("LEDGER_OCR_API_KEY", raising=False)
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 422
    assert "LEDGER_OCR_API_KEY" in resp.json()["detail"]


async def test_ocr_env_provider_configured_returns_501(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "env")
    monkeypatch.setenv("LEDGER_OCR_API_KEY", "abc")
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 501


async def test_ocr_candidates_confidence_clamped_and_category_lookup(client):
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["amount_cents"] == 6800
    names = [c["category_name"] for c in body["candidates"]]
    assert names == ["餐饮", "购物"]
    for cand in body["candidates"]:
        assert 0.0 <= cand["confidence"] <= 1.0
    # 餐饮分类存在，应映射到真实 id
    assert body["candidates"][0]["category_id"] is not None


async def test_ocr_missing_file_field_returns_422(client):
    resp = await client.post("/api/bills/ocr")
    assert resp.status_code == 422


async def test_review_image_returns_stored_content_type_for_jpeg(client):
    review_id = await _upload_ocr(client, filename="receipt.jpeg", ctype="image/jpeg")
    resp = await client.get(f"/api/bills/review/{review_id}/image")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == PNG_BYTES


async def test_confirm_negative_amount_returns_422(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)
    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "m",
            "amount_cents": -1,
            "occurred_on": "2024-05-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 422


async def test_confirm_bad_date_format_returns_422(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)
    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "m",
            "amount_cents": 100,
            "occurred_on": "2024/05/01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "日期格式非法，应为 YYYY-MM-DD"


async def test_confirm_note_provided_uses_note_not_default(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)
    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "星巴克臻选",
            "amount_cents": 1234,
            "occurred_on": "2024-06-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "自定义备注",
        },
    )
    assert resp.status_code == 200
    tx_id = resp.json()["transaction_id"]
    tx_resp = await client.get(f"/api/transactions/{tx_id}")
    assert tx_resp.status_code == 200
    assert tx_resp.json()["note"] == "自定义备注"


async def test_confirm_missing_review_returns_404(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    resp = await client.post(
        "/api/bills/review/999999/confirm",
        json={
            "merchant": "m",
            "amount_cents": 100,
            "occurred_on": "2024-05-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 404


async def test_list_reviews_empty_when_nothing_uploaded(client):
    resp = await client.get("/api/bills/review")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_confirm_missing_required_field_returns_422(client):
    review_id = await _upload_ocr(client)
    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={"amount_cents": 100, "occurred_on": "2024-05-01"},
    )
    assert resp.status_code == 422


async def test_confirm_rejected_state_unchanged_after_409(client):
    review_id = await _upload_ocr(client)
    reject = await client.post(f"/api/bills/review/{review_id}/reject")
    assert reject.status_code == 200

    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    resp = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "m",
            "amount_cents": 100,
            "occurred_on": "2024-05-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert resp.status_code == 409

    # 记录应仍为 rejected 且不出现在 pending 列表
    listing = await client.get("/api/bills/review")
    assert listing.json()["items"] == []


async def test_review_image_content_type_fallback_when_missing(client):
    # 上传时 content_type 为空，落库应回退为 image/png
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "")},
    )
    assert resp.status_code == 200
    review_id = resp.json()["review_id"]
    img = await client.get(f"/api/bills/review/{review_id}/image")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/png")


async def test_ocr_metrics_not_failing_main_flow(client, monkeypatch):
    # 让埋点函数抛异常，主流程仍应成功返回
    import ledger.routers.bills as bills_mod

    def boom(*args, **kwargs):
        raise RuntimeError("metrics down")

    monkeypatch.setattr(bills_mod, "record_bills_ocr_request", boom)
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("receipt.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "mock"


async def test_ocr_metrics_failure_hook_exception_swallowed(client, monkeypatch):
    import ledger.routers.bills as bills_mod

    def boom(*args, **kwargs):
        raise RuntimeError("failure metric down")

    # 触发失败路径（空文件）时埋点异常不应改变响应
    monkeypatch.setattr(bills_mod, "record_bills_ocr_failure", boom)
    resp = await client.post(
        "/api/bills/ocr",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "图片内容为空"


async def test_list_reviews_field_confidence_parsed_as_dict(client):
    review_id = await _upload_ocr(client)
    listing = await client.get("/api/bills/review")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == review_id
    fc = items[0]["field_confidence"]
    assert isinstance(fc, dict)
    assert fc.get("merchant") == pytest.approx(0.95)


async def test_confirm_then_reject_returns_409(client):
    account_id = await _make_account(client)
    category_id = await _get_food_category_id(client)
    review_id = await _upload_ocr(client)
    confirm = await client.post(
        f"/api/bills/review/{review_id}/confirm",
        json={
            "merchant": "m",
            "amount_cents": 100,
            "occurred_on": "2024-05-01",
            "category_id": category_id,
            "account_id": account_id,
            "note": "",
        },
    )
    assert confirm.status_code == 200
    reject = await client.post(f"/api/bills/review/{review_id}/reject")
    assert reject.status_code == 409
    assert reject.json()["detail"] == "该记录已处理，不可重复驳回"