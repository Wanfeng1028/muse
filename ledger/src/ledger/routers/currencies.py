"""汇率路由：/api/currencies 读写。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.config import get_settings
from ledger.currency import validate_currency_code
from ledger.database import get_session
from ledger.models import Currency
from ledger.schemas import CurrencyRateIn

router = APIRouter(prefix="/api/currencies", tags=["currencies"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


@router.get("")
async def list_currencies(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """列出全部汇率，按币种代码升序。"""
    rows = (await session.execute(select(Currency).order_by(Currency.code))).scalars().all()
    return [{"code": c.code, "rate_to_base": c.rate_to_base, "updated_at": c.updated_at} for c in rows]


@router.put("/{code}")
async def upsert_currency(
    code: str, payload: CurrencyRateIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """新增或更新某币种兑本位币汇率。本位币汇率恒为 1，不可修改。"""
    try:
        norm = validate_currency_code(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if norm == get_settings().base_currency:
        raise HTTPException(status_code=400, detail="本位币汇率恒为 1，不可修改")
    now = _now()
    cur = await session.get(Currency, norm)
    if cur is None:
        cur = Currency(code=norm, rate_to_base=payload.rate_to_base, updated_at=now)
        session.add(cur)
    else:
        cur.rate_to_base = payload.rate_to_base
        cur.updated_at = now
    await session.commit()
    await session.refresh(cur)
    return {"code": cur.code, "rate_to_base": cur.rate_to_base, "updated_at": cur.updated_at}
