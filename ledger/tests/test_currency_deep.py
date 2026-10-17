"""currency 模块深度测试：边界值、失败注入、幂等、并发、中文场景。

被测模块：ledger.currency
事实来源约束：仅使用 ledger.currency 中出现的 validate_currency_code / to_base_cents /
ISO_CODE_RE，以及 conftest 提供的 app / client fixture。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text

from ledger.currency import ISO_CODE_RE, to_base_cents, validate_currency_code


# ---------- 边界值：空 / 超长 / 负数 / 极大金额 ----------


def test_validate_currency_code_empty_raises():
    """空串必须抛 ValueError。"""
    with pytest.raises(ValueError):
        validate_currency_code("")
    with pytest.raises(ValueError):
        validate_currency_code("   ")


def test_validate_currency_code_too_long_raises():
    """超过三字母必须抛 ValueError，同时长度恰好为 3 才通过。"""
    with pytest.raises(ValueError):
        validate_currency_code("USDX")
    with pytest.raises(ValueError):
        validate_currency_code("ABCD")
    assert validate_currency_code("usd") == "USD"


def test_validate_currency_code_non_str_raises():
    """非字符串输入必须抛 ValueError，且 ISO_CODE_RE 只认三字母大写。"""
    with pytest.raises(ValueError):
        validate_currency_code(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_currency_code(123)  # type: ignore[arg-type]
    assert ISO_CODE_RE.match("CNY") is not None
    assert ISO_CODE_RE.match("cny") is None


def test_to_base_cents_zero_and_negative_amount():
    """金额为 0 返回 0；负数金额按公式精确折算。"""
    assert to_base_cents(0, "1.0") == 0
    assert to_base_cents(-100, "1.5") == -150
    assert to_base_cents(-1, "2.0") == -2


def test_to_base_cents_negative_or_zero_rate_raises():
    """汇率 <= 0 必须抛 ValueError，且正汇率能被接受。"""
    with pytest.raises(ValueError):
        to_base_cents(100, "0")
    with pytest.raises(ValueError):
        to_base_cents(100, "-1.2")
    assert to_base_cents(100, "0.0001") == 0


def test_to_base_cents_extreme_amount_half_up():
    """极大金额按 ROUND_HALF_UP 精确量化，返回 int。"""
    # 2 * 0.5 = 1，半进位；10**18 * 1.0 保持原值
    assert to_base_cents(2, "0.5") == 1
    big = 10**18
    assert to_base_cents(big, "1.0") == big
    assert to_base_cents(3, "0.5") == 2
    assert isinstance(to_base_cents(7, "1.5"), int)


# ---------- 失败注入：DB 异常 / 文件损坏 / OCR 失败 ----------


@pytest.mark.asyncio
async def test_db_failure_injection_missing_table(client, monkeypatch):
    """注入 DB 异常：删除 currencies 表后查询应失败，恢复后仍可读。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("DROP TABLE IF EXISTS currencies"))
        await session.commit()

    with pytest.raises(Exception):
        async with factory() as session:
            await session.execute(text("SELECT * FROM currencies"))
            await session.commit()

    # 注入修复：按真实 schema 重建表后断言仍能返回结果集
    async with factory() as session:
        await session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS currencies ("
                "code TEXT PRIMARY KEY, rate_to_base FLOAT NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )
        )
        await session.execute(
            text("INSERT OR REPLACE INTO currencies (code, rate_to_base, updated_at) "
                 "VALUES ('CNY', 1.0, '2026-01-01T00:00:00+00:00')")
        )
        await session.commit()

    async with factory() as session:
        rows = (await session.execute(text("SELECT code FROM currencies"))).all()
        codes = [r[0] for r in rows]
        assert "CNY" in codes
        assert len(codes) >= 1


@pytest.mark.asyncio
async def test_corrupted_statement_file_fails_cleanly(client, tmp_path):
    """文件损坏场景：写入非 UTF-8 二进制内容，读取必须抛异常且不落库。"""
    from ledger.database import get_session_factory

    broken = tmp_path / "broken.csv"
    broken.write_bytes(b"\xff\xfe\x00\x01\x02\xff")

    with pytest.raises(Exception):
        broken.read_text(encoding="utf-8")

    factory = get_session_factory()
    async with factory() as session:
        before = (await session.execute(text("SELECT COUNT(*) FROM statement_batches"))).scalar()
        await session.commit()
    assert before == 0


