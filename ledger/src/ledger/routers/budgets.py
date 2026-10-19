from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import Budget, Category
from ledger.services import budget_progress, budget_yearly

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


class BudgetCreate(BaseModel):
    category_id: int
    year_month: str = Field(min_length=7, max_length=7)
    amount_cents: int = Field(gt=0)


class BudgetUpdate(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)
    year_month: str | None = Field(default=None, min_length=7, max_length=7)


@router.get("")
async def list_budgets(
    month: str = Query(..., description="YYYY-MM"),
    session: AsyncSession = Depends(get_session),
):
    """按月份返回预算列表，含 spent/remaining/pct。"""
    return await budget_progress(session, month)


@router.get("/yearly")
async def get_yearly_overview(
    year: str = Query(..., description="YYYY"),
    session: AsyncSession = Depends(get_session),
):
    """年度总览：逐月汇总预算与支出。"""
    if len(year) != 4 or not year.isdigit():
        raise HTTPException(status_code=422, detail="year 必须为 4 位年份")
    months = await budget_yearly(session, int(year))
    return {"year": year, "months": months}


@router.post("", status_code=201)
async def create_budget(
    payload: BudgetCreate,
    session: AsyncSession = Depends(get_session),
):
    """创建预算；分类必须存在且为 expense。"""
    category = await session.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    if category.kind != "expense":
        raise HTTPException(status_code=400, detail="预算只能关联支出分类")

    budget = Budget(
        category_id=payload.category_id,
        year_month=payload.year_month,
        amount_cents=payload.amount_cents,
    )
    session.add(budget)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="该分类当月预算已存在")
    await session.refresh(budget)
    return {
        "id": budget.id,
        "category_id": budget.category_id,
        "year_month": budget.year_month,
        "amount_cents": budget.amount_cents,
    }


@router.put("/{budget_id}")
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    session: AsyncSession = Depends(get_session),
):
    """更新预算金额或月份；重复冲突返回 409。"""
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="预算不存在")

    data = payload.model_dump(exclude_unset=True)
    if "amount_cents" in data and data["amount_cents"] is not None:
        budget.amount_cents = data["amount_cents"]
    if "year_month" in data and data["year_month"] is not None:
        budget.year_month = data["year_month"]

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="该分类当月预算已存在")
    await session.refresh(budget)
    return {
        "id": budget.id,
        "category_id": budget.category_id,
        "year_month": budget.year_month,
        "amount_cents": budget.amount_cents,
    }


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_session),
):
    """删除预算。"""
    budget = await session.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="预算不存在")
    await session.delete(budget)
    await session.commit()
    return None
