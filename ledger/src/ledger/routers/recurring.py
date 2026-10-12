"""recurring 路由：定期收支计划的增删改查与即将到期查询。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger import services
from ledger.database import get_session
from ledger.models import Account, Category, Recurring
from ledger.schemas import (
    RecurringCreate,
    RecurringOut,
    RecurringUpdate,
    UpcomingOut,
)

router = APIRouter(prefix="/api/recurring", tags=["recurring"])


def _now_iso() -> str:
    """返回 UTC ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


async def _get_account(session: AsyncSession, account_id: int) -> Account:
    """按 id 获取账户，不存在则 404。"""
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户不存在")
    return account


async def _get_category(session: AsyncSession, category_id: int) -> Category:
    """按 id 获取分类，不存在则 404。"""
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    return category


async def _get_recurring(session: AsyncSession, recurring_id: int) -> Recurring:
    """按 id 获取定期计划，不存在则 404。"""
    item = await session.get(Recurring, recurring_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定期计划不存在")
    return item


def _validate_type_and_category(
    type_value: str,
    category: Category | None,
) -> None:
    """校验 type 与分类 kind 一致。"""
    if type_value not in ("income", "expense"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type 必须为 income 或 expense")
    if category is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须提供 category_id")
    if category.kind != type_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类类型与交易类型不一致")


@router.get("/upcoming", response_model=list[UpcomingOut])
async def list_upcoming(
    days: int = Query(default=30, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[UpcomingOut]:
    """查询未来 days 天内即将到期的启用中定期计划。"""
    return await services.upcoming_recurring(session, days=days)


@router.get("", response_model=list[RecurringOut])
async def list_recurring(
    session: AsyncSession = Depends(get_session),
) -> list[Recurring]:
    """列出全部定期计划，按 is_active 降序、id 升序。"""
    stmt = select(Recurring).order_by(Recurring.is_active.desc(), Recurring.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=RecurringOut, status_code=status.HTTP_201_CREATED)
async def create_recurring(
    payload: RecurringCreate,
    session: AsyncSession = Depends(get_session),
) -> Recurring:
    """创建定期计划，校验账户与分类存在性。"""
    await _get_account(session, payload.account_id)
    category = None
    if payload.category_id is not None:
        category = await _get_category(session, payload.category_id)
    _validate_type_and_category(payload.type, category)

    if not (1 <= payload.day_of_month <= 28):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="day_of_month 必须在 1~28 之间")

    now = _now_iso()
    item = Recurring(
        name=payload.name,
        type=payload.type,
        account_id=payload.account_id,
        category_id=payload.category_id,
        amount_cents=payload.amount_cents,
        day_of_month=payload.day_of_month,
        note=payload.note,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/{recurring_id}", response_model=RecurringOut)
async def get_recurring(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
) -> Recurring:
    """获取单个定期计划。"""
    return await _get_recurring(session, recurring_id)


@router.put("/{recurring_id}", response_model=RecurringOut)
async def update_recurring(
    recurring_id: int,
    payload: RecurringUpdate,
    session: AsyncSession = Depends(get_session),
) -> Recurring:
    """更新定期计划。"""
    item = await _get_recurring(session, recurring_id)
    data = payload.model_dump(exclude_unset=True)

    if "account_id" in data and data["account_id"] is not None:
        await _get_account(session, data["account_id"])

    category = None
    if "category_id" in data and data["category_id"] is not None:
        category = await _get_category(session, data["category_id"])

    new_type = data.get("type", item.type)
    new_category_id = data.get("category_id", item.category_id)

    if new_type not in ("income", "expense"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type 必须为 income 或 expense")
    if new_category_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须提供 category_id")
    if category is None:
        category = await _get_category(session, new_category_id)
    if category.kind != new_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类类型与交易类型不一致")

    if "day_of_month" in data and data["day_of_month"] is not None:
        if not (1 <= data["day_of_month"] <= 28):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="day_of_month 必须在 1~28 之间")

    for field, value in data.items():
        setattr(item, field, value)

    item.updated_at = _now_iso()
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(
    recurring_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """删除定期计划。"""
    item = await _get_recurring(session, recurring_id)
    await session.delete(item)
    await session.commit()
    return None