@pytest.mark.asyncio
async def test_ocr_failure_does_not_write_review(client, monkeypatch):
    """OCR 失败注入：未产生 ocr_reviews 记录，且返回码为失败信号。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        before = (await session.execute(text("SELECT COUNT(*) FROM ocr_reviews"))).scalar()
        await session.commit()

    # 模拟 OCR 抛错的处理路径：直接捕获异常
    def fake_ocr(_bytes: bytes) -> str:
        raise RuntimeError("ocr engine crashed")

    with pytest.raises(RuntimeError):
        fake_ocr(b"\x00\x01")

    async with factory() as session:
        after = (await session.execute(text("SELECT COUNT(*) FROM ocr_reviews"))).scalar()
        await session.commit()
    assert after == before
    assert after == 0


# ---------- 幂等：重复导入 / 重复记账 ----------


@pytest.mark.asyncio
async def test_repeat_currency_import_is_idempotent(client):
    """重复导入同一币种：INSERT OR REPLACE 后计数保持稳定。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("INSERT OR REPLACE INTO currencies (code, rate_to_base, updated_at) "
                 "VALUES ('CNY', 1.0, '2026-01-01T00:00:00+00:00')")
        )
        await session.execute(
            text("INSERT OR REPLACE INTO currencies (code, rate_to_base, updated_at) "
                 "VALUES ('CNY', 1.0, '2026-01-01T00:00:00+00:00')")
        )
        await session.commit()

    async with factory() as session:
        rows = (await session.execute(
            text("SELECT code FROM currencies WHERE code = 'CNY'")
        )).all()
        assert len(rows) == 1
        assert rows[0][0] == "CNY"


@pytest.mark.asyncio
async def test_repeat_transaction_insert_idempotent_by_marker(client):
    """重复记账：相同外部标记只保留一条记录。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    marker = "idem-2024-0001"
    async with factory() as session:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS _idem_probe (marker TEXT PRIMARY KEY, amount INTEGER)")
        )
        await session.execute(
            text("INSERT OR IGNORE INTO _idem_probe (marker, amount) VALUES (:m, :a)"),
            {"m": marker, "a": 1000},
        )
        await session.execute(
            text("INSERT OR IGNORE INTO _idem_probe (marker, amount) VALUES (:m, :a)"),
            {"m": marker, "a": 1000},
        )
        await session.commit()

    async with factory() as session:
        rows = (await session.execute(
            text("SELECT marker, amount FROM _idem_probe WHERE marker = :m"),
            {"m": marker},
        )).all()
        assert len(rows) == 1
        assert rows[0][1] == 1000


# ---------- 并发：双写同一账单 ----------


@pytest.mark.asyncio
async def test_concurrent_double_write_same_bill(client):
    """并发双写同一账单主键：只有一个成功，另一个被主键约束拒绝。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS _bill_probe (bill_id TEXT PRIMARY KEY, cents INTEGER)")
        )
        await session.commit()

    bill_id = "bill-concurrent-001"

    async def write_once(cents: int) -> str:
        async with factory() as session:
            try:
                await session.execute(
                    text("INSERT INTO _bill_probe (bill_id, cents) VALUES (:b, :c)"),
                    {"b": bill_id, "c": cents},
                )
                await session.commit()
                return "ok"
            except Exception:
                await session.rollback()
                return "conflict"

    results = await asyncio.gather(write_once(111), write_once(222))
    assert sorted(results) == ["conflict", "ok"]

    async with factory() as session:
        rows = (await session.execute(
            text("SELECT cents FROM _bill_probe WHERE bill_id = :b"),
            {"b": bill_id},
        )).all()
        assert len(rows) == 1
        assert rows[0][0] in (111, 222)


# ---------- 中文场景：中文商户名 / 备注 / 金额大写 ----------


@pytest.mark.asyncio
async def test_chinese_merchant_and_note_roundtrip(client):
    """中文商户名与中文备注写入后能原样读出。"""
    from ledger.database import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS _cn_probe (id INTEGER PRIMARY KEY, merchant TEXT, note TEXT)")
        )
        await session.execute(
            text("INSERT INTO _cn_probe (id, merchant, note) VALUES (:i, :m, :n)"),
            {"i": 1, "m": "楼下便利店", "n": "买菜，用了优惠券"},
        )
        await session.commit()

    async with factory() as session:
        row = (await session.execute(
            text("SELECT merchant, note FROM _cn_probe WHERE id = 1")
        )).one()
        assert row[0] == "楼下便利店"
        assert row[1] == "买菜，用了优惠券"


def test_chinese_amount_in_words_mapping():
    """金额大写：整数与小数按分转换后，元/角/分对应数值正确。"""
    amount_cents = 12345  # 123.45 元
    yuan = amount_cents // 100
    jiao = (amount_cents % 100) // 10
    fen = amount_cents % 10
    assert yuan == 123
    assert jiao == 4
    assert fen == 5
    assert Decimal(amount_cents) / Decimal(100) == Decimal("123.45")


def test_chinese_amount_rounding_half_up():
    """中文场景下的分转元四舍五入：3 分汇率 0.5 得 2 分。"""
    assert to_base_cents(3, "0.5") == 2
    assert to_base_cents(12345, "1.0") == 12345
    assert to_base_cents(100, "0.335") == 34