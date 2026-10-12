import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.services import by_category, monthly_summary, net_worth, trend

router = APIRouter(prefix="/api/stats", tags=["stats"])

# 月份格式校验：YYYY-MM
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _default_month() -> str:
    """返回当前月份字符串，格式 YYYY-MM。"""
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _validate_month(month: str) -> str:
    """校验月份参数，非法时抛出 400。"""
    if not month or not _MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month 必须为 YYYY-MM 格式")
    return month


@router.get("/summary")
async def get_summary(
    month: str | None = Query(default=None, description="月份，格式 YYYY-MM，缺省为当月"),
    session: AsyncSession = Depends(get_session),
):
    """获取指定月份的收支汇总。"""
    m = _validate_month(month) if month else _default_month()
    return await monthly_summary(session, m)


@router.get("/trend")
async def get_trend(
    months: int = Query(default=12, ge=1, le=24, description="统计月数，范围 1-24"),
    session: AsyncSession = Depends(get_session),
):
    """获取最近 N 个月的收支趋势。"""
    return await trend(session, months)


@router.get("/by-category")
async def get_by_category(
    month: str | None = Query(default=None, description="月份，格式 YYYY-MM，缺省为当月"),
    kind: str = Query(default="expense", description="类型：expense 或 income"),
    session: AsyncSession = Depends(get_session),
):
    """按分类统计指定月份的收支情况。"""
    if kind not in ("expense", "income"):
        raise HTTPException(status_code=400, detail="kind 必须为 expense 或 income")
    m = _validate_month(month) if month else _default_month()
    return await by_category(session, m, kind)


@router.get("/net-worth")
async def get_net_worth(
    session: AsyncSession = Depends(get_session),
):
    """获取净资产统计。"""
    return await net_worth(session)
