"""数据库模型定义（SQLAlchemy 2.0 声明式）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ledger.database import Base


def utcnow() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


class Account(Base):
    """账户表：现金/储蓄/信用卡/电子钱包/投资账户。"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="CNY")
    opening_balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Category(Base):
    """分类表：收入/支出分类。"""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "kind", name="uq_categories_name_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str] = mapped_column(String, nullable=False, default="")
    color: Mapped[str] = mapped_column(String, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Transaction(Base):
    """交易表：收入/支出/转账。"""

    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="ck_transactions_amount_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    to_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_on: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String, nullable=False, default="CNY")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class Currency(Base):
    """汇率表：币种代码 -> 兑本位币汇率。rate_to_base 语义：1 单位该币种主单位 = 多少本位币元。"""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    rate_to_base: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class Budget(Base):
    """预算表：按分类 + 月份设定预算金额。"""

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("category_id", "year_month", name="uq_budgets_category_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    year_month: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class Recurring(Base):
    """周期性收支规则表。"""

    __tablename__ = "recurring"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class StatementTemplate(Base):
    """账单模板表：保存账单来源与列映射。"""

    __tablename__ = "statement_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class MatchRule(Base):
    """侦探规则表：关键词或正则命中后自动归类。"""

    __tablename__ = "match_rules"
    __table_args__ = (
        UniqueConstraint(
            "keyword",
            "pattern_type",
            "direction",
            name="uq_match_rules_keyword_ptype_direction",
        ),
    )


    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False, default="any")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    pattern_type: Mapped[str] = mapped_column(String, nullable=False, default="keyword")
    is_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class MerchantAlias(Base):
    """商户别名表：用户一次手工纠正后记住的映射（归一化别名 → 分类），下次同类自动命中。"""

    __tablename__ = "merchant_aliases"
    __table_args__ = (UniqueConstraint("alias", "direction", name="uq_merchant_aliases_alias_direction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class ReportScheme(Base):
    """月报分类口径表：name 为口径名（主键），scheme_json 存 {桶名: [分类名, ...]}。"""

    __tablename__ = "report_schemes"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    scheme_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class OcrReview(Base):
    """OCR 审核队列表：拍照识别结果待人工确认入账 / 驳回。"""

    __tablename__ = "ocr_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','confirmed','rejected')",
            name="ck_ocr_reviews_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False, default="image/png")
    filename: Mapped[str] = mapped_column(String, nullable=False, default="")
    merchant: Mapped[str] = mapped_column(String, nullable=False, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_on: Mapped[str] = mapped_column(String, nullable=False, default="")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String, nullable=False, default="")
    mock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    field_confidence: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    transaction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class StatementBatch(Base):
    """导入批次表：一次账单导入的汇总。"""

    __tablename__ = "statement_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("statement_templates.id"), nullable=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="preview")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    auto_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)


class StatementItem(Base):
    """导入明细表：账单中的单行记录。"""

    __tablename__ = "statement_items"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_statement_items_fingerprint"),
        CheckConstraint("amount_cents > 0", name="ck_statement_items_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("statement_batches.id"), nullable=False)
    occurred_on: Mapped[str] = mapped_column(String, nullable=False)
    counterparty: Mapped[str] = mapped_column(String, nullable=False, default="")
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    suggested_category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    match_source: Mapped[str] = mapped_column(String, nullable=False, default="none")
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_action: Mapped[str] = mapped_column(String, nullable=False, default="categorize")
    suggested_to_account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=True)
    suggested_rule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("match_rules.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="preview")
    claimed_category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    transaction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow)
