"""对账差异工作台接口测试。"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from ledger import matching
from ledger.models import (
    Account,
    Category,
    MatchRule,
    StatementBatch,
    StatementItem,
    Transaction,
    utcnow,
)


async def _seed_batch(session, account_id: int) -> StatementBatch:
    """插入一个批次与三条 pending 条目。"""
    batch = StatementBatch(
        filename="2024-01.csv",
        account_id=account_id,
        status="preview",
        total_count=3,
        auto_count=0,
        pending_count=3,
    )
    session.add(batch)
    await session.flush()

    rows = [
        ("星巴克咖啡", "拿铁", 3200, "out"),
        ("滴滴出行", "打车", 2500, "out"),
        ("工资发放", "月薪", 100000, "in"),
    ]
    for idx, (cp, summary, amount, direction) in enumerate(rows):
        occurred_on_str = f"2024-01-{idx + 1:02d}"
        item = StatementItem(
            batch_id=batch.id,
            occurred_on=occurred_on_str,
            counterparty=cp,
            summary=summary,
            amount_cents=amount,
            direction=direction,
            fingerprint=matching.fingerprint(
                occurred_on_str, amount, direction, cp, summary
            ),
            status="pending",
        )
        session.add(item)
    await session.commit()
    return batch


async def _make_account(session, name: str) -> Account:
    """插入一个账户。"""
    account = Account(
        name=name,
        type="cash",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(account)
    await session.commit()
    return account

async def _make_category(session, name: str, kind: str) -> Category:
    """取已有分类（种子数据里有），没有才插入。"""
    existing = (
        await session.execute(
            select(Category).where(Category.name == name, Category.kind == kind)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    category = Category(name=name, kind=kind)
    session.add(category)
    await session.commit()
    return category


@pytest_asyncio.fixture(scope="function")
async def session(app):
    """函数级：清空业务表并重播种，返回一个新的 AsyncSession。"""
    from sqlalchemy import text

    from ledger.database import get_session_factory
    from ledger.seed import ensure_seed

    factory = get_session_factory()
    async with factory() as s:
        for t in (
            "ocr_reviews",
            "statement_items",
            "statement_batches",
            "match_rules",
            "merchant_aliases",
            "statement_templates",
            "currencies",
            "transactions",
            "budgets",
            "recurring",
            "categories",
            "accounts",
        ):
            await s.execute(text(f"DELETE FROM {t}"))
        await s.commit()
        await ensure_seed(s)
        await s.commit()
        yield s


@pytest.fixture
async def seed(client, session):
    """准备账户、分类与批次数据。"""
    account = await _make_account(session, "主账户")
    batch = await _seed_batch(session, account.id)
    return {"account": account, "batch": batch}


async def test_list_batches(client, seed):
    """批次列表返回刚建的批次，pending_count 为 3。"""
    resp = await client.get("/api/workbench/batches")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["pending_count"] == 3
    assert data["items"][0]["account_name"] == "主账户"


async def test_list_items_and_search(client, seed):
    """条目列表分页与关键词搜索。"""
    batch_id = seed["batch"].id

    resp = await client.get(
        f"/api/workbench/batches/{batch_id}/items",
        params={"status": "pending"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["candidates"] == []

    resp2 = await client.get(
        f"/api/workbench/batches/{batch_id}/items",
        params={"status": "pending", "q": "星巴克"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1


async def test_resolve_confirm(client, session, seed):
    """confirm 动作生成交易并更新批次计数。"""
    batch_id = seed["batch"].id
    category = await _make_category(session, "餐饮", "expense")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()
    target = items[0]

    resp = await client.post(
        f"/api/workbench/items/{target.id}/resolve",
        json={"action": "confirm", "category_id": category.id, "save_rule": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "claimed"

    tx_count = (
        await session.execute(select(func.count(Transaction.id)))
    ).scalar_one()
    assert tx_count == 1

    await session.refresh(seed["batch"])
    assert seed["batch"].pending_count == 2


async def test_resolve_non_pending(client, session, seed):
    """对非 pending 条目再次处理报 400。"""
    batch_id = seed["batch"].id
    category = await _make_category(session, "餐饮", "expense")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()
    target = items[0]

    first = await client.post(
        f"/api/workbench/items/{target.id}/resolve",
        json={"action": "confirm", "category_id": category.id},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/workbench/items/{target.id}/resolve",
        json={"action": "confirm", "category_id": category.id},
    )
    assert second.status_code == 400


async def test_resolve_learn(client, session, seed):
    """learn 动作新建关键词规则并将条目置 claimed。"""
    batch_id = seed["batch"].id
    category = await _make_category(session, "餐饮", "expense")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()
    target = items[0]

    resp = await client.post(
        f"/api/workbench/items/{target.id}/resolve",
        json={"action": "learn", "category_id": category.id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "claimed"

    rules = (
        await session.execute(
            select(MatchRule).where(MatchRule.pattern_type == "keyword")
        )
    ).scalars().all()
    assert len(rules) == 1
    assert rules[0].keyword == "星巴克咖啡"


async def test_resolve_learn_duplicate(client, session, seed):
    """重复创建相同三元组规则报 409。"""
    batch_id = seed["batch"].id
    category = await _make_category(session, "餐饮", "expense")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()

    first = await client.post(
        f"/api/workbench/items/{items[0].id}/resolve",
        json={"action": "learn", "category_id": category.id},
    )
    assert first.status_code == 200

    session.add(
        StatementItem(
            batch_id=batch_id,
            occurred_on="2024-02-01",
            counterparty="星巴克咖啡",
            summary="再来一杯",
            amount_cents=3300,
            direction="out",
            fingerprint=matching.fingerprint("2024-02-01", 3300, "out", "星巴克咖啡", "再来一杯"),
            match_source="none",
            confidence=0,
            status="pending",
        )
    )
    await session.commit()

    new_item = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.counterparty == "星巴克咖啡")
            .order_by(StatementItem.id.desc())
        )
    ).scalars().first()

    second = await client.post(
        f"/api/workbench/items/{new_item.id}/resolve",
        json={"action": "learn", "category_id": category.id},
    )
    assert second.status_code == 409


async def test_resolve_transfer(client, session, seed):
    """transfer 动作生成 type 为 transfer 的交易。"""
    batch_id = seed["batch"].id
    other = await _make_account(session, "备用账户")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()
    target = items[1]

    resp = await client.post(
        f"/api/workbench/items/{target.id}/resolve",
        json={"action": "transfer", "to_account_id": other.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    tx = (
        await session.execute(
            select(Transaction).where(Transaction.id == body["transaction_id"])
        )
    ).scalars().first()
    assert tx is not None
    assert tx.type == "transfer"
    assert tx.category_id is None


async def test_resolve_batch_partial(client, session, seed):
    """批量 confirm 部分成功语义。"""
    batch_id = seed["batch"].id
    category = await _make_category(session, "餐饮", "expense")

    items = (
        await session.execute(
            select(StatementItem)
            .where(StatementItem.batch_id == batch_id)
            .order_by(StatementItem.id.asc())
        )
    ).scalars().all()

    first = await client.post(
        f"/api/workbench/items/{items[0].id}/resolve",
        json={"action": "confirm", "category_id": category.id},
    )
    assert first.status_code == 200

    payload = {
        "item_ids": [items[1].id, items[0].id],
        "action": "confirm",
        "category_id": category.id,
    }
    resp = await client.post(
        f"/api/workbench/batches/{batch_id}/resolve-batch",
        json=payload,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] == [items[1].id]
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == items[0].id

    await session.refresh(seed["batch"])
    assert seed["batch"].pending_count == 1


async def test_resolve_missing_item(client, seed):
    """处理不存在的条目报 404。"""
    resp = await client.post(
        "/api/workbench/items/999999/resolve",
        json={"action": "ignore"},
    )
    assert resp.status_code == 404
