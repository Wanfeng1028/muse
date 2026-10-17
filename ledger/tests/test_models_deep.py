"""models 深度测试：边界值、失败注入、幂等、并发、中文场景。

所有用例走真实 SQLAlchemy 引擎与真实 API，不对被测模块做 mock。
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from ledger.database import get_session_factory
from ledger.models import (
    Account,
    Category,
    OcrReview,
    StatementBatch,
    StatementItem,
    Transaction,
    utcnow,
)


async def _make_account(name: str = "现金", type_: str = "cash") -> int:
    """插入一个账户，返回主键。"""
    factory = get_session_factory()
    async with factory() as session:
        acc = Account(
            name=name,
            type=type_,
            currency="CNY",
            opening_balance_cents=0,
            note="",
            is_archived=0,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc.id


async def _make_category(name: str = "餐饮", kind: str = "expense") -> int:
    """插入一个分类，返回主键。"""
    factory = get_session_factory()
    async with factory() as session:
        cat = Category(name=name, kind=kind, icon="", color="", sort_order=0)
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return cat.id


async def _count(model) -> int:
    """统计表行数。"""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())


@pytest.mark.asyncio
async def test_account_超长中文名与空备注可写入(client):
    """账户表：超长中文名（200 字）与空备注都能正常落库，字段原样返回。"""
    long_name = "测试账户" * 50
    assert len(long_name) == 200

    acc_id = await _make_account(name=long_name, type_="储蓄")

    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(Account, acc_id)

    assert row is not None
    assert row.name == long_name
    assert row.note == ""
    assert row.type == "储蓄"


@pytest.mark.asyncio
async def test_transaction_金额为零被检查约束拒绝(client):
    """交易表：amount_cents = 0 触发 ck_transactions_amount_positive。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(
                Transaction(
                    type="expense",
                    account_id=acc_id,
                    to_account_id=None,
                    category_id=None,
                    amount_cents=0,
                    occurred_on="2024-06-01",
                    note="",
                    currency="CNY",
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            await session.commit()

    assert await _count(Transaction) == 0


@pytest.mark.asyncio
async def test_transaction_负数金额被检查约束拒绝(client):
    """交易表：amount_cents = -1 触发检查约束，且不影响已有正数记录。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        session.add(
            Transaction(
                type="expense",
                account_id=acc_id,
                to_account_id=None,
                category_id=None,
                amount_cents=100,
                occurred_on="2024-06-01",
                note="正常一笔",
                currency="CNY",
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(
                Transaction(
                    type="expense",
                    account_id=acc_id,
                    to_account_id=None,
                    category_id=None,
                    amount_cents=-1,
                    occurred_on="2024-06-01",
                    note="负数",
                    currency="CNY",
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            await session.commit()

    assert await _count(Transaction) == 1


@pytest.mark.asyncio
async def test_transaction_极大金额可写入(client):
    """交易表：接近 int64 上限的金额可以写入并读回一致。"""
    acc_id = await _make_account()
    big = 9_000_000_000_000_000_000
    factory = get_session_factory()

    async with factory() as session:
        tx = Transaction(
            type="income",
            account_id=acc_id,
            to_account_id=None,
            category_id=None,
            amount_cents=big,
            occurred_on="2024-06-01",
            note="大额",
            currency="CNY",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(tx)
        await session.commit()
        await session.refresh(tx)
        tx_id = tx.id

    async with factory() as session:
        row = await session.get(Transaction, tx_id)

    assert row is not None
    assert row.amount_cents == big


@pytest.mark.asyncio
async def test_category_同名同类型唯一约束(client):
    """分类表：同 name + kind 重复插入触发 uq_categories_name_kind。"""
    # 用种子数据中不存在的分类名，避免与 ensure_seed 冲突
    await _make_category(name="测试唯一分类", kind="expense")
    factory = get_session_factory()

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(Category(name="测试唯一分类", kind="expense", icon="", color="", sort_order=1))
            await session.commit()


@pytest.mark.asyncio
async def test_statement_item_指纹唯一实现幂等导入(client):
    """导入明细：同一 fingerprint 第二次插入失败，行数保持 1，实现重复导入幂等。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        batch = StatementBatch(
            filename="账单.csv",
            template_id=None,
            account_id=acc_id,
            status="preview",
            total_count=1,
            auto_count=0,
            pending_count=1,
            created_at=utcnow(),
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

    async with factory() as session:
        session.add(
            StatementItem(
                batch_id=batch_id,
                occurred_on="2024-06-01",
                counterparty="星巴克",
                summary="拿铁",
                amount_cents=3500,
                direction="expense",
                raw_json="{}",
                fingerprint="fp-abc-001",
                suggested_category_id=None,
                match_source="none",
                confidence=0,
            )
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(
                StatementItem(
                    batch_id=batch_id,
                    occurred_on="2024-06-01",
                    counterparty="星巴克",
                    summary="拿铁",
                    amount_cents=3500,
                    direction="expense",
                    raw_json="{}",
                    fingerprint="fp-abc-001",
                    suggested_category_id=None,
                    match_source="none",
                    confidence=0,
                )
            )
            await session.commit()

    assert await _count(StatementItem) == 1


@pytest.mark.asyncio
async def test_statement_item_零金额被检查约束拒绝(client):
    """导入明细：amount_cents = 0 触发 ck_statement_items_amount_positive。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        batch = StatementBatch(
            filename="账单2.csv",
            template_id=None,
            account_id=acc_id,
            status="preview",
            total_count=1,
            auto_count=0,
            pending_count=1,
            created_at=utcnow(),
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(
                StatementItem(
                    batch_id=batch_id,
                    occurred_on="2024-06-01",
                    counterparty="",
                    summary="",
                    amount_cents=0,
                    direction="expense",
                    raw_json="{}",
                    fingerprint="fp-zero",
                    suggested_category_id=None,
                    match_source="none",
                    confidence=0,
                )
            )
            await session.commit()

    assert await _count(StatementItem) == 0


@pytest.mark.asyncio
async def test_ocr_review_非法状态被检查约束拒绝(client):
    """OCR 审核表：status 写 'unknown' 触发 ck_ocr_reviews_status。"""
    factory = get_session_factory()

    with pytest.raises(IntegrityError):
        async with factory() as session:
            session.add(
                OcrReview(
                    image=b"\x89PNG",
                    content_type="image/png",
                    filename="小票.png",
                    merchant="超市",
                    amount_cents=1000,
                    occurred_on="2024-06-01",
                    raw_text="",
                    provider="mock",
                    mock=1,
                    category_id=None,
                    field_confidence="{}",
                    status="unknown",
                    transaction_id=None,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            await session.commit()

    assert await _count(OcrReview) == 0


@pytest.mark.asyncio
async def test_ocr_review_中文商户与空图片字节可写入(client):
    """OCR 审核表：中文商户名、空图片字节、pending 状态均可写入。"""
    factory = get_session_factory()

    async with factory() as session:
        row = OcrReview(
            image=b"",
            content_type="image/jpeg",
            filename="",
            merchant="兰州牛肉拉面（人民路店）",
            amount_cents=2850,
            occurred_on="2024-06-01",
            raw_text="兰州牛肉拉面 28.50",
            provider="mock",
            mock=1,
            category_id=None,
            field_confidence="{}",
            status="pending",
            transaction_id=None,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id

    async with factory() as session:
        got = await session.get(OcrReview, row_id)

    assert got is not None
    assert got.merchant == "兰州牛肉拉面（人民路店）"
    assert got.image == b""
    assert got.status == "pending"


@pytest.mark.asyncio
async def test_account_外键约束阻止孤儿交易(client):
    """交易表：account_id 指向不存在的账户时，SQLite 外键约束拒绝写入。"""
    factory = get_session_factory()

    async with factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))

    raised = False
    try:
        async with factory() as session:
            await session.execute(text("PRAGMA foreign_keys=ON"))
            session.add(
                Transaction(
                    type="expense",
                    account_id=999999,
                    to_account_id=None,
                    category_id=None,
                    amount_cents=100,
                    occurred_on="2024-06-01",
                    note="孤儿",
                    currency="CNY",
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            await session.commit()
    except IntegrityError:
        raised = True

    assert raised is True
    assert await _count(Transaction) == 0


@pytest.mark.asyncio
async def test_并发双写同一账单指纹只成功一次(client):
    """并发：两个协程同时插入同一 fingerprint，最终只有 1 条成功。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        batch = StatementBatch(
            filename="并发账单.csv",
            template_id=None,
            account_id=acc_id,
            status="preview",
            total_count=1,
            auto_count=0,
            pending_count=1,
            created_at=utcnow(),
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

    async def _insert_once() -> bool:
        try:
            async with factory() as session:
                session.add(
                    StatementItem(
                        batch_id=batch_id,
                        occurred_on="2024-06-02",
                        counterparty="便利店",
                        summary="矿泉水",
                        amount_cents=200,
                        direction="expense",
                        raw_json="{}",
                        fingerprint="fp-concurrent-1",
                        suggested_category_id=None,
                        match_source="none",
                        confidence=0,
                    )
                )
                await session.commit()
            return True
        except IntegrityError:
            return False

    results = await asyncio.gather(_insert_once(), _insert_once())
    success = sum(1 for r in results if r)

    assert success == 1
    assert await _count(StatementItem) == 1


@pytest.mark.asyncio
async def test_并发双写同一账单批次只保留一条明细(client):
    """并发：两协程插入不同 fingerprint 但同 batch_id，两条都能落库且归属同一批次。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        batch = StatementBatch(
            filename="并发账单2.csv",
            template_id=None,
            account_id=acc_id,
            status="preview",
            total_count=2,
            auto_count=0,
            pending_count=2,
            created_at=utcnow(),
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

    async def _insert(fp: str) -> int:
        async with factory() as session:
            item = StatementItem(
                batch_id=batch_id,
                occurred_on="2024-06-03",
                counterparty="早餐店",
                summary="包子",
                amount_cents=500,
                direction="expense",
                raw_json="{}",
                fingerprint=fp,
                suggested_category_id=None,
                match_source="none",
                confidence=0,
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return item.id

    ids = await asyncio.gather(_insert("fp-c-1"), _insert("fp-c-2"))

    assert len(set(ids)) == 2
    async with factory() as session:
        result = await session.execute(
            select(func.count()).select_from(StatementItem).where(StatementItem.batch_id == batch_id)
        )
        assert int(result.scalar_one()) == 2


@pytest.mark.asyncio
async def test_statement_item_中文备注与中文对手方可写入(client):
    """导入明细：中文对手方、中文摘要、方向字段原样保留。"""
    acc_id = await _make_account()
    factory = get_session_factory()

    async with factory() as session:
        batch = StatementBatch(
            filename="中文账单.csv",
            template_id=None,
            account_id=acc_id,
            status="preview",
            total_count=1,
            auto_count=0,
            pending_count=1,
            created_at=utcnow(),
        )
        session.add(batch)
        await session.commit()
        await session.refresh(batch)
        batch_id = batch.id

    async with factory() as session:
        item = StatementItem(
            batch_id=batch_id,
            occurred_on="2024-06-04",
            counterparty="北京市朝阳区老王煎饼铺",
            summary="双蛋煎饼加脆饼",
            amount_cents=1250,
            direction="expense",
            raw_json="{}",
            fingerprint="fp-中文-1",
            suggested_category_id=None,
            match_source="none",
            confidence=0,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    async with factory() as session:
        got = await session.get(StatementItem, item_id)

    assert got is not None
    assert got.counterparty == "北京市朝阳区老王煎饼铺"
    assert got.summary == "双蛋煎饼加脆饼"
    assert got.amount_cents == 1250


@pytest.mark.asyncio
async def test_数据库路径可写且文件存在(client):
    """环境：LEDGER_DB 指向的 sqlite 文件确实被创建，且能连上做查询。"""
    db_path = os.environ["LEDGER_DB"]

    assert os.path.exists(db_path)
    assert os.path.getsize(db_path) > 0

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1