"""交易路由：/api/transactions 及单条读写。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select

from ledger.currency import validate_currency_code
from ledger.database import get_session_factory
from ledger.models import Account, Category, Transaction
from ledger.schemas import TransactionUpdate

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

VALID_TYPES = ("income", "expense", "transfer")


class TransactionIn(BaseModel):
    """创建/更新交易请求体。"""

    type: str
    account_id: int
    to_account_id: int | None = None
    category_id: int | None = None
    amount_cents: int = Field(gt=0)
    occurred_on: str
    note: str = ""
    currency: str = "CNY"

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v: str) -> str:
        return validate_currency_code(v)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(t: Transaction) -> dict[str, Any]:
    return {
        "id": t.id,
        "type": t.type,
        "account_id": t.account_id,
        "to_account_id": t.to_account_id,
        "category_id": t.category_id,
        "amount_cents": t.amount_cents,
        "occurred_on": t.occurred_on,
        "note": t.note,
        "currency": t.currency,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


async def _validate(s, data: TransactionIn, is_update: bool = False) -> None:
    """校验交易业务规则，不合法抛 HTTPException(400)。"""
    if data.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail="非法的交易类型")

    # 账户必须存在且未归档
    acc = await s.get(Account, data.account_id)
    if acc is None:
        raise HTTPException(status_code=400, detail="账户不存在")
    if acc.is_archived:
        raise HTTPException(status_code=400, detail="账户已归档")

    # 转入账户校验
    if data.to_account_id is not None:
        if data.to_account_id == data.account_id:
            raise HTTPException(status_code=400, detail="转入账户不能与转出账户相同")
        to_acc = await s.get(Account, data.to_account_id)
        if to_acc is None:
            raise HTTPException(status_code=400, detail="转入账户不存在")
        if to_acc.is_archived:
            raise HTTPException(status_code=400, detail="转入账户已归档")

    # 分类校验
    category = None
    if data.category_id is not None:
        category = await s.get(Category, data.category_id)
        if category is None:
            raise HTTPException(status_code=400, detail="分类不存在")

    if data.type == "transfer":
        if data.to_account_id is None:
            raise HTTPException(status_code=400, detail="转账必须指定转入账户")
        if data.category_id is not None:
            raise HTTPException(status_code=400, detail="转账不能指定分类")
    else:
        if data.category_id is None:
            raise HTTPException(status_code=400, detail="收入/支出必须指定分类")
        if data.to_account_id is not None:
            raise HTTPException(status_code=400, detail="收入/支出不能指定转入账户")
        if category is not None and category.kind != data.type:
            raise HTTPException(status_code=400, detail="分类类型与交易类型不一致")


@router.get("")
async def list_transactions(
    account_id: int | None = None,
    category_id: int | None = None,
    type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """分页查询交易列表，返回 {items, total}。"""
    if type is not None and type != "":
        if type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail="type 参数非法")
    for value, name in ((date_from, "date_from"), (date_to, "date_to")):
        if value in (None, ""):
            continue
        try:
            datetime.strptime(value, "%Y-%m-%d")
            valid = len(value) == 10 and value[4] == "-" and value[7] == "-"
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise HTTPException(status_code=400, detail=f"{name} 参数非法")
    async with get_session_factory()() as s:
        conds = []
        if account_id is not None:
            # 转账按账户过滤时双向匹配
            conds.append(
                or_(
                    Transaction.account_id == account_id,
                    Transaction.to_account_id == account_id,
                )
            )
        if category_id is not None:
            conds.append(Transaction.category_id == category_id)
        if type:
            conds.append(Transaction.type == type)
        if date_from:
            conds.append(Transaction.occurred_on >= date_from)
        if date_to:
            conds.append(Transaction.occurred_on <= date_to)
        if q:
            conds.append(Transaction.note.like(f"%{q}%"))

        base = select(Transaction)
        cnt = select(func.count()).select_from(Transaction)
        for c in conds:
            base = base.where(c)
            cnt = cnt.where(c)

        total = (await s.execute(cnt)).scalar_one()
        rows = (
            (
                await s.execute(
                    base.order_by(Transaction.occurred_on.desc(), Transaction.id.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )

        return {"items": [_serialize(t) for t in rows], "total": total}


@router.post("", status_code=201)
async def create_transaction(payload: TransactionIn) -> dict[str, Any]:
    """创建交易。"""
    async with get_session_factory()() as s:
        await _validate(s, payload, is_update=False)
        now = _now()
        t = Transaction(
            type=payload.type,
            account_id=payload.account_id,
            to_account_id=payload.to_account_id,
            category_id=payload.category_id,
            amount_cents=payload.amount_cents,
            occurred_on=payload.occurred_on,
            note=payload.note,
            currency=payload.currency,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return _serialize(t)


@router.get("/{txn_id}")
async def get_transaction(txn_id: int) -> dict[str, Any]:
    """获取单条交易。"""
    async with get_session_factory()() as s:
        t = await s.get(Transaction, txn_id)
        if t is None:
            raise HTTPException(status_code=404, detail="交易不存在")
        return _serialize(t)


@router.put("/{txn_id}")
async def update_transaction(txn_id: int, payload: TransactionUpdate) -> dict[str, Any]:
    """部分更新交易（type 与 account_id 不可修改，请求体中不含这两项）。"""
    async with get_session_factory()() as s:
        t = await s.get(Transaction, txn_id)
        if t is None:
            raise HTTPException(status_code=404, detail="交易不存在")
        data = payload.model_dump(exclude_unset=True)
        occurred = data.get("occurred_on", t.occurred_on)
        if hasattr(occurred, "isoformat"):
            occurred = occurred.isoformat()
        merged = TransactionIn(
            type=t.type,
            account_id=t.account_id,
            to_account_id=data.get("to_account_id", t.to_account_id),
            category_id=data.get("category_id", t.category_id),
            amount_cents=data.get("amount_cents", t.amount_cents),
            occurred_on=occurred,
            note=data.get("note", t.note),
            currency=data.get("currency", t.currency),
        )
        await _validate(s, merged, is_update=True)

        t.to_account_id = merged.to_account_id
        t.category_id = merged.category_id
        t.amount_cents = merged.amount_cents
        t.occurred_on = merged.occurred_on
        t.note = merged.note
        t.currency = merged.currency
        t.updated_at = _now()
        await s.commit()
        await s.refresh(t)
        return _serialize(t)


@router.delete("/{txn_id}", status_code=204)
async def delete_transaction(txn_id: int) -> None:
    """删除交易。"""
    async with get_session_factory()() as s:
        t = await s.get(Transaction, txn_id)
        if t is None:
            raise HTTPException(status_code=404, detail="交易不存在")
        await s.delete(t)
        await s.commit()
    return None
