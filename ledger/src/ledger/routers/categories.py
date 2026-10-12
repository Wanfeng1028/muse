"""分类相关 API 路由。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import Budget, Category, Transaction
from ledger.schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])

# 允许的分类类型
_VALID_KINDS = {"income", "expense"}


async def _name_conflict(session: AsyncSession, name: str, kind: str, exclude_id: int | None = None) -> bool:
    """检查同名同 kind 的分类是否已存在。"""
    stmt = select(Category.id).where(Category.name == name, Category.kind == kind)
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    result = await session.execute(stmt)
    return result.first() is not None


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    kind: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """列出分类，可按 kind 过滤，按 kind、sort_order、id 排序。"""
    stmt = select(Category)
    if kind is not None:
        if kind not in _VALID_KINDS:
            raise HTTPException(status_code=400, detail="kind 参数必须为 income 或 expense")
        stmt = stmt.where(Category.kind == kind)
    stmt = stmt.order_by(Category.kind, Category.sort_order, Category.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    payload: CategoryCreate,
    session: AsyncSession = Depends(get_session),
):
    """创建分类；同名同 kind 返回 409。"""
    if payload.kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail="kind 必须为 income 或 expense")
    if await _name_conflict(session, payload.name, payload.kind):
        raise HTTPException(status_code=409, detail="同名同类型的分类已存在")

    category = Category(
        name=payload.name,
        kind=payload.kind,
        icon=payload.icon or "",
        color=payload.color or "",
        sort_order=payload.sort_order or 0,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
):
    """更新分类；改 kind 时若已被交易引用返回 409；name 冲突返回 409。"""
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")

    new_name = payload.name if payload.name is not None else category.name
    new_kind = payload.kind if payload.kind is not None else category.kind

    if payload.kind is not None and payload.kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail="kind 必须为 income 或 expense")

    # 修改 kind 时，检查是否已有交易引用
    if payload.kind is not None and payload.kind != category.kind:
        count_stmt = select(func.count(Transaction.id)).where(Transaction.category_id == category_id)
        count = (await session.execute(count_stmt)).scalar_one()
        if count > 0:
            raise HTTPException(status_code=409, detail="该分类已被交易引用，无法修改类型")

    # 检查 name + kind 唯一性
    if await _name_conflict(session, new_name, new_kind, exclude_id=category_id):
        raise HTTPException(status_code=409, detail="同名同类型的分类已存在")

    category.name = new_name
    category.kind = new_kind
    if payload.icon is not None:
        category.icon = payload.icon
    if payload.color is not None:
        category.color = payload.color
    if payload.sort_order is not None:
        category.sort_order = payload.sort_order

    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
):
    """删除分类；被交易或预算引用返回 409。"""
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")

    txn_count = (
        await session.execute(select(func.count(Transaction.id)).where(Transaction.category_id == category_id))
    ).scalar_one()
    if txn_count > 0:
        raise HTTPException(status_code=409, detail=f"该分类已被 {txn_count} 条交易引用，无法删除")

    budget_count = (
        await session.execute(select(func.count(Budget.id)).where(Budget.category_id == category_id))
    ).scalar_one()
    if budget_count > 0:
        raise HTTPException(status_code=409, detail=f"该分类已被 {budget_count} 条预算引用，无法删除")

    await session.delete(category)
    await session.commit()
    return None
