import json
import shutil

import pytest

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


def png_file(name="bill.png", content=PNG_BYTES, ctype="image/png"):
    return {"file": (name, content, ctype)}


@pytest.mark.asyncio
async def test_ocr_preview_ok(client):
    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["encoding"] == "ocr"
    assert body["template_name"] == "微信支付"
    assert "交易时间" in body["headers"]
    assert body["total_rows"] == 4
    assert body["sample"][0]["counterparty"]
    assert body["ocr_text"].splitlines()[0] == "交易时间,交易对方,商品,金额(元),收/支"


@pytest.mark.asyncio
async def test_ocr_bad_image(client):
    files = {"file": ("bill.png", b"this is definitely not an image", "image/png")}
    resp = await client.post("/api/statements/ocr", files=files)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_ocr_oversize(client):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)
    files = {"file": ("bill.png", big, "image/png")}
    resp = await client.post("/api/statements/ocr", files=files)
    assert resp.status_code == 413, resp.text


@pytest.mark.asyncio
async def test_ocr_not_image(client):
    files = {"file": ("bill.txt", b"hello", "text/plain")}
    resp = await client.post("/api/statements/ocr", files=files)
    assert resp.status_code == 415, resp.text

    files2 = {"file": ("bill.png", PNG_BYTES, "text/plain")}
    resp2 = await client.post("/api/statements/ocr", files=files2)
    assert resp2.status_code == 415, resp2.text


@pytest.mark.asyncio
async def test_ocr_unavailable_503(client, monkeypatch):
    monkeypatch.setenv("LEDGER_OCR_PROVIDER", "tesseract")
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    resp = await client.post("/api/statements/ocr", files=png_file())
    assert resp.status_code == 503, resp.text
    detail = resp.json().get("detail", "")
    assert "apt install tesseract" in detail


@pytest.mark.asyncio
async def test_ocr_empty_file(client):
    files = {"file": ("bill.png", b"", "image/png")}
    resp = await client.post("/api/statements/ocr", files=files)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_ocr_full_chain_claim_and_rule(client):
    preview = await client.post("/api/statements/ocr", files=png_file())
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    ocr_text = preview_body["ocr_text"]
    mapping = preview_body["mapping"]

    account_resp = await client.post("/api/accounts", json={"name": "OCR测试账户", "type": "cash"})
    assert account_resp.status_code == 201, account_resp.text
    account_id = account_resp.json()["id"]

    upload_resp = await client.post(
        "/api/statements/upload",
        files={"file": ("ocr.csv", ocr_text.encode("utf-8"), "text/csv")},
        data={
            "account_id": str(account_id),
            "mapping": json.dumps(mapping),
        },
    )
    assert upload_resp.status_code == 200, upload_resp.text
    upload_body = upload_resp.json()
    batch_id = upload_body["batch"]["id"]
    assert upload_body["parsed"] >= 3

    confirm_resp = await client.post(f"/api/statements/{batch_id}/confirm")
    assert confirm_resp.status_code == 200, confirm_resp.text

    items_resp = await client.get(f"/api/statements/{batch_id}/items")
    assert items_resp.status_code == 200, items_resp.text
    items = items_resp.json()["items"]
    pending = [it for it in items if it["status"] == "pending"]
    assert pending
    item_id = pending[0]["id"]

    cats_resp = await client.get("/api/categories")
    assert cats_resp.status_code == 200, cats_resp.text
    cats = cats_resp.json()
    expense_cats = [c for c in cats if c["kind"] == "expense"]
    assert expense_cats
    cid = expense_cats[0]["id"]

    claim_resp = await client.post(
        f"/api/statements/items/{item_id}/claim",
        json={"category_id": cid, "save_rule": True},
    )
    assert claim_resp.status_code == 200, claim_resp.text

    rules_resp = await client.get("/api/match-rules")
    assert rules_resp.status_code == 200, rules_resp.text
    rules = rules_resp.json()
    assert isinstance(rules, list)
    assert len(rules) > 0
