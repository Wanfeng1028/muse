"""导入导出路由：CSV 导入与导出。"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.database import get_session
from ledger.models import Account, Category, Transaction
from ledger.schemas import ImportResult
from ledger.services import import_csv_rows

router = APIRouter(tags=["import-export"])


@router.post("/api/import/csv", response_model=ImportResult)
async def import_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ImportResult:
    """从上传的 CSV 文件导入交易记录。"""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return await import_csv_rows(session, text)


def _format_amount_yuan(amount_cents: int) -> str:
    """将「分」整数格式化为「元」字符串，去掉多余零。"""
    value = Decimal(amount_cents) / Decimal(100)
    normalized = value.normalize()
    # 避免科学计数法，例如 1E+2
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "" or text == "-":
        text = "0"
    return text


_TYPE_TO_CN = {"income": "收入", "expense": "支出", "transfer": "转账"}


@router.get("/api/export/csv")
async def export_csv(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """导出交易为 CSV 文件。"""
    stmt = select(Transaction)
    if date_from is not None:
        stmt = stmt.where(Transaction.occurred_on >= date_from.isoformat())
    if date_to is not None:
        stmt = stmt.where(Transaction.occurred_on <= date_to.isoformat())
    stmt = stmt.order_by(Transaction.occurred_on.asc(), Transaction.id.asc())

    result = await session.execute(stmt)
    transactions = list(result.scalars().all())

    # 预取账户与分类名称
    account_ids = set()
    category_ids = set()
    for tx in transactions:
        account_ids.add(tx.account_id)
        if tx.to_account_id is not None:
            account_ids.add(tx.to_account_id)
        if tx.category_id is not None:
            category_ids.add(tx.category_id)

    account_names: dict[int, str] = {}
    if account_ids:
        acc_rows = await session.execute(select(Account.id, Account.name).where(Account.id.in_(account_ids)))
        for aid, aname in acc_rows.all():
            account_names[aid] = aname

    category_names: dict[int, str] = {}
    if category_ids:
        cat_rows = await session.execute(select(Category.id, Category.name).where(Category.id.in_(category_ids)))
        for cid, cname in cat_rows.all():
            category_names[cid] = cname

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "type", "account", "category", "amount", "note"])

    for tx in transactions:
        type_cn = _TYPE_TO_CN.get(tx.type, tx.type)
        account_name = account_names.get(tx.account_id, "")
        if tx.type == "transfer" and tx.to_account_id is not None:
            to_name = account_names.get(tx.to_account_id, "")
            account_name = f"{account_name}->{to_name}"
        category_name = ""
        if tx.type != "transfer" and tx.category_id is not None:
            category_name = category_names.get(tx.category_id, "")
        writer.writerow(
            [
                tx.occurred_on,
                type_cn,
                account_name,
                category_name,
                _format_amount_yuan(tx.amount_cents),
                tx.note or "",
            ]
        )

    content = buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ledger-export.csv"'},
    )
