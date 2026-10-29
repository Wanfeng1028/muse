"""账单相关路由：图片 OCR 识别、审核队列（确认入账/驳回）。"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.logging import get_logger
from ledger.models import Category, OcrReview
from ledger.ocr import OcrFailedError, OcrNotConfiguredError, get_provider
from ledger.ocr_metrics import record_bills_ocr_failure, record_bills_ocr_request
from ledger.routers.transactions import TransactionIn, create_transaction

router = APIRouter(prefix="/api/bills", tags=["bills"])

_logger = get_logger("bills")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _classify_bills_ocr_reason(status_code: int, detail: str) -> str:
    """把 bills OCR 的 HTTP 状态码与 detail 映射为失败分类 reason。"""
    if status_code == 501:
        return "unavailable"
    if status_code == 422:
        if detail == "仅支持图片文件（PNG/JPG/WebP/GIF/BMP）":
            return "unsupported"
        if detail == "图片超过 5MB 限制":
            return "oversize"
        if detail == "文件名为空" or detail == "图片内容为空":
            return "invalid"
        return "invalid"
    if status_code == 500:
        return "invalid"
    return "internal"


@router.post("/ocr")
async def ocr_bill(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """上传账单图片，OCR 识别后返回预填账单 JSON。

    全路径指标埋点：每次请求都计数（result=ok|error）并记录耗时；
    失败请求另按原因分类计数（reason=unavailable|unsupported|invalid|oversize|internal）。
    埋点自身异常只记 warning，永不影响主流程。
    """
    _start = time.perf_counter()
    _result = "error"
    _reason: str | None = None
    try:
        out = await _ocr_bill_impl(file=file, session=session)
    except OcrNotConfiguredError as exc:
        _reason = "unavailable"
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotImplementedError as exc:
        _reason = "unavailable"
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except HTTPException as exc:
        _reason = _classify_bills_ocr_reason(exc.status_code or 500, str(exc.detail))
        raise
    except Exception:
        _reason = "internal"
        raise
    else:
        _result = "ok"
        return out
    finally:
        # 埋点永不影响主流程
        try:
            record_bills_ocr_request(_result, time.perf_counter() - _start)
            if _reason is not None:
                record_bills_ocr_failure(_reason)
        except Exception as exc:
            _logger.warning(
                "ocr_metrics_record_failed",
                extra={"extra_data": {"error": repr(exc)}},
            )


async def _ocr_bill_impl(
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

    # 识别结果入审核队列（待人工确认/驳回）
    now = datetime.now(UTC).isoformat()
    review = OcrReview(
        image=raw,
        content_type=file.content_type or "image/png",
        filename=file.filename or "",
        merchant=result.merchant,
        amount_cents=result.amount_cents,
        occurred_on=result.occurred_on,
        raw_text=result.raw_text,
        provider=result.provider,
        mock=1 if result.mock else 0,
        category_id=candidates[0]["category_id"] if candidates else None,
        field_confidence=json.dumps(result.field_confidence, ensure_ascii=False),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    return {
        "review_id": review.id,
        "merchant": result.merchant,
        "amount_cents": result.amount_cents,
        "occurred_on": result.occurred_on,
        "candidates": candidates,
        "provider": result.provider,
        "mock": result.mock,
        "field_confidence": result.field_confidence,
    }


def _serialize_review(row: OcrReview) -> dict:
    """序列化审核记录；field_confidence 解析失败时给空 dict。"""
    try:
        fc = json.loads(row.field_confidence or "{}")
    except (TypeError, ValueError):
        fc = {}
    if not isinstance(fc, dict):
        fc = {}
    return {
        "id": row.id,
        "merchant": row.merchant,
        "amount_cents": row.amount_cents,
        "occurred_on": row.occurred_on,
        "provider": row.provider,
        "mock": row.mock,
        "status": row.status,
        "category_id": row.category_id,
        "transaction_id": row.transaction_id,
        "created_at": row.created_at,
        "field_confidence": fc,
    }


class ReviewConfirmIn(BaseModel):
    """审核确认入账请求体。"""

    merchant: str = ""
    amount_cents: int = Field(gt=0)
    occurred_on: str
    category_id: int
    account_id: int
    note: str = ""


def _validate_date(value: str) -> str:
    """校验 YYYY-MM-DD 日期格式，非法抛 HTTPException(422)。"""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="日期格式非法，应为 YYYY-MM-DD") from None
    return value


@router.get("/review")
async def list_reviews(session: AsyncSession = Depends(get_session)) -> dict:
    """列出待审核的 OCR 记录（id 倒序）。"""
    stmt = select(OcrReview).where(OcrReview.status == "pending").order_by(OcrReview.id.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return {"items": [_serialize_review(r) for r in rows]}


@router.get("/review/{review_id}/image")
async def review_image(review_id: int, session: AsyncSession = Depends(get_session)) -> Response:
    """返回审核记录的原图。"""
    row = await session.get(OcrReview, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    return Response(content=row.image, media_type=row.content_type or "image/png")


async def _confirm_one(session: AsyncSession, review_id: int, payload: ReviewConfirmIn) -> dict:
    """确认单条审核记录并入账（不 commit，由调用方决定提交/回滚）。"""
    row = await session.get(OcrReview, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="该记录已处理，不可重复确认")
    _validate_date(payload.occurred_on)
    txn = await create_transaction(
        TransactionIn(
            type="expense",
            account_id=payload.account_id,
            category_id=payload.category_id,
            amount_cents=payload.amount_cents,
            occurred_on=payload.occurred_on,
            note=payload.note or f"拍照记账：{payload.merchant}",
            currency="CNY",
        )
    )
    row.status = "confirmed"
    row.transaction_id = int(txn["id"])
    row.updated_at = datetime.now(UTC).isoformat()
    await session.flush()
    return {"transaction_id": int(txn["id"]), "review_id": row.id}


async def _reject_one(session: AsyncSession, review_id: int) -> dict:
    """驳回单条审核记录（不 commit，由调用方决定提交/回滚）。"""
    row = await session.get(OcrReview, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="该记录已处理，不可重复驳回")
    row.status = "rejected"
    row.updated_at = datetime.now(UTC).isoformat()
    await session.flush()
    return {"id": row.id, "status": row.status}


@router.post("/review/{review_id}/confirm")
async def confirm_review(
    review_id: int,
    payload: ReviewConfirmIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """确认审核记录并入账：创建支出交易，记录关联。"""
    result = await _confirm_one(session, review_id, payload)
    await session.commit()
    return result


@router.post("/review/{review_id}/reject")
async def reject_review(review_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    """驳回审核记录。"""
    result = await _reject_one(session, review_id)
    await session.commit()
    return result


class ReviewBatchItem(BaseModel):
    """批量确认时的单条入参：review_id + ReviewConfirmIn 全字段。"""

    review_id: int
    merchant: str = ""
    amount_cents: int = Field(gt=0)
    occurred_on: str
    category_id: int
    account_id: int
    note: str = ""


class ReviewBatchIn(BaseModel):
    """批量操作请求体。"""

    action: str
    items: list


@router.post("/review/batch")
async def review_batch(
    payload: ReviewBatchIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量确认或驳回审核记录，逐条独立处理。

    reject 分支循环结束统一 commit；confirm 分支逐条 commit，避免与
    create_transaction 内部新 session 争抢 SQLite 写锁。
    非 HTTP 异常同样逐条记入 failed，不中断整批。
    """
    if payload.action not in ("confirm", "reject"):
        raise HTTPException(status_code=400, detail="action 非法，应为 confirm 或 reject")
    if not payload.items:
        raise HTTPException(status_code=400, detail="items 不可为空")

    succeeded: list[dict] = []
    failed: list[dict] = []

    if payload.action == "reject":
        for raw in payload.items:
            try:
                review_id = int(raw)
            except (TypeError, ValueError):
                failed.append({"review_id": raw, "error": "review_id 非法"})
                continue
            try:
                result = await _reject_one(session, review_id)
            except HTTPException as exc:
                await session.rollback()
                failed.append({"review_id": review_id, "error": str(exc.detail)})
                continue
            except Exception as exc:
                await session.rollback()
                _logger.warning(
                    "batch_item_failed",
                    extra={"extra_data": {"action": "reject", "review_id": review_id, "error": repr(exc)}},
                )
                failed.append({"review_id": review_id, "error": "处理失败"})
                continue
            await session.commit()
            succeeded.append({"review_id": result["id"], "status": result["status"]})
    else:
        for raw in payload.items:
            try:
                item = ReviewBatchItem(**raw)
            except Exception as exc:
                rid = raw.get("review_id") if isinstance(raw, dict) else None
                failed.append({"review_id": rid, "error": str(exc)})
                continue
            confirm_payload = ReviewConfirmIn(
                merchant=item.merchant,
                amount_cents=item.amount_cents,
                occurred_on=item.occurred_on,
                category_id=item.category_id,
                account_id=item.account_id,
                note=item.note,
            )
            try:
                result = await _confirm_one(session, item.review_id, confirm_payload)
            except HTTPException as exc:
                await session.rollback()
                failed.append({"review_id": item.review_id, "error": str(exc.detail)})
                continue
            except Exception as exc:
                await session.rollback()
                _logger.warning(
                    "batch_item_failed",
                    extra={"extra_data": {"action": "confirm", "review_id": item.review_id, "error": repr(exc)}},
                )
                failed.append({"review_id": item.review_id, "error": "处理失败"})
                continue
            await session.commit()
            succeeded.append(
                {
                    "review_id": result["review_id"],
                    "transaction_id": result["transaction_id"],
                }
            )

    return {"succeeded": succeeded, "failed": failed}
