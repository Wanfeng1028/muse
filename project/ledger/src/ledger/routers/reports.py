"""月度收支报告路由。

提供分类口径的读取/写入，以及按月份聚合的收支报告接口。
所有金额均以整数分进行运算，避免浮点误差。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Category, ReportScheme, Transaction

router = APIRouter(prefix="/api/reports", tags=["reports"])

# 月份格式严格校验：四位年 + 两位月（01-12）
YEAR_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# 未命中口径 mapping 的分类统一归入该桶
UNCATEGORIZED_BUCKET = "未分类"
# 收入类交易统一归入该桶，不参与口径 mapping
INCOME_BUCKET = "收入"
# note 为空时的商户名
NO_NOTE_MERCHANT = "未备注"

# 默认口径，表空时自动写入
DEFAULT_SCHEME: dict[str, Any] = {
    "name": "9月口径",
    "mapping": {
        "考研投入": ["教育"],
        "一次性大项": ["数码", "住房"],
        "饮食": ["餐饮"],
        "日用": ["日用"],
        "话费": ["其他"],
        "交通": ["交通"],
    },
}


class SchemePutIn(BaseModel):
    """PUT /category-scheme 请求体。"""

    name: str = Field(min_length=1)
    mapping: dict[str, list[str]]

    @field_validator("mapping")
    @classmethod
    def _check_mapping(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        """校验桶名非空，且桶内分类名列表不为空。"""
        if not value:
            raise ValueError("mapping 不能为空")
        for bucket, names in value.items():
            if not bucket or not bucket.strip():
                raise ValueError("桶名不能为空")
            if not names:
                raise ValueError(f"桶 {bucket} 的分类列表不能为空")
        return value


def _validate_year_month(year_month: str) -> str:
    """校验 year_month 格式，非法时抛 422。"""
    if not YEAR_MONTH_PATTERN.match(year_month):
        raise HTTPException(status_code=422, detail="year_month 格式必须为 YYYY-MM")
    return year_month


def _prev_year_month(year_month: str) -> str:
    """计算上一个月份，正确处理跨年（如 2026-01 的上月是 2025-12）。"""
    year = int(year_month[:4])
    month = int(year_month[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _month_range(year_month: str) -> tuple[str, str]:
    """返回该月的起始日与结束日（含），均为 YYYY-MM-DD 字符串。"""
    year = int(year_month[:4])
    month = int(year_month[5:7])
    start = date(year, month, 1)
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    end = date.fromordinal(nxt.toordinal() - 1)
    return start.isoformat(), end.isoformat()


def _extract_merchant(note: str | None) -> str:
    """从 note 提取商户名：取首个空格前的 token；note 为空则返回未备注。"""
    if not note or not note.strip():
        return NO_NOTE_MERCHANT
    return note.strip().split(" ", 1)[0]


async def _load_categories(session: AsyncSession) -> list[Category]:
    """读取全部分类。"""
    result = await session.execute(select(Category))
    return list(result.scalars().all())


async def _ensure_default_scheme(session: AsyncSession) -> None:
    """表为空时自动写入默认口径。"""
    result = await session.execute(select(ReportScheme).limit(1))
    if result.scalars().first() is not None:
        return
    row = ReportScheme(
        name=DEFAULT_SCHEME["name"],
        scheme_json=json.dumps(DEFAULT_SCHEME["mapping"], ensure_ascii=False),
    )
    session.add(row)
    await session.commit()


async def _load_schemes(session: AsyncSession) -> list[dict[str, Any]]:
    """读取全部口径，按 updated_at 倒序（最新在前）。"""
    result = await session.execute(
        select(ReportScheme).order_by(ReportScheme.updated_at.desc(), ReportScheme.name)
    )
    schemes: list[dict[str, Any]] = []
    for row in result.scalars().all():
        schemes.append(
            {
                "name": row.name,
                "mapping": json.loads(row.scheme_json),
                "updated_at": row.updated_at,
            }
        )
    return schemes


async def _get_scheme_mapping(session: AsyncSession, name: str) -> dict[str, list[str]]:
    """按名称读取口径 mapping，不存在时抛 404。"""
    result = await session.execute(select(ReportScheme).where(ReportScheme.name == name))
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"口径不存在: {name}")
    return json.loads(row.scheme_json)


@router.get("/category-scheme")
async def get_category_scheme(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """读取全部分类口径，表空时自动写入默认口径。"""
    await _ensure_default_scheme(session)
    schemes = await _load_schemes(session)
    active = schemes[0]["name"] if schemes else None
    return {"schemes": schemes, "active": active}


@router.put("/category-scheme")
async def put_category_scheme(
    payload: SchemePutIn, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """写入或更新分类口径，校验分类名必须真实存在。"""
    categories = await _load_categories(session)
    valid_names = {c.name for c in categories}

    invalid: list[str] = []
    for names in payload.mapping.values():
        for category_name in names:
            if category_name not in valid_names and category_name not in invalid:
                invalid.append(category_name)
    if invalid:
        raise HTTPException(status_code=400, detail=f"非法分类名: {', '.join(invalid)}")

    result = await session.execute(select(ReportScheme).where(ReportScheme.name == payload.name))
    row = result.scalars().first()
    scheme_json = json.dumps(payload.mapping, ensure_ascii=False)
    if row is None:
        row = ReportScheme(name=payload.name, scheme_json=scheme_json)
        session.add(row)
    else:
        row.scheme_json = scheme_json
    await session.commit()
    return {"ok": True, "name": payload.name}


@router.get("/monthly")
async def get_monthly_report(
    year_month: str = Query(...),
    scheme: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """生成指定月份的收支报告。"""
    _validate_year_month(year_month)

    # 确定口径名：显式指定则校验存在性，否则取 active
    await _ensure_default_scheme(session)
    schemes = await _load_schemes(session)
    if scheme is None:
        if not schemes:
            raise HTTPException(status_code=404, detail="暂无可用口径")
        scheme = schemes[0]["name"]
    mapping = await _get_scheme_mapping(session, scheme)

    # 分类 id -> 分类对象
    categories = await _load_categories(session)
    category_by_id = {c.id: c for c in categories}
    # 分类名 -> 桶名
    bucket_of_category: dict[str, str] = {}
    for bucket, names in mapping.items():
        for category_name in names:
            bucket_of_category[category_name] = bucket

    # 读取本月与上月交易
    this_start, this_end = _month_range(year_month)
    last_year_month = _prev_year_month(year_month)
    last_start, last_end = _month_range(last_year_month)

    result = await session.execute(
        select(Transaction).where(
            Transaction.occurred_on >= this_start,
            Transaction.occurred_on <= this_end,
        )
    )
    this_txns = list(result.scalars().all())

    result = await session.execute(
        select(Transaction).where(
            Transaction.occurred_on >= last_start,
            Transaction.occurred_on <= last_end,
        )
    )
    last_txns = list(result.scalars().all())

    income_cents = 0
    expense_cents = 0
    tx_count = 0

    # 分类聚合：category_id -> {"amount_cents", "count", "kind"}
    category_agg: dict[int | None, dict[str, Any]] = {}
    # 桶聚合：bucket -> {"amount_cents", "count", "kind"}
    bucket_agg: dict[str, dict[str, Any]] = {}
    # 商户聚合：merchant -> {"amount_cents", "count"}（仅支出）
    merchant_agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {"amount_cents": 0, "count": 0}
    )

    for txn in this_txns:
        # transfer 不计入收支
        if txn.type == "transfer":
            continue
        tx_count += 1

        if txn.type == "income":
            income_cents += txn.amount_cents
        elif txn.type == "expense":
            expense_cents += txn.amount_cents

        # 分类聚合
        cat = category_by_id.get(txn.category_id) if txn.category_id else None
        cat_key = txn.category_id
        entry = category_agg.get(cat_key)
        if entry is None:
            entry = {
                "category_id": txn.category_id,
                "name": cat.name if cat else "未分类",
                "kind": cat.kind if cat else txn.type,
                "amount_cents": 0,
                "count": 0,
            }
            category_agg[cat_key] = entry
        entry["amount_cents"] += txn.amount_cents
        entry["count"] += 1

        # 桶聚合：收入统一归收入桶，支出按口径 mapping
        if txn.type == "income":
            bucket_name = INCOME_BUCKET
            bucket_kind = "income"
        else:
            if cat is not None and cat.name in bucket_of_category:
                bucket_name = bucket_of_category[cat.name]
            else:
                bucket_name = UNCATEGORIZED_BUCKET
            bucket_kind = "expense"

        bucket_entry = bucket_agg.get(bucket_name)
        if bucket_entry is None:
            bucket_entry = {
                "bucket": bucket_name,
                "kind": bucket_kind,
                "amount_cents": 0,
                "count": 0,
            }
            bucket_agg[bucket_name] = bucket_entry
        bucket_entry["amount_cents"] += txn.amount_cents
        bucket_entry["count"] += 1

        # 商户 Top 榜（仅支出）
        if txn.type == "expense":
            merchant = _extract_merchant(txn.note)
            merchant_agg[merchant]["amount_cents"] += txn.amount_cents
            merchant_agg[merchant]["count"] += 1

    # 上月按分类聚合，用于环比
    last_category_agg: dict[int | None, int] = defaultdict(int)
    for txn in last_txns:
        if txn.type == "transfer":
            continue
        last_category_agg[txn.category_id] += txn.amount_cents

    by_category = sorted(
        category_agg.values(), key=lambda item: item["amount_cents"], reverse=True
    )

    buckets = sorted(
        bucket_agg.values(), key=lambda item: item["amount_cents"], reverse=True
    )

    # 环比：本月有交易的分类全列
    mom: list[dict[str, Any]] = []
    for entry in category_agg.values():
        cat_key = entry["category_id"]
        this_cents = entry["amount_cents"]
        last_cents = last_category_agg.get(cat_key, 0)
        delta_cents = this_cents - last_cents
        if last_cents == 0:
            delta_pct = None
        else:
            delta_pct = round(delta_cents / last_cents * 100, 1)
        mom.append(
            {
                "category_id": cat_key,
                "name": entry["name"],
                "this_cents": this_cents,
                "last_cents": last_cents,
                "delta_cents": delta_cents,
                "delta_pct": delta_pct,
            }
        )
    mom.sort(key=lambda item: abs(item["delta_cents"]), reverse=True)

    top_merchants = sorted(
        (
            {"merchant": name, "amount_cents": agg["amount_cents"], "count": agg["count"]}
            for name, agg in merchant_agg.items()
        ),
        key=lambda item: item["amount_cents"],
        reverse=True,
    )[:10]

    return {
        "year_month": year_month,
        "income_cents": income_cents,
        "expense_cents": expense_cents,
        "net_cents": income_cents - expense_cents,
        "tx_count": tx_count,
        "by_category": by_category,
        "buckets": buckets,
        "mom": mom,
        "top_merchants": top_merchants,
    }
