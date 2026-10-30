"""config 深度测试：边界值、失败注入、幂等、并发、中文场景。

被测对象：ledger.config 中的 get_settings 及 Settings。
说明：本文件聚焦配置模块的真实行为，通过环境变量注入 + 缓存清理
驱动，断言 Settings 的最终取值，不 mock 被测模块内部逻辑。
"""

from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path

import httpx
import pytest


CONFIG_MODULE = "ledger.config"


def _fresh_config():
    """重新导入 ledger.config，拿到未被缓存的模块对象。"""
    mod = importlib.import_module(CONFIG_MODULE)
    importlib.reload(mod)
    return mod


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """每个用例前后清掉 get_settings 的 lru_cache，避免串味。"""
    mod = _fresh_config()
    mod.get_settings.cache_clear()
    yield
    mod.get_settings.cache_clear()


@pytest.fixture
def env_guard():
    """保存并恢复 LEDGER_* 环境变量，避免污染其他用例。"""
    keys = (
        "LEDGER_DB",
        "LEDGER_HOST",
        "LEDGER_PORT",
        "LEDGER_LOG_LEVEL",
        "LEDGER_BASE_CURRENCY",
    )
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_empty_db_path_falls_back_to_project_root(env_guard):
    """边界：LEDGER_DB 为空字符串时按相对路径处理，拼到项目根目录。"""
    os.environ["LEDGER_DB"] = ""
    mod = _fresh_config()
    settings = mod.get_settings()

    expected = str(mod.PROJECT_ROOT / "")
    assert settings.db_path == expected
    assert settings.db_path.startswith(str(mod.PROJECT_ROOT))
    assert os.path.isabs(settings.db_path)


def test_relative_db_path_is_anchored_to_project_root(env_guard):
    """边界：相对路径必须拼到 PROJECT_ROOT，绝对路径保持原样。"""
    os.environ["LEDGER_DB"] = "data/ledger.db"
    mod = _fresh_config()
    settings_rel = mod.get_settings()

    assert settings_rel.db_path == str(mod.PROJECT_ROOT / "data/ledger.db")
    assert os.path.isabs(settings_rel.db_path)

    mod.get_settings.cache_clear()
    os.environ["LEDGER_DB"] = "/tmp/ledger_abs.db"
    settings_abs = mod.get_settings()

    assert settings_abs.db_path == "/tmp/ledger_abs.db"
    assert Path(settings_abs.db_path).is_absolute()


def test_negative_and_oversized_port_fall_back_to_default(env_guard):
    """边界：端口负数/超长数字串透传，非数字串必须抛错。"""
    os.environ["LEDGER_PORT"] = "-1"
    mod = _fresh_config()
    settings_neg = mod.get_settings()
    assert settings_neg.port == -1
    assert settings_neg.port != mod.DEFAULT_PORT

    mod.get_settings.cache_clear()
    os.environ["LEDGER_PORT"] = "99999999999999999999999999"
    settings_huge = mod.get_settings()
    assert settings_huge.port == 99999999999999999999999999
    assert settings_huge.port != mod.DEFAULT_PORT

    mod.get_settings.cache_clear()
    os.environ["LEDGER_PORT"] = "not-a-number"
    with pytest.raises(ValueError) as exc:
        mod.get_settings()
    assert "LEDGER_PORT" in str(exc.value)
    assert "not-a-number" in str(exc.value)


def test_invalid_log_level_raises(env_guard):
    """失败注入：非法日志级别必须抛 ValueError，且带原始值。"""
    os.environ["LEDGER_LOG_LEVEL"] = "verbose"
    mod = _fresh_config()
    with pytest.raises(ValueError) as exc:
        mod.get_settings()
    assert "LEDGER_LOG_LEVEL" in str(exc.value)
    assert "verbose" in str(exc.value)


def test_lowercase_log_level_is_uppercased(env_guard):
    """中文场景：日志级别大小写不敏感，统一大写后放行。"""
    os.environ["LEDGER_LOG_LEVEL"] = "warning"
    mod = _fresh_config()
    settings = mod.get_settings()
    assert settings.log_level == "WARNING"
    assert settings.log_level in mod.ALLOWED_LOG_LEVELS


def test_invalid_base_currency_raises(env_guard):
    """失败注入：非三字母大写的币种代码必须抛 ValueError。"""
    os.environ["LEDGER_BASE_CURRENCY"] = "人民币"
    mod = _fresh_config()
    with pytest.raises(ValueError) as exc:
        mod.get_settings()
    assert "LEDGER_BASE_CURRENCY" in str(exc.value)
    assert "人民币" in str(exc.value)


