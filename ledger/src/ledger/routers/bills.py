"""账单相关路由：图片 OCR 识别预填接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import Category
from ledger.ocr import OcrFailedError, OcrNotConfiguredError, get_provider

router = APIRouter(prefix="/api/bills", tags=["bills"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@router.post("/ocr")
async def ocr_bill(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """上传账单图片，OCR 识别后返回预填账单 JSON。"""
    # 文件名校验
    if not file.filename:
        raise HTTPException(status_code=422, detail="文件名为空")

    # 类型校验：content_type 以 image/ 开头，或扩展名在允许列表内
    content_type = file.content_type or ""
    filename_lower = file.filename.lower()
    has_allowed_ext = any(filename_lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)
    if not content_type.startswith("image/") and not has_allowed_ext:
        raise HTTPException(
            status_code=422,
            detail="仅支持图片文件（PNG/JPG/WebP/GIF/BMP）",
        )

    # 读取并校验大小
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="图片内容为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="图片超过 5MB 限制")

    # 获取提供商
    try:
        provider = get_provider()
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"OCR 提供商配置非法：{exc}",
        ) from exc

    # 调用识别
    try:
        result = await provider.recognize(raw, file.filename or "", file.content_type or "")
    except OcrNotConfiguredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except OcrFailedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 候选分类解析：查库映射 category_id，confidence 钳制到 [0,1]
    candidates: list[dict] = []
    for cand in result.candidates:
        category_name = cand.get("category_name", "")
        stmt = select(Category.id).where(
            Category.name == category_name,
            Category.kind == "expense",
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        raw_conf = cand.get("confidence", 0.0)
        try:
            conf = float(raw_conf)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        candidates.append(
            {
                "category_id": int(row) if row is not None else None,
                "category_name": category_name,
                "confidence": conf,
            }
        )

    return {
        "merchant": result.merchant,
        "amount_cents": result.amount_cents,
        "occurred_on": result.occurred_on,
        "candidates": candidates,
        "provider": result.provider,
        "mock": result.mock,
    }
