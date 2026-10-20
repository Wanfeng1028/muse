import pytest
import pytest_asyncio
from sqlalchemy import text, select
from ledger.database import get_session_factory
from ledger.seed import ensure_seed
from ledger.models import Account, Category, Transaction, utcnow
from ledger.services import import_csv_rows, audit_ledger, _txn_fingerprint
from ledger.matching import (
    match_best,
    match_by_history,
    detect_transfer_pair,
    fingerprint,
    suggest_candidates,
)


@pytest_asyncio.fixture(scope="function")
async def session(app):
    factory = get_session_factory()
    async with factory() as s:
        for t in ("ocr_reviews","statement_items","statement_batches","match_rules","merchant_aliases","statement_templates","currencies","transactions","budgets","recurring","categories","accounts"):
            await s.execute(text(f"DELETE FROM {t}"))
        await s.commit()
        await ensure_seed(s)
        await s.commit()
        yield s

@pytest_asyncio.fixture(scope="function")
async def session(app):
    from sqlalchemy import text
    from ledger.database import get_session_factory
    from ledger.seed import ensure_seed
    factory = get_session_factory()
    async with factory() as s:
        for t in ("ocr_reviews","statement_items","statement_batches","match_rules","merchant_aliases","statement_templates","currencies","transactions","budgets","recurring","categories","accounts"):
            await s.execute(text(f"DELETE FROM {t}"))
        await s.commit()
        await ensure_seed(s)
        await s.commit()
        yield s

async def test_wlfl_t1_empty_audit(session):
    result = await audit_ledger(session)
    assert result["ok"] is True
    assert result["error_count"] == 0
    assert result["warning_count"] == 0
    assert result["identity"]["holds"] is True
    assert result["identity"]["diff_cents"] == 0
    totals = result["totals"]
    assert totals["accounts"] == 0
    assert totals["transactions"] == 0
    assert totals["opening_sum_cents"] == 0
    assert totals["income_sum_cents"] == 0
    assert totals["expense_sum_cents"] == 0
    assert totals["transfer_out_sum_cents"] == 0
    assert totals["transfer_in_sum_cents"] == 0