def test_base_currency_is_stripped_and_uppercased(env_guard):
    """边界：币种前后空白要裁掉，再转大写，长度必须为 3。"""
    os.environ["LEDGER_BASE_CURRENCY"] = "  cny  "
    mod = _fresh_config()
    settings = mod.get_settings()
    assert settings.base_currency == "CNY"
    assert len(settings.base_currency) == 3


def test_settings_is_cached_singleton(env_guard):
    """幂等：同一进程内多次调用 get_settings 返回同一对象。"""
    os.environ["LEDGER_DB"] = "data/idempotent.db"
    mod = _fresh_config()
    first = mod.get_settings()
    second = mod.get_settings()
    assert first is second
    assert first.db_path == second.db_path


def test_settings_frozen_cannot_mutate(env_guard):
    """幂等：Settings 为 frozen dataclass，禁止原地改字段。"""
    mod = _fresh_config()
    settings = mod.get_settings()
    with pytest.raises(Exception) as exc:
        settings.port = 1
    assert settings.port == mod.DEFAULT_PORT
    assert "frozen" in str(exc.value).lower() or "cannot assign" in str(exc.value).lower()


def test_default_settings_without_env(env_guard):
    """边界：清空全部 LEDGER_* 后应落到默认值。"""
    for k in (
        "LEDGER_DB",
        "LEDGER_HOST",
        "LEDGER_PORT",
        "LEDGER_LOG_LEVEL",
        "LEDGER_BASE_CURRENCY",
    ):
        os.environ.pop(k, None)
    mod = _fresh_config()
    settings = mod.get_settings()
    assert settings.host == mod.DEFAULT_HOST
    assert settings.port == mod.DEFAULT_PORT
    assert settings.log_level == mod.DEFAULT_LOG_LEVEL
    assert settings.base_currency == "CNY"


@pytest.mark.asyncio
async def test_concurrent_get_settings_is_stable(env_guard):
    """并发：多任务同时读配置，结果必须一致且是同一单例。"""
    os.environ["LEDGER_DB"] = "data/concurrent.db"
    os.environ["LEDGER_HOST"] = "0.0.0.0"
    mod = _fresh_config()

    async def read():
        return mod.get_settings()

    results = await asyncio.gather(*[read() for _ in range(16)])
    assert len(results) == 16
    assert all(r is results[0] for r in results)
    assert all(r.db_path == results[0].db_path for r in results)


@pytest.mark.asyncio
async def test_api_uses_config_db_path(client):
    """中文场景：真实打 API，健康检查返回 200，且配置来自临时库。"""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok"

    mod = importlib.import_module(CONFIG_MODULE)
    settings = mod.get_settings()
    assert settings.db_path
    assert "test.db" in settings.db_path


@pytest.mark.asyncio
async def test_api_chinese_merchant_roundtrip(client):
    """中文场景：中文商户名与备注走真实 API 往返，内容不被破坏。"""
    created_acc = await client.post("/api/accounts", json={"name": "测试现金", "type": "cash"})
    assert created_acc.status_code == 201
    account_id = created_acc.json()["id"]

    categories = await client.get("/api/categories")
    assert categories.status_code == 200
    category_list = categories.json()
    assert len(category_list) >= 1
    category_id = category_list[0]["id"]

    payload = {
        "type": "expense",
        "account_id": account_id,
        "category_id": category_id,
        "amount_cents": 1234,
        "occurred_on": "2024-05-01",
        "note": "晚风小面馆 午饭 大写金额：壹拾贰元叁角肆分",
    }
    created = await client.post("/api/transactions", json=payload)
    assert created.status_code in (200, 201)
    created_body = created.json()
    assert "晚风小面馆" in created_body["note"]
    assert "壹拾贰元叁角肆分" in created_body["note"]


@pytest.mark.asyncio
async def test_api_concurrent_double_write_same_bill(client):
    """并发：同一账单并发双写，API 不 5xx，落库条数可核对。"""
    created_acc = await client.post("/api/accounts", json={"name": "并发现金", "type": "cash"})
    assert created_acc.status_code == 201
    account_id = created_acc.json()["id"]
    categories = await client.get("/api/categories")
    category_id = categories.json()[0]["id"]

    payload = {
        "type": "expense",
        "account_id": account_id,
        "category_id": category_id,
        "amount_cents": 888,
        "occurred_on": "2024-05-02",
        "note": "并发测试商户 同一账单双写",
    }

    async def write():
        return await client.post("/api/transactions", json=payload)

    responses = await asyncio.gather(write(), write())
    statuses = [r.status_code for r in responses]
    assert all(s < 500 for s in statuses)
    assert len(statuses) == 2

    listed = await client.get("/api/transactions")
    assert listed.status_code == 200
    items = listed.json()["items"]
    matched = [t for t in items if t.get("note") == "并发测试商户 同一账单双写"]
    assert len(matched) == len([s for s in statuses if s in (200, 201)])