# src/ledger/services.py
"""核心业务逻辑，供 routers 与页面复用。所有函数均为 async，接收 AsyncSession。"""

from __future__ import annotations

import calendar
import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.models import Account, Budget, Category, Recurring, Transaction

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def month_range(month: str) -> tuple[str, str]:
    """返回 (当月首日, 下月首日) 的 'YYYY-MM-DD' 字符串，用于 occurred_on 比较。"""
    year, mon = int(month[:4]), int(month[5:7])
    start = f"{year:04d}-{mon:02d}-01"
    if mon == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{mon + 1:02d}-01"
    return start, end


def _now_iso() -> str:
    """UTC ISO8601 时间字符串。"""
    return datetime.now(UTC).isoformat()


def _prev_month(month: str) -> str:
    """给定 'YYYY-MM' 返回上一个月。"""
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{mon - 1:02d}"


# ---------------------------------------------------------------------------
# 账户
# ---------------------------------------------------------------------------


async def account_balance(s: AsyncSession, account_id: int) -> int:
    """按契约余额公式计算单个账户余额（分）。"""
    acc = await s.get(Account, account_id)
    if acc is None:
        raise ValueError("account not found")

    # 收入流入（account_id = 该账户）
    income = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "income", Transaction.account_id == account_id
        )
    )
    # 支出流出（account_id = 该账户）
    expense = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "expense", Transaction.account_id == account_id
        )
    )
    # 转出（account_id = 该账户）
    transfer_out = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "transfer", Transaction.account_id == account_id
        )
    )
    # 转入（to_account_id = 该账户）
    transfer_in = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "transfer", Transaction.to_account_id == account_id
        )
    )

    return int(acc.opening_balance_cents) + int(income) - int(expense) - int(transfer_out) + int(transfer_in)


async def list_accounts_with_balance(s: AsyncSession) -> list[dict]:
    """全部未归档账户，附 balance_cents，按 id 升序。"""
    rows = (await s.execute(select(Account).where(Account.is_archived == 0).order_by(Account.id))).scalars().all()

    result: list[dict] = []
    for acc in rows:
        bal = await account_balance(s, acc.id)
        result.append(
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
    return result


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


async def monthly_summary(s: AsyncSession, month: str) -> dict:
    """当月收支合计、净额与交易笔数（transfer 不计入收支但计入 count）。"""
    start, end = month_range(month)

    income = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "income",
            Transaction.occurred_on >= start,
            Transaction.occurred_on < end,
        )
    )
    expense = await s.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.type == "expense",
            Transaction.occurred_on >= start,
            Transaction.occurred_on < end,
        )
    )
    count = await s.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.occurred_on >= start,
            Transaction.occurred_on < end,
        )
    )

    income_cents = int(income)
    expense_cents = int(expense)
    return {
        "month": month,
        "income_cents": income_cents,
        "expense_cents": expense_cents,
        "net_cents": income_cents - expense_cents,
        "count": int(count),
    }


async def trend(s: AsyncSession, months: int = 12) -> list[dict]:
    """最近 months 个自然月（含当月），按月升序。"""
    if months <= 0:
        months = 12

    today = date.today()
    cur = f"{today.year:04d}-{today.month:02d}"
    month_list: list[str] = []
    m = cur
    for _ in range(months):
        month_list.append(m)
        m = _prev_month(m)
    month_list.reverse()

    result: list[dict] = []
    for mon in month_list:
        start, end = month_range(mon)
        income = await s.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.type == "income",
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
        )
        expense = await s.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.type == "expense",
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
        )
        result.append(
            {
                "month": mon,
                "income_cents": int(income),
                "expense_cents": int(expense),
            }
        )
    return result


async def by_category(s: AsyncSession, month: str, kind: str = "expense") -> list[dict]:
    """当月该 kind 各分类合计，附分类名/icon/color，按合计降序，每项含 pct。"""
    start, end = month_range(month)

    rows = (
        await s.execute(
            select(
                Category.id,
                Category.name,
                Category.icon,
                Category.color,
                func.coalesce(func.sum(Transaction.amount_cents), 0).label("total"),
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .where(
                Transaction.type == kind,
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
            .group_by(Category.id)
            .order_by(func.sum(Transaction.amount_cents).desc())
        )
    ).all()

    grand_total = sum(int(r.total) for r in rows)
    result: list[dict] = []
    for r in rows:
        total = int(r.total)
        pct = round(total / grand_total * 100, 1) if grand_total > 0 else 0.0
        result.append(
            {
                "category_id": r.id,
                "name": r.name,
                "icon": r.icon,
                "color": r.color,
                "total_cents": total,
                "pct": pct,
            }
        )
    return result


async def net_worth(s: AsyncSession) -> dict:
    """全部未归档账户余额之和，附各账户余额列表。"""
    accounts = await list_accounts_with_balance(s)
    total = sum(a["balance_cents"] for a in accounts)
    return {
        "total_cents": total,
        "accounts": [{"id": a["id"], "name": a["name"], "balance_cents": a["balance_cents"]} for a in accounts],
    }


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------


async def budget_progress(s: AsyncSession, month: str) -> list[dict]:
    """当月全部预算，附分类名与 spent_cents/remaining_cents/pct。"""
    start, end = month_range(month)

    budgets = (
        await s.execute(
            select(Budget, Category.name)
            .join(Category, Category.id == Budget.category_id)
            .where(Budget.year_month == month)
            .order_by(Budget.id)
        )
    ).all()

    result: list[dict] = []
    for budget, cat_name in budgets:
        spent = await s.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.type == "expense",
                Transaction.category_id == budget.category_id,
                Transaction.occurred_on >= start,
                Transaction.occurred_on < end,
            )
        )
        spent_cents = int(spent)
        amount_cents = int(budget.amount_cents)
        remaining_cents = amount_cents - spent_cents
        pct = round(spent_cents / amount_cents * 100, 1) if amount_cents > 0 else 0.0
        result.append(
            {
                "id": budget.id,
                "category_id": budget.category_id,
                "category_name": cat_name,
                "year_month": budget.year_month,
                "amount_cents": amount_cents,
                "spent_cents": spent_cents,
                "remaining_cents": remaining_cents,
                "pct": pct,
            }
        )
    return result


