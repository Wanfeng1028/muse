"""失败注入测试：DB 锁定 / 坏 CSV / 磁盘满 / 指标 DB 故障。"""

from __future__ import annotations

import os

import pytest

from ledger.backup import BackupError, backup_db
from ledger.migrations import run_migrations


async def test_db_locked_returns_500_with_request_id(client, monkeypatch):
    # transactions 路由直接用 get_session_factory()（见 routers/transactions.py），
    # 不走 get_session 依赖；此处 patch 路由模块内的名字。
    import sqlite3
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.get.side_effect = sqlite3.OperationalError("database is locked")
    mock.execute.side_effect = sqlite3.OperationalError("database is locked")

    class _CM:
        async def __aenter__(self):
            return mock

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        "ledger.routers.transactions.get_session_factory",
        lambda: (lambda: _CM()),
    )

    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": 1,
            "category_id": 1,
            "type": "expense",
            "amount_cents": 100,
            "occurred_on": "2024-01-01",
            "note": "x",
        },
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "服务器内部错误"
    assert body["request_id"] == resp.headers["X-Request-Id"]
    assert len(body["request_id"]) == 12


async def test_bad_csv_does_not_crash_service(client):
    resp = await client.post(
        "/api/import/csv",
        files={"file": ("bad.csv", os.urandom(2048), "text/csv")},
    )
    assert resp.status_code == 200

    health = await client.get("/api/health")
    assert health.status_code == 200


async def test_backup_disk_full_raises_and_leaves_no_partial(tmp_path, monkeypatch):
    db_path = tmp_path / "ledger.db"
    bdir = tmp_path / "backups"
    bdir.mkdir()

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    await run_migrations(engine)
    await engine.dispose()

    def _boom(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("ledger.backup.shutil.copy2", _boom)

    with pytest.raises(BackupError):
        backup_db(str(db_path), str(bdir))

    assert list(bdir.glob("ledger-*.db")) == []


async def test_metrics_does_not_hang_on_db_failure(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("ledger.routers.metrics.get_session_factory", _boom)

    resp = await client.get("/api/metrics")
    assert resp.status_code == 500
    body = resp.json()
    assert "request_id" in body
    assert resp.headers["X-Request-Id"] == body["request_id"]
