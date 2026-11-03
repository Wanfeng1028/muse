"""默认分类种子数据。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ledger.config import get_settings
from ledger.models import Category, Currency, utcnow

# (name, kind, icon, color, sort_order)
DEFAULT_CATEGORIES: list[tuple[str, str, str, str, int]] = [
    # 支出类
    ("餐饮", "expense", "🍜", "#ef4444", 10),
    ("交通", "expense", "🚇", "#3b82f6", 20),
    ("购物", "expense", "🛍", "#a855f7", 30),
    ("住房", "expense", "🏠", "#f59e0b", 40),
    ("日用", "expense", "🧴", "#10b981", 50),
    ("医疗", "expense", "💊", "#ef4444", 60),
    ("教育", "expense", "📚", "#6366f1", 70),
    ("娱乐", "expense", "🎮", "#ec4899", 80),
    ("社交", "expense", "🍻", "#f97316", 90),
    ("数码", "expense", "💻", "#0ea5e9", 100),
    ("旅行", "expense", "✈", "#14b8a6", 110),
    ("其他", "expense", "📦", "#6b7280", 120),
    # 收入类
    ("工资", "income", "💼", "#10b981", 10),
    ("奖金", "income", "🏆", "#f59e0b", 20),
    ("兼职", "income", "💻", "#3b82f6", 30),
    ("理财", "income", "📈", "#8b5cf6", 40),
    ("红包", "income", "🧧", "#ef4444", 50),
    ("其他", "income", "💰", "#6b7280", 60),
]


async def _ensure_base_currency(s: AsyncSession) -> None:
    """保证本位币的汇率行存在（rate_to_base=1.0），缺失则插入。"""
    base = get_settings().base_currency
    exists = await s.scalar(select(func.count()).select_from(Currency).where(Currency.code == base))
    if not exists:
        s.add(Currency(code=base, rate_to_base=1.0, updated_at=utcnow()))
        await s.commit()


async def ensure_seed(s: AsyncSession) -> None:
    """当 categories 表为空时，批量写入默认分类；同时保证本位币汇率行存在。"""
    await _ensure_base_currency(s)
    count = await s.scalar(select(func.count()).select_from(Category))
    if count and count > 0:
        return
    for name, kind, icon, color, sort_order in DEFAULT_CATEGORIES:
        s.add(
            Category(
                name=name,
                kind=kind,
                icon=icon,
                color=color,
                sort_order=sort_order,
            )
        )
    await s.commit()