async def test_wlfl_t2_income_expense(session):
    # 创建账户
    acc = Account(name="主账户", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(acc)
    await session.commit()
    # 查询分类
    salary_cat = await session.scalar(select(Category).where(Category.name == "工资", Category.kind == "income"))
    food_cat = await session.scalar(select(Category).where(Category.name == "餐饮", Category.kind == "expense"))
    assert salary_cat is not None
    assert food_cat is not None
    # 插入交易
    now = utcnow()
    t1 = Transaction(type="income", account_id=acc.id, category_id=salary_cat.id, amount_cents=100000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    t2 = Transaction(type="expense", account_id=acc.id, category_id=food_cat.id, amount_cents=30000, occurred_on="2024-01-02", note="", created_at=now, updated_at=now)
    session.add_all([t1, t2])
    await session.commit()
    result = await audit_ledger(session)
    assert result["identity"]["holds"] is True
    assert result["totals"]["income_sum_cents"] == 100000
    assert result["totals"]["expense_sum_cents"] == 30000
    assert result["identity"]["expected_cents"] == 70000
    assert result["ok"] is True

async def test_wlfl_t3_multi_leg(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=100000, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    b = Account(name="B", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    c = Account(name="C", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add_all([a, b, c])
    await session.commit()
    now = utcnow()
    t1 = Transaction(type="transfer", account_id=a.id, to_account_id=b.id, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    t2 = Transaction(type="transfer", account_id=b.id, to_account_id=c.id, amount_cents=20000, occurred_on="2024-01-02", note="", created_at=now, updated_at=now)
    session.add_all([t1, t2])
    await session.commit()
    result = await audit_ledger(session)
    assert result["identity"]["holds"] is True
    assert result["totals"]["transfer_out_sum_cents"] == 70000
    assert result["totals"]["transfer_in_sum_cents"] == 70000
    # A 的余额 = 期初100000 - 转出50000 = 50000
    # balance_sum = 50000(A) + 30000(B) + 20000(C) = 100000
    assert result["identity"]["balance_sum_cents"] == 100000
    assert result["identity"]["expected_cents"] == 100000

async def test_wlfl_t4_dangling_to_account(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    now = utcnow()
    t = Transaction(type="transfer", account_id=a.id, to_account_id=9999, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "TRANSFER_TO_ACCOUNT_NOT_FOUND" in codes
    assert "IDENTITY_BROKEN" in codes
    assert result["identity"]["holds"] is False
    assert result["identity"]["diff_cents"] == -50000
    assert result["ok"] is False

async def test_wlfl_t5_transfer_self(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    now = utcnow()
    t = Transaction(type="transfer", account_id=a.id, to_account_id=a.id, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "TRANSFER_SELF" in codes

async def test_wlfl_t6_transfer_missing_to(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    now = utcnow()
    t = Transaction(type="transfer", account_id=a.id, to_account_id=None, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "TRANSFER_MISSING_TO" in codes

async def test_wlfl_t7_expense_missing_category(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    now = utcnow()
    t = Transaction(type="expense", account_id=a.id, category_id=None, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "TRANSACTION_MISSING_CATEGORY" in codes

async def test_wlfl_t8_income_wrong_category(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    food_cat = await session.scalar(select(Category).where(Category.name == "餐饮", Category.kind == "expense"))
    assert food_cat is not None
    now = utcnow()
    t = Transaction(type="income", account_id=a.id, category_id=food_cat.id, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "CATEGORY_KIND_MISMATCH" in codes

async def test_wlfl_t9_unknown_type(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    salary_cat = await session.scalar(select(Category).where(Category.name == "工资", Category.kind == "income"))
    assert salary_cat is not None
    now = utcnow()
    t = Transaction(type="dividend", account_id=a.id, category_id=salary_cat.id, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    codes = [i["code"] for i in result["issues"]]
    assert "UNKNOWN_TYPE" in codes

async def test_wlfl_t10_csv_amount_precision(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    # 12.34 -> 1234
    csv_text = "date,type,account,category,amount\n2024-01-01,支出,A,餐饮,12.34\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 1
    t = await session.scalar(select(Transaction))
    assert t.amount_cents == 1234
    # 清理
    await session.execute(text("DELETE FROM transactions"))
    await session.commit()
    # 0.01 -> 1
    csv_text = "date,type,account,category,amount\n2024-01-01,支出,A,餐饮,0.01\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 1
    t = await session.scalar(select(Transaction))
    assert t.amount_cents == 1
    await session.execute(text("DELETE FROM transactions"))
    await session.commit()
    # 0 -> error
    csv_text = "date,type,account,category,amount\n2024-01-01,支出,A,餐饮,0\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert len(result["errors"]) > 0
    # -5 -> error
    csv_text = "date,type,account,category,amount\n2024-01-01,支出,A,餐饮,-5\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert len(result["errors"]) > 0
    # abc -> error
    csv_text = "date,type,account,category,amount\n2024-01-01,支出,A,餐饮,abc\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert len(result["errors"]) > 0
    # 缺 amount 列
    csv_text = "date,type,account,category\n2024-01-01,支出,A,餐饮\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert any("表头缺少必需列" in e for e in result["errors"])

async def test_wlfl_t11_csv_duplicate_rows(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add(a)
    await session.commit()
    # 相同行
    csv_text = "date,type,account,category,amount,note\n2024-01-01,支出,A,餐饮,10.00,note1\n2024-01-01,支出,A,餐饮,10.00,note1\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 1
    assert result["skipped"] == 1
    # 不同 note
    await session.execute(text("DELETE FROM transactions"))
    await session.commit()
    csv_text = "date,type,account,category,amount,note\n2024-01-01,支出,A,餐饮,10.00,note1\n2024-01-01,支出,A,餐饮,10.00,note2\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 2
    assert result["skipped"] == 0

async def test_wlfl_t12_csv_transfer(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    b = Account(name="B", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add_all([a, b])
    await session.commit()
    # 成功
    csv_text = "date,type,account,category,amount\n2024-01-01,转账,A,B,50.00\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 1
    t = await session.scalar(select(Transaction))
    assert t.type == "transfer"
    assert t.account_id == a.id
    assert t.to_account_id == b.id
    await session.execute(text("DELETE FROM transactions"))
    await session.commit()
    # 目标账户不存在
    csv_text = "date,type,account,category,amount\n2024-01-01,转账,A,不存在,50.00\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert len(result["errors"]) > 0
    # 转出转入同名
    csv_text = "date,type,account,category,amount\n2024-01-01,转账,A,A,50.00\n"
    result = await import_csv_rows(session, csv_text)
    assert result["created"] == 0
    assert len(result["errors"]) > 0

async def test_wlfl_t13_match_best(session):
    # alias 压过规则
    aliases = [{"alias": "星巴克", "category_id": 1, "direction": "out"}]
    rules = [
        {"id": 10, "keyword": "星巴克", "category_id": 2, "priority": 5, "pattern_type": "keyword", "is_enabled": 1, "direction": "any"},
    ]
    result = match_best("星巴克", "", "out", rules=rules, aliases=aliases, history=[], top_categories=[])
    assert result["source"] == "alias"
    assert result["confidence"] == 85
    assert result["category_id"] == 1
    # 同 priority 正则胜关键词
    rules = [
        {"id": 1, "keyword": "咖啡", "category_id": 2, "priority": 5, "pattern_type": "keyword", "is_enabled": 1, "direction": "any"},
        {"id": 2, "keyword": "咖.*啡", "category_id": 3, "priority": 5, "pattern_type": "regex", "is_enabled": 1, "direction": "any"},
    ]
    result = match_best("咖啡", "", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "rule_regex"
    assert result["confidence"] == 97
    assert result["category_id"] == 3
    # direction 不符被跳过
    rules = [
        {"id": 1, "keyword": "咖啡", "category_id": 2, "priority": 5, "pattern_type": "keyword", "is_enabled": 1, "direction": "in"},
    ]
    result = match_best("咖啡", "", "out", rules=rules, aliases=[], history=[], top_categories=[])
    assert result["source"] == "none"
    assert result["category_id"] is None
    assert result["confidence"] == 0
    assert result["reason"] == "无匹配"

async def test_wlfl_t14_match_by_history(session):
    # 精确2票 -> 70
    history = [
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
    ]
    result = match_by_history("星巴克", "", "out", history)
    assert result == (1, 70)
    # 仅1票精确 -> None
    history = [
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
    ]
    result = match_by_history("星巴克", "", "out", history)
    assert result is None
    # 模糊2票 -> 65
    history = [
        {"counterparty": "星巴克咖啡", "category_id": 1, "direction": "out"},
        {"counterparty": "星巴克", "category_id": 1, "direction": "out"},
    ]
    result = match_by_history("星巴克", "", "out", history)
    assert result == (1, 65)

async def test_wlfl_t15_detect_transfer_pair(session):
    account_names = {1: "招行", 2: "支付宝"}
    # 一出一入金对上且一方对上账户名
    items = [
        {"id": 1, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "out", "counterparty": "招行"},
        {"id": 2, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "in", "counterparty": "某人"},
    ]
    pairs = detect_transfer_pair(items, account_names)
    assert pairs == [(1, 2)]
    # 金额差超容差（默认100分）不配对
    items = [
        {"id": 1, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "out", "counterparty": "招行"},
        {"id": 2, "occurred_on": "2024-01-01", "amount_cents": 50101, "direction": "in", "counterparty": "某人"},
    ]
    pairs = detect_transfer_pair(items, account_names)
    assert pairs == []
    # 双方都对不上账户名 -> 不配对
    items = [
        {"id": 1, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "out", "counterparty": "未知"},
        {"id": 2, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "in", "counterparty": "未知"},
    ]
    pairs = detect_transfer_pair(items, account_names)
    assert pairs == []
    # 贪心独占（一个 out 只配一个 in）
    items = [
        {"id": 1, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "out", "counterparty": "招行"},
        {"id": 2, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "in", "counterparty": "某人"},
        {"id": 3, "occurred_on": "2024-01-01", "amount_cents": 50000, "direction": "in", "counterparty": "某人"},
    ]
    pairs = detect_transfer_pair(items, account_names)
    assert pairs == [(1, 2)]

async def test_wlfl_t16_fingerprint(session):
    fp1 = fingerprint("2024-01-01", 50000, "out", "星巴克", "咖啡")
    assert len(fp1) == 32
    fp2 = fingerprint("2024-01-01", 50000, "out", "星巴克", "咖啡")
    assert fp1 == fp2
    fp3 = fingerprint("2024-01-01", 50000, "out", "星巴克", "奶茶")
    assert fp1 != fp3

async def test_wlfl_t17_suggest_candidates(session):
    # 空历史+空常用 -> []
    result = suggest_candidates("星巴克", "", "out", [], [])
    assert result == []
    # 常用分类补齐最多3条且 confidence 为 55/45/35
    top_categories = [(1, 10), (2, 8), (3, 6), (4, 4)]
    result = suggest_candidates("星巴克", "", "out", [], top_categories)
    assert len(result) == 3
    assert result[0][2] == 55
    assert result[1][2] == 45
    assert result[2][2] == 35
    assert result[0][0] == 1
    assert result[1][0] == 2
    assert result[2][0] == 3

async def test_wlfl_t18_cross_currency(session):
    a = Account(name="A", type="checking", currency="CNY", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    b = Account(name="B", type="checking", currency="USD", opening_balance_cents=0, is_archived=0, created_at=utcnow(), updated_at=utcnow())
    session.add_all([a, b])
    await session.commit()
    now = utcnow()
    t = Transaction(type="transfer", account_id=a.id, to_account_id=b.id, amount_cents=50000, occurred_on="2024-01-01", note="", created_at=now, updated_at=now)
    session.add(t)
    await session.commit()
    result = await audit_ledger(session)
    issues = result["issues"]
    cross = [i for i in issues if i["code"] == "TRANSFER_CROSS_CURRENCY"]
    assert len(cross) == 1
    assert cross[0]["severity"] == "warning"
    assert result["ok"] is True
    assert result["error_count"] == 0
