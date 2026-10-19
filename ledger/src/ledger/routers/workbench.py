"""对账差异工作台接口。

提供批次列表、条目列表、单条处理与批量处理能力。
所有路径均挂载在 /api/workbench 前缀下。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import (
    Account,
    Category,
    MatchRule,
    MerchantAlias,
    StatementBatch,
    StatementItem,
    Transaction,
    utcnow,
)
from ledger.routers.statements import (
    _apply_claim,
    _direction_matches_kind,
)

router = APIRouter(prefix="/api/workbench", tags=["workbench"])

# 允许的处理动作集合
_ALLOWED_ACTIONS = {"confirm", "ignore", "learn", "transfer"}

# page_size 上限
_MAX_PAGE_SIZE = 200


class ResolvePayload(BaseModel):
    """单条条目处理入参。"""

    action: str
    category_id: Optional[int] = None
    to_account_id: Optional[int] = None
    save_rule: bool = False


class ResolveBatchPayload(BaseModel):
    """批量条目处理入参。"""

    item_ids: list[int] = Field(default_factory=list)
    action: str
    category_id: Optional[int] = None


async def _get_item_or_404(session: AsyncSession, item_id: int) -> StatementItem:
    """按 id 读取条目，不存在则抛 404。"""
    item = await session.get(StatementItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    return item


async def _get_batch_or_404(session: AsyncSession, batch_id: int) -> StatementBatch:
    """按 id 读取批次，不存在则抛 404。"""
    batch = await session.get(StatementBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="批次不存在")
    return batch


async def _load_category_or_400(session: AsyncSession, category_id: Optional[int]) -> Category:
    """读取分类，缺失则抛 400。"""
    if category_id is None:
        raise HTTPException(status_code=400, detail="缺少 category_id")
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=400, detail="分类不存在")
    return category


def _bump_rule_hit_count(item: StatementItem) -> None:
    """条目命中规则时递增规则命中计数。

    仅在 suggested_rule_id 非空且 match_source 以 rule 开头时生效。
    """
    if item.suggested_rule_id is None:
        return
    if not (item.match_source or "").startswith("rule"):
        return
    return


async def _increment_rule_hit(session: AsyncSession, item: StatementItem) -> None:
    """按条目记录递增规则 hit_count。"""
    if item.suggested_rule_id is None:
        return
    if not (item.match_source or "").startswith("rule"):
        return
    rule = await session.get(MatchRule, item.suggested_rule_id)
    if rule is None:
        return
    rule.hit_count = (rule.hit_count or 0) + 1


async def _do_confirm(
    session: AsyncSession,
    item: StatementItem,
    batch: StatementBatch,
    category_id: Optional[int],
    save_rule: bool,
) -> dict[str, Any]:
    """执行 confirm 动作，复用认领核心逻辑。"""
    category = await _load_category_or_400(session, category_id)
    if not _direction_matches_kind(item.direction, category.kind):
        raise HTTPException(status_code=400, detail="分类类型与收支方向不匹配")

    await _apply_claim(session, item, batch, category.id, save_rule, False)
    await _increment_rule_hit(session, item)
    await session.commit()
    return {
        "ok": True,
        "item_id": item.id,
        "status": item.status,
        "transaction_id": item.transaction_id,
    }


async def _do_learn(
    session: AsyncSession,
    item: StatementItem,
    batch: StatementBatch,
    category_id: Optional[int],
) -> dict[str, Any]:
    """执行 learn 动作：新建关键词规则并完成入账。"""
    category = await _load_category_or_400(session, category_id)

    keyword = (item.counterparty or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="条目对手方为空，无法学习规则")

    exists_stmt = select(MatchRule.id).where(
        MatchRule.keyword == keyword,
        MatchRule.pattern_type == "keyword",
        MatchRule.direction == item.direction,
    )
    exists = (await session.execute(exists_stmt)).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="相同规则已存在")

    rule = MatchRule(
        keyword=keyword,
        pattern_type="keyword",
        category_id=category.id,
        direction=item.direction,
        priority=0,
        is_enabled=True,
        hit_count=0,
    )
    session.add(rule)
    await session.flush()

    await _apply_claim(session, item, batch, category.id, False, False)
    await session.commit()
    return {
        "ok": True,
        "item_id": item.id,
        "status": item.status,
        "transaction_id": item.transaction_id,
        "rule_id": rule.id,
    }


async def _do_transfer(
    session: AsyncSession,
    item: StatementItem,
    batch: StatementBatch,
    to_account_id: Optional[int],
) -> dict[str, Any]:
    """执行 transfer 动作：生成转账交易并将条目置为 claimed。"""
    if to_account_id is None:
        raise HTTPException(status_code=400, detail="缺少 to_account_id")

    to_account = await session.get(Account, to_account_id)
    if to_account is None:
        raise HTTPException(status_code=404, detail="目标账户不存在")

    if to_account_id == batch.account_id:
        raise HTTPException(status_code=400, detail="目标账户不能与批次账户相同")

    tx = Transaction(
        type="transfer",
        account_id=batch.account_id,
        to_account_id=to_account_id,
        category_id=None,
        amount_cents=item.amount_cents,
        occurred_on=item.occurred_on,
        note=item.summary or item.counterparty,
        currency="CNY",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(tx)
    await session.flush()

    item.status = "claimed"
    item.transaction_id = tx.id
    item.claimed_category_id = None
    if batch.pending_count and batch.pending_count > 0:
        batch.pending_count -= 1
    await session.commit()
    return {
        "ok": True,
        "item_id": item.id,
        "status": item.status,
        "transaction_id": tx.id,
    }


async def _do_ignore(
    session: AsyncSession,
    item: StatementItem,
    batch: StatementBatch,
) -> dict[str, Any]:
    """执行 ignore 动作：条目置 skipped 并修正待处理计数。"""
    item.status = "skipped"
    if batch.pending_count and batch.pending_count > 0:
        batch.pending_count -= 1
    await session.commit()
    return {
        "ok": True,
        "item_id": item.id,
        "status": item.status,
        "transaction_id": None,
    }


async def _resolve_single(
    session: AsyncSession,
    item_id: int,
    action: str,
    category_id: Optional[int],
    to_account_id: Optional[int],
    save_rule: bool,
) -> dict[str, Any]:
    """处理单条条目，返回结果字典，异常抛出由上层捕获。"""
    item = await _get_item_or_404(session, item_id)
    if item.status != "pending":
        raise HTTPException(status_code=400, detail="仅可处理 pending 状态的条目")
    batch = await _get_batch_or_404(session, item.batch_id)

    if action == "confirm":
        return await _do_confirm(session, item, batch, category_id, save_rule)
    if action == "learn":
        return await _do_learn(session, item, batch, category_id)
    if action == "transfer":
        return await _do_transfer(session, item, batch, to_account_id)
    if action == "ignore":
        return await _do_ignore(session, item, batch)
    raise HTTPException(status_code=422, detail="不支持的动作")


@router.get("/batches")
async def list_batches(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """返回批次列表，含账户名称，按 id 倒序。"""
    stmt = (
        select(StatementBatch, Account.name)
        .outerjoin(Account, Account.id == StatementBatch.account_id)
        .order_by(StatementBatch.id.desc())
    )
    rows = (await session.execute(stmt)).all()

    items = []
    for batch, account_name in rows:
        items.append(
            {
                "id": batch.id,
                "filename": batch.filename,
                "account_id": batch.account_id,
                "status": batch.status,
                "total_count": batch.total_count,
                "pending_count": batch.pending_count,
                "created_at": batch.created_at,
                "account_name": account_name,
            }
        )
    return {"items": items}


@router.get("/batches/{batch_id}/items")
async def list_batch_items(
    batch_id: int,
    status: str = Query("pending"),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """分页返回批次内条目，支持状态过滤与关键词搜索。"""
    await _get_batch_or_404(session, batch_id)

    filters = [StatementItem.batch_id == batch_id]
    if status != "all":
        filters.append(StatementItem.status == status)

    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                StatementItem.counterparty.ilike(like),
                StatementItem.summary.ilike(like),
            )
        )

    total = (
        await session.execute(
            select(func.count(StatementItem.id)).where(*filters)
        )
    ).scalar_one()

    stmt = (
        select(StatementItem, Category.name)
        .outerjoin(Category, Category.id == StatementItem.suggested_category_id)
        .where(*filters)
        .order_by(StatementItem.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()

    items = []
    for item, category_name in rows:
        items.append(
            {
                "id": item.id,
                "occurred_on": item.occurred_on,
                "counterparty": item.counterparty,
                "summary": item.summary,
                "amount_cents": item.amount_cents,
                "direction": item.direction,
                "match_source": item.match_source,
                "confidence": item.confidence,
                "suggested_category_id": item.suggested_category_id,
                "suggested_category_name": category_name,
                "candidates": [],
            }
        )
    return {"items": items, "total": total, "page": page}


@router.post("/items/{item_id}/resolve")
async def resolve_item(
    item_id: int,
    payload: ResolvePayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """处理单条条目，支持 confirm/ignore/learn/transfer。"""
    if payload.action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=422, detail="不支持的动作")

    return await _resolve_single(
        session,
        item_id,
        payload.action,
        payload.category_id,
        payload.to_account_id,
        payload.save_rule,
    )


@router.post("/batches/{batch_id}/resolve-batch")
async def resolve_batch(
    batch_id: int,
    payload: ResolveBatchPayload,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """批量处理条目，逐条处理并返回部分成功语义。"""
    if payload.action not in {"confirm", "ignore"}:
        raise HTTPException(status_code=422, detail="批量仅支持 confirm 或 ignore")

    await _get_batch_or_404(session, batch_id)

    ok_ids: list[int] = []
    failed: list[dict[str, Any]] = []

    for item_id in payload.item_ids:
        try:
            await _resolve_single(
                session,
                item_id,
                payload.action,
                payload.category_id,
                None,
                False,
            )
            ok_ids.append(item_id)
        except HTTPException as exc:
            await session.rollback()
            failed.append({"id": item_id, "reason": str(exc.detail)})

    return {"ok": ok_ids, "failed": failed}
