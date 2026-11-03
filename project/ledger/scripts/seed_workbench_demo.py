"""工作台演示数据播种脚本。

用于截图验收：重建 data/demo.db，写入账户、规则、批次、待处理条目、
交易与报表口径，最后打印统计信息。

用法：
    python scripts/seed_workbench_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# 保证可以以脚本方式直接运行
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "demo.db"

# 必须在导入 ledger 之前设置环境变量，确保建库指向 demo 库
os.environ["LEDGER_DB"] = str(DB_PATH)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from ledger.database import get_session_factory, init_db  # noqa: E402
from ledger.matching import fingerprint  # noqa: E402
from ledger.models import (  # noqa: E402
    Account,
    Category,
    MatchRule,
    ReportScheme,
    StatementBatch,
    StatementItem,
    Transaction,
    utcnow,
)
from ledger.seed import ensure_seed  # noqa: E402


def reset_database() -> None:
    """删除旧库并重新建库。"""
    if DB_PATH.exists():
        DB_PATH.unlink()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def seed_accounts(session: AsyncSession) -> dict[str, Account]:
    """写入两个账户：招商银行储蓄卡与招商银行信用卡。"""
    now = utcnow()
    debit = Account(
        name="招商银行储蓄卡",
        type="bank",
        currency="CNY",
        opening_balance_cents=0,
        is_archived=0,
        created_at=now,
        updated_at=now,
    )
    credit = Account(
        name="招商银行信用卡",
        type="credit",
        currency="CNY",
        opening_balance_cents=0,
        is_archived=0,
        created_at=now,
        updated_at=now,
    )
    session.add_all([debit, credit])
    await session.flush()
    return {"debit": debit, "credit": credit}


async def seed_rules(
    session: AsyncSession, categories: dict[str, int]
) -> dict[str, MatchRule]:
    """写入 6 条匹配规则，覆盖 keyword 与 regex 两类。"""
    rules = [
        MatchRule(
            keyword="美团",
            pattern_type="keyword",
            category_id=categories["餐饮"],
            direction="out",
            priority=10,
            is_enabled=1,
            hit_count=12,
        ),
        MatchRule(
            keyword="滴滴",
            pattern_type="keyword",
            category_id=categories["交通"],
            direction="out",
            priority=20,
            is_enabled=1,
            hit_count=8,
        ),
        MatchRule(
            keyword="^(星巴克|瑞幸咖啡)$",
            pattern_type="regex",
            category_id=categories["餐饮"],
            direction="out",
            priority=15,
            is_enabled=1,
            hit_count=6,
        ),
        MatchRule(
            keyword="盒马|拼多多",
            pattern_type="regex",
            category_id=categories["购物"],
            direction="out",
            priority=25,
            is_enabled=1,
            hit_count=4,
        ),
        MatchRule(
            keyword="12306",
            pattern_type="keyword",
            category_id=categories["交通"],
            direction="out",
            priority=30,
            is_enabled=1,
            hit_count=3,
        ),
        MatchRule(
            keyword="京东",
            pattern_type="keyword",
            category_id=categories["购物"],
            direction="out",
            priority=40,
            is_enabled=0,
            hit_count=0,
        ),
    ]
    session.add_all(rules)
    await session.flush()
    return {
        "meituan": rules[0],
        "didi": rules[1],
        "coffee": rules[2],
        "shopping": rules[3],
        "rail": rules[4],
        "jd": rules[5],
    }


async def seed_batch(session: AsyncSession, account_id: int) -> StatementBatch:
    """写入一个待处理批次。"""
    batch = StatementBatch(
        filename="cmb-statement-sample.csv",
        account_id=account_id,
        status="pending",
        total_count=10,
        auto_count=0,
        pending_count=10,
    )
    session.add(batch)
    await session.flush()
    return batch


def build_item(
    batch_id: int,
    occurred_on: str,
    counterparty: str,
    summary: str,
    amount_cents: int,
    direction: str,
    match_source: str = "none",
    confidence: int = 0,
    suggested_category_id: int | None = None,
    suggested_rule_id: int | None = None,
) -> StatementItem:
    """构造一条待处理条目，自动计算 fingerprint。"""
    return StatementItem(
        batch_id=batch_id,
        occurred_on=occurred_on,
        counterparty=counterparty,
        summary=summary,
        amount_cents=amount_cents,
        direction=direction,
        fingerprint=fingerprint(
            occurred_on, amount_cents, direction, counterparty, summary
        ),
        match_source=match_source,
        confidence=confidence,
        status="pending",
        suggested_category_id=suggested_category_id,
        suggested_rule_id=suggested_rule_id,
    )


async def seed_items(
    session: AsyncSession,
    batch: StatementBatch,
    categories: dict[str, int],
    rules: dict[str, MatchRule],
) -> None:
    """写入 10 条 pending 条目，前 4 条带建议。"""
    items = [
        # 前 4 条：带建议，来源与规则自洽
        build_item(
            batch.id, "2026-09-05", "美团外卖", "午餐订单", 3280, "out",
            match_source="rule_keyword", confidence=96,
            suggested_category_id=categories["餐饮"],
            suggested_rule_id=rules["meituan"].id,
        ),
        build_item(
            batch.id, "2026-09-06", "滴滴出行", "快车行程", 2150, "out",
            match_source="rule_keyword", confidence=94,
            suggested_category_id=categories["交通"],
            suggested_rule_id=rules["didi"].id,
        ),
        build_item(
            batch.id, "2026-09-07", "星巴克", "门店消费", 3500, "out",
            match_source="alias", confidence=90,
            suggested_category_id=categories["餐饮"],
            suggested_rule_id=None,
        ),
        build_item(
            batch.id, "2026-09-08", "盒马鲜生", "生鲜采购", 12680, "out",
            match_source="history", confidence=85,
            suggested_category_id=categories["购物"],
            suggested_rule_id=None,
        ),
        # 后 6 条：无建议
        build_item(
            batch.id, "2026-09-09", "中国铁路12306", "高铁票", 55300, "out"
        ),
        build_item(batch.id, "2026-09-10", "拼多多", "日用品", 8990, "out"),
        build_item(batch.id, "2026-09-11", "京东", "数码配件", 23990, "out"),
        build_item(batch.id, "2026-09-12", "瑞幸咖啡", "咖啡", 1800, "out"),
        build_item(batch.id, "2026-09-13", "海底捞", "聚餐", 45600, "out"),
        build_item(batch.id, "2026-09-14", "蔚来充电", "充电费", 12000, "out"),
    ]
    session.add_all(items)
    await session.flush()


async def add_tx(
    session: AsyncSession,
    account_id: int,
    tx_type: str,
    amount_cents: int,
    occurred_on: str,
    category_id: int | None,
    merchant: str,
    summary: str,
) -> None:
    """写入一笔交易，note 采用 "{商户} {摘要}" 格式。"""
    now = utcnow()
    session.add(
        Transaction(
            type=tx_type,
            account_id=account_id,
            amount_cents=amount_cents,
            occurred_on=occurred_on,
            category_id=category_id,
            note=f"{merchant} {summary}",
            created_at=now,
            updated_at=now,
        )
    )


async def seed_transactions(
    session: AsyncSession, account_id: int, categories: dict[str, int]
) -> None:
    """写入 2026-09 的 25 笔与 2026-08 的 8 笔交易。"""
    canteen = categories["餐饮"]
    transport = categories["交通"]
    shopping = categories["购物"]
    daily = categories["日用"]
    education = categories["教育"]
    salary = categories["工资"]

    # 2026-09：教育 1 笔
    await add_tx(session, account_id, "expense", 140000, "2026-09-02",
                 education, "新东方在线", "网课 考研投入")

    # 2026-09：餐饮 6 笔
    await add_tx(session, account_id, "expense", 2500, "2026-09-03",
                 canteen, "公司食堂", "午餐")
    await add_tx(session, account_id, "expense", 3280, "2026-09-05",
                 canteen, "美团外卖", "午餐订单")
    await add_tx(session, account_id, "expense", 3500, "2026-09-07",
                 canteen, "星巴克", "门店消费")
    await add_tx(session, account_id, "expense", 45600, "2026-09-13",
                 canteen, "海底捞", "聚餐")
    await add_tx(session, account_id, "expense", 1800, "2026-09-12",
                 canteen, "瑞幸咖啡", "咖啡")
    await add_tx(session, account_id, "expense", 4200, "2026-09-18",
                 canteen, "西贝莜面村", "晚餐")

    # 2026-09：交通 4 笔
    await add_tx(session, account_id, "expense", 2150, "2026-09-06",
                 transport, "滴滴出行", "快车行程")
    await add_tx(session, account_id, "expense", 55300, "2026-09-09",
                 transport, "中国铁路12306", "高铁票")
    await add_tx(session, account_id, "expense", 600, "2026-09-15",
                 transport, "地铁", "通勤")
    await add_tx(session, account_id, "expense", 600, "2026-09-16",
                 transport, "地铁", "通勤")

    # 2026-09：购物 3 笔
    await add_tx(session, account_id, "expense", 8990, "2026-09-10",
                 shopping, "拼多多", "日用品")
    await add_tx(session, account_id, "expense", 23990, "2026-09-11",
                 shopping, "京东", "数码配件")
    await add_tx(session, account_id, "expense", 12680, "2026-09-08",
                 shopping, "盒马鲜生", "生鲜采购")

    # 2026-09：日用 2 笔
    await add_tx(session, account_id, "expense", 3980, "2026-09-20",
                 daily, "沃尔玛", "家庭日用")
    await add_tx(session, account_id, "expense", 2560, "2026-09-22",
                 daily, "屈臣氏", "洗护用品")

    # 2026-09：工资 1 笔
    await add_tx(session, account_id, "income", 500000, "2026-09-10",
                 salary, "某科技有限公司", "九月工资")

    # 2026-09：其他日常消费补齐至 25 笔
    await add_tx(session, account_id, "expense", 8000, "2026-09-24",
                 canteen, "肯德基", "晚餐")
    await add_tx(session, account_id, "expense", 12000, "2026-09-25",
                 transport, "蔚来充电", "充电费")
    await add_tx(session, account_id, "expense", 6800, "2026-09-26",
                 shopping, "名创优品", "家居小件")
    await add_tx(session, account_id, "expense", 1580, "2026-09-27",
                 daily, "便利店", "日用品")
    await add_tx(session, account_id, "expense", 9900, "2026-09-28",
                 canteen, "海底捞", "夜宵")
    await add_tx(session, account_id, "expense", 3000, "2026-09-29",
                 transport, "滴滴出行", "机场往返")

    # 2026-08：餐饮 5 笔 + 交通 3 笔，供环比
    await add_tx(session, account_id, "expense", 2200, "2026-08-05",
                 canteen, "公司食堂", "午餐")
    await add_tx(session, account_id, "expense", 3100, "2026-08-08",
                 canteen, "美团外卖", "午餐订单")
    await add_tx(session, account_id, "expense", 3400, "2026-08-12",
                 canteen, "星巴克", "门店消费")
    await add_tx(session, account_id, "expense", 8800, "2026-08-18",
                 canteen, "西贝莜面村", "聚餐")
    await add_tx(session, account_id, "expense", 1900, "2026-08-24",
                 canteen, "瑞幸咖啡", "咖啡")
    await add_tx(session, account_id, "expense", 2600, "2026-08-06",
                 transport, "滴滴出行", "快车行程")
    await add_tx(session, account_id, "expense", 42000, "2026-08-15",
                 transport, "中国铁路12306", "高铁票")
    await add_tx(session, account_id, "expense", 600, "2026-08-20",
                 transport, "地铁", "通勤")


async def seed_report_scheme(session: AsyncSession) -> None:
    """写入报表口径。"""
    scheme = {
        "考研投入": ["教育"],
        "一次性大项": ["数码", "住房"],
        "饮食": ["餐饮"],
        "日用": ["日用"],
        "话费": ["其他"],
        "交通": ["交通"],
    }
    session.add(
        ReportScheme(
            name="9月口径",
            scheme_json=json.dumps(scheme, ensure_ascii=False),
            updated_at=utcnow(),
        )
    )
    await session.flush()


async def load_categories(session: AsyncSession) -> list[Category]:
    """读取已播种的默认分类。"""
    result = await session.execute(select(Category))
    return list(result.scalars().all())


async def main() -> None:
    """入口：重建库并播种全部演示数据。"""
    reset_database()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await ensure_seed(session)
        categories = {
            c.name: c.id for c in (await session.execute(select(Category))).scalars().all()
        }
        accounts = await seed_accounts(session)
        rules = await seed_rules(session, categories)
        batch = await seed_batch(session, accounts["debit"].id)
        await seed_items(session, batch, categories, rules)
        await seed_transactions(session, accounts["debit"].id, categories)
        await seed_report_scheme(session)
        await session.commit()

    print("demo 数据就绪：规则 6 条，批次 1 个（10 条待处理），交易 33 笔")


if __name__ == "__main__":
    asyncio.run(main())