# ---------------------------------------------------------------------------
# CSV 导入
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "收入": "income",
    "支出": "expense",
    "转账": "transfer",
    "income": "income",
    "expense": "expense",
    "transfer": "transfer",
}


async def import_csv_rows(s: AsyncSession, text: str) -> dict:
    """解析 CSV 并逐行写入交易。返回 {"created","skipped","errors"}。"""
    created = 0
    skipped = 0
    errors: list[str] = []

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"created": 0, "skipped": 0, "errors": []}

    # 首行为表头
    header = [h.strip().lower() for h in rows[0]]
    try:
        idx_date = header.index("date")
        idx_type = header.index("type")
        idx_account = header.index("account")
        idx_category = header.index("category")
        idx_amount = header.index("amount")
    except ValueError:
        return {
            "created": 0,
            "skipped": 0,
            "errors": ["表头缺少必需列(date,type,account,category,amount)"],
        }
    idx_note = header.index("note") if "note" in header else -1

    for line_no, raw in enumerate(rows[1:], start=2):
        # 空行跳过
        if not raw or all((c or "").strip() == "" for c in raw):
            skipped += 1
            continue

        def cell(i: int) -> str:
            return raw[i].strip() if i < len(raw) and raw[i] is not None else ""

        try:
            date_str = cell(idx_date)
            type_raw = cell(idx_type)
            account_name = cell(idx_account)
            category_name = cell(idx_category)
            amount_raw = cell(idx_amount)
            note = cell(idx_note) if idx_note >= 0 else ""

            # 日期校验
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"日期格式无效: {date_str}")

            # 类型校验
            txn_type = _TYPE_MAP.get(type_raw)
            if txn_type is None:
                raise ValueError(f"交易类型无效: {type_raw}")

            # 金额（元 -> 分）
            try:
                amount_yuan = Decimal(amount_raw)
            except (InvalidOperation, ValueError):
                raise ValueError(f"金额无效: {amount_raw}")
            amount_cents = int((amount_yuan * 100).to_integral_value())
            if amount_cents <= 0:
                raise ValueError(f"金额必须大于 0: {amount_raw}")

            # 账户匹配
            acc = await s.scalar(select(Account).where(Account.name == account_name, Account.is_archived == 0))
            if acc is None:
                raise ValueError(f"账户不存在: {account_name}")

            category_id = None
            to_account_id = None

            if txn_type == "transfer":
                # 转账：category 列表示目标账户
                to_acc = await s.scalar(select(Account).where(Account.name == category_name, Account.is_archived == 0))
                if to_acc is None:
                    raise ValueError(f"转入账户不存在: {category_name}")
                if to_acc.id == acc.id:
                    raise ValueError("转出与转入账户不能相同")
                to_account_id = to_acc.id
            else:
                # 收入/支出：category 按名称 + kind 匹配
                cat = await s.scalar(select(Category).where(Category.name == category_name, Category.kind == txn_type))
                if cat is None:
                    raise ValueError(f"分类不存在或类型不匹配: {category_name}")
                category_id = cat.id

            now = _now_iso()
            txn = Transaction(
                type=txn_type,
                account_id=acc.id,
                to_account_id=to_account_id,
                category_id=category_id,
                amount_cents=amount_cents,
                occurred_on=date_str,
                note=note,
                created_at=now,
                updated_at=now,
            )
            s.add(txn)
            created += 1
        except ValueError as e:
            errors.append(f"第{line_no}行: {e}")
            skipped += 1

    await s.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# 周期账单
# ---------------------------------------------------------------------------


async def upcoming_recurring(s: AsyncSession, days: int = 30) -> list[dict]:
    """is_active=1 的周期账单，计算 next_date，只返回距今 <= days 的，按 next_date 升序。"""
    if days < 0:
        days = 0

    items = (await s.execute(select(Recurring).where(Recurring.is_active == 1).order_by(Recurring.id))).scalars().all()

    today = date.today()
    result: list[dict] = []

    for rec in items:
        day = rec.day_of_month
        if day < 1 or day > 28:
            day = 1

        # 本月该日
        last_day_this = calendar.monthrange(today.year, today.month)[1]
        d_this = min(day, last_day_this)
        candidate = date(today.year, today.month, d_this)
        if candidate < today:
            # 下月
            if today.month == 12:
                y, m = today.year + 1, 1
            else:
                y, m = today.year, today.month + 1
            last_day_next = calendar.monthrange(y, m)[1]
            d_next = min(day, last_day_next)
            candidate = date(y, m, d_next)

        delta = (candidate - today).days
        if delta <= days:
            result.append(
                {
                    "id": rec.id,
                    "name": rec.name,
                    "type": rec.type,
                    "account_id": rec.account_id,
                    "category_id": rec.category_id,
                    "amount_cents": rec.amount_cents,
                    "day_of_month": rec.day_of_month,
                    "note": rec.note,
                    "is_active": rec.is_active,
                    "created_at": rec.created_at,
                    "updated_at": rec.updated_at,
                    "next_date": candidate.isoformat(),
                }
            )

    result.sort(key=lambda x: x["next_date"])
    return result
