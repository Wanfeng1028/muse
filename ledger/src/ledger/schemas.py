"""Pydantic v2 数据校验模型（统一契约）。

所有金额字段一律为「分」整数，禁止浮点金额。
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 账户
# ---------------------------------------------------------------------------


class AccountCreate(BaseModel):
    """创建账户请求体。"""

    name: str
    type: Literal["cash", "savings", "credit", "ewallet", "investment"]
    currency: str = "CNY"
    opening_balance_cents: int = 0
    note: str = ""


class AccountUpdate(BaseModel):
    """更新账户请求体，全部字段可选。"""

    name: str | None = None
    type: Literal["cash", "savings", "credit", "ewallet", "investment"] | None = None
    currency: str | None = None
    opening_balance_cents: int | None = None
    note: str | None = None
    is_archived: bool | None = None


class AccountOut(BaseModel):
    """账户输出，附带计算后的余额（分）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    currency: str
    opening_balance_cents: int
    note: str
    is_archived: bool
    balance_cents: int
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    """创建分类请求体。"""

    name: str
    kind: Literal["income", "expense"]
    icon: str = ""
    color: str = ""
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    """更新分类请求体，全部字段可选。"""

    name: str | None = None
    kind: Literal["income", "expense"] | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    """分类输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    icon: str
    color: str
    sort_order: int


# ---------------------------------------------------------------------------
# 交易
# ---------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    """创建交易请求体。"""

    type: Literal["income", "expense", "transfer"]
    account_id: int
    to_account_id: int | None = None
    category_id: int | None = None
    amount_cents: int = Field(gt=0)
    occurred_on: date
    note: str = ""


class TransactionUpdate(BaseModel):
    """更新交易请求体；type/account_id 不可改（传了会报 422）。"""

    model_config = ConfigDict(extra="forbid")

    to_account_id: int | None = None
    category_id: int | None = None
    amount_cents: int | None = Field(default=None, gt=0)
    occurred_on: date | None = None
    note: str | None = None


class TransactionOut(BaseModel):
    """交易输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    account_id: int
    to_account_id: int | None
    category_id: int | None
    amount_cents: int
    occurred_on: str
    note: str
    created_at: str
    updated_at: str


class TransactionList(BaseModel):
    """交易分页列表。"""

    items: list[TransactionOut]
    total: int


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------


class BudgetCreate(BaseModel):
    """创建预算请求体。"""

    category_id: int
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount_cents: int = Field(gt=0)


class BudgetUpdate(BaseModel):
    """更新预算请求体，全部字段可选。"""

    category_id: int | None = None
    year_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    amount_cents: int | None = Field(default=None, gt=0)


class BudgetOut(BaseModel):
    """预算输出，附带已花、剩余与百分比。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    year_month: str
    amount_cents: int
    spent_cents: int
    remaining_cents: int
    pct: float
    category_name: str


# ---------------------------------------------------------------------------
# 定期记账
# ---------------------------------------------------------------------------


class RecurringCreate(BaseModel):
    """创建定期记账请求体。"""

    name: str
    type: Literal["income", "expense"]
    account_id: int
    category_id: int | None = None
    amount_cents: int = Field(gt=0)
    day_of_month: int = Field(ge=1, le=28)
    note: str = ""
    is_active: bool = True


class RecurringUpdate(BaseModel):
    """更新定期记账请求体，全部字段可选。"""

    name: str | None = None
    type: Literal["income", "expense"] | None = None
    account_id: int | None = None
    category_id: int | None = None
    amount_cents: int | None = Field(default=None, gt=0)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    note: str | None = None
    is_active: bool | None = None


class RecurringOut(BaseModel):
    """定期记账输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    account_id: int
    category_id: int | None
    amount_cents: int
    day_of_month: int
    note: str
    is_active: bool
    created_at: str
    updated_at: str


class UpcomingOut(RecurringOut):
    """即将到期的定期记账，附带下次发生日期 YYYY-MM-DD。"""

    next_date: str


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


class SummaryOut(BaseModel):
    """月度收支汇总。"""

    month: str
    income_cents: int
    expense_cents: int
    net_cents: int
    count: int


class TrendPoint(BaseModel):
    """趋势图单月数据点。"""

    month: str
    income_cents: int
    expense_cents: int


class CategoryStat(BaseModel):
    """按分类的统计项。"""

    category_id: int
    name: str
    icon: str
    color: str
    total_cents: int
    pct: float


class NetWorth(BaseModel):
    """净资产汇总。"""

    total_cents: int
    accounts: list[dict]


# ---------------------------------------------------------------------------
# 导入导出
# ---------------------------------------------------------------------------


class ImportResult(BaseModel):
    """CSV 导入结果。"""

    created: int
    skipped: int
    errors: list[str]
