# src/ledger/routers/accounts.py
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger import services
from ledger.database import get_session
from ledger.models import Account, Transaction
from ledger.schemas import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    TransactionList,
    TransactionOut,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    include_archived: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    """列出所有账户，含余额。"""
    items = await services.list_accounts_with_balance(session)
    if include_archived:
        res = await session.execute(select(Account).where(Account.is_archived == 1).order_by(Account.id))
        for acc in res.scalars().all():
            bal = await services.account_balance(session, acc.id)
            items.append(
                {
                    "id": acc.id,
                    "name": acc.name,
                    "type": acc.type,
                    "currency": acc.currency,
                    "opening_balance_cents": acc.opening_balance_cents,
                    "note": acc.note,
                    "is_archived": acc.is_archived,
                    "created_at": acc.created_at,
                    "updated_at": acc.updated_at,
                    "balance_cents": bal,
                }
            )
    return items


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
):
    """创建账户。"""
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="账户名称不能为空")

    now = _now_iso()
    acc = Account(
        name=name,
        type=payload.type,
        currency=payload.currency or "CNY",
        opening_balance_cents=payload.opening_balance_cents or 0,
        note=payload.note or "",
        is_archived=0,
        created_at=now,
        updated_at=now,
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    return AccountOut(
        id=acc.id,
        name=acc.name,
        type=acc.type,
        currency=acc.currency,
        opening_balance_cents=acc.opening_balance_cents,
        balance_cents=acc.opening_balance_cents,
        note=acc.note,
        is_archived=bool(acc.is_archived),
        created_at=acc.created_at,
        updated_at=acc.updated_at,
    )


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
):
    """获取单个账户详情。"""
    acc = await session.get(Account, account_id)
    if acc is None or acc.is_archived:
        raise HTTPException(status_code=404, detail="账户不存在")

    items = [i for i in await services.list_accounts_with_balance(session) if i["id"] == account_id]
    if items:
        return items[0]
    bal = await services.account_balance(session, acc.id)
    return AccountOut(
        id=acc.id,
        name=acc.name,
        type=acc.type,
        currency=acc.currency,
        opening_balance_cents=acc.opening_balance_cents,
        balance_cents=bal,
        note=acc.note,
        is_archived=bool(acc.is_archived),
        created_at=acc.created_at,
        updated_at=acc.updated_at,
    )


@router.put("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
):
    """部分更新账户。"""
    acc = await session.get(Account, account_id)
    if acc is None or acc.is_archived:
        raise HTTPException(status_code=404, detail="账户不存在")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="账户名称不能为空")
        acc.name = name
    if "type" in data and data["type"] is not None:
        acc.type = data["type"]
    if "currency" in data and data["currency"] is not None:
        acc.currency = data["currency"]
    if "opening_balance_cents" in data and data["opening_balance_cents"] is not None:
        acc.opening_balance_cents = data["opening_balance_cents"]
    if "note" in data and data["note"] is not None:
        acc.note = data["note"]

    acc.updated_at = _now_iso()
    await session.commit()
    await session.refresh(acc)

    items = [i for i in await services.list_accounts_with_balance(session) if i["id"] == account_id]
    if items:
        return items[0]
    bal = await services.account_balance(session, acc.id)
    return AccountOut(
        id=acc.id,
        name=acc.name,
        type=acc.type,
        currency=acc.currency,
        opening_balance_cents=acc.opening_balance_cents,
        balance_cents=bal,
        note=acc.note,
        is_archived=bool(acc.is_archived),
        created_at=acc.created_at,
        updated_at=acc.updated_at,
    )


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_session),
):
    """软删除账户（is_archived=1），交易保留。"""
    acc = await session.get(Account, account_id)
    if acc is None or acc.is_archived:
        raise HTTPException(status_code=404, detail="账户不存在")

    acc.is_archived = 1
    acc.updated_at = _now_iso()
    await session.commit()
    return None


@router.get("/{account_id}/transactions", response_model=TransactionList)
async def list_account_transactions(
    account_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """获取该账户相关交易（含转出与转入），按日期降序、id 降序。"""
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="账户不存在")

    cond = or_(
        Transaction.account_id == account_id,
        Transaction.to_account_id == account_id,
    )

    total_q = await session.execute(select(func.count()).select_from(Transaction).where(cond))
    total = int(total_q.scalar_one() or 0)

    stmt = (
        select(Transaction)
        .where(cond)
        .order_by(Transaction.occurred_on.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    items = [TransactionOut.model_validate(r) for r in rows]
    return TransactionList(items=items, total=total)
