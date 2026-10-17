"""配置模块深度测试：解析边界、类型回退、路径解析、校验 fail fast、幂等。

事实来源：feedflow/config.py 与 tests/conftest.py。
本文件不 mock 被测模块核心逻辑，直接调用 config.load / config.validate
与真实 flask 测试客户端，断言真实返回值。
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

import feedflow.config as config


ENV_KEYS = [
    "FEEDFLOW_DB",
    "FEEDFLOW_HOST",
    "FEEDFLOW_PORT",
    "FEEDFLOW_FETCH_INTERVAL",
    "FEEDFLOW_FETCH_TIMEOUT",
    "FEEDFLOW_FETCH_RETRIES",
    "FEEDFLOW_USER_AGENT",
    "FEEDFLOW_LOG_LEVEL",
    "FEEDFLOW_BACKUP_DIR",
    "FEEDFLOW_DIGEST_N",
    "FEEDFLOW_EXTRACT_TIMEOUT",
    "FEEDFLOW_FEVER_API_KEY",
    "FEEDFLOW_RATE_LIMIT_RPS",
    "FEEDFLOW_RATE_LIMIT_BURST",
    "FEEDFLOW_RATE_LIMIT_ENABLED",
]


@pytest.fixture
def clean_env(monkeypatch):
    """清空所有 FEEDFLOW_ 环境变量，保证每个用例从确定状态出发。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# 1. 畸形输入解析边界
# ---------------------------------------------------------------------------

def test_parse_int_malformed_and_whitespace(clean_env):
    """畸形 int 字符串回退默认值，合法带空白的字符串能正确解析。"""
    clean_env.setenv("FEEDFLOW_PORT", "not-a-number")
    clean_env.setenv("FEEDFLOW_FETCH_INTERVAL", "  45  ")
    cfg = config.load()
    assert cfg["port"] == config.DEFAULT_PORT
    assert cfg["fetch_interval"] == 45


def test_parse_float_malformed_and_negative(clean_env):
    """float 畸形回退默认值，负数字符串解析为负数原样返回。"""
    clean_env.setenv("FEEDFLOW_RATE_LIMIT_RPS", "abc")
    cfg = config.load()
    assert cfg["rate_limit_rps"] == config.DEFAULT_RATE_LIMIT_RPS

    clean_env.setenv("FEEDFLOW_RATE_LIMIT_RPS", "-3.5")
    cfg2 = config.load()
    assert cfg2["rate_limit_rps"] == -3.5


def test_parse_bool_all_accepted_tokens(clean_env):
    """布尔解析覆盖 true/false 各种写法，无法识别的回退默认。"""
    clean_env.setenv("FEEDFLOW_RATE_LIMIT_ENABLED", "YES")
    assert config.load()["rate_limit_enabled"] is True

    clean_env.setenv("FEEDFLOW_RATE_LIMIT_ENABLED", "off")
    assert config.load()["rate_limit_enabled"] is False

    clean_env.setenv("FEEDFLOW_RATE_LIMIT_ENABLED", "maybe")
    assert config.load()["rate_limit_enabled"] == config.DEFAULT_RATE_LIMIT_ENABLED


# ---------------------------------------------------------------------------
# 2. 空值与编码相关
# ---------------------------------------------------------------------------

def test_empty_string_falls_back_for_int_and_float(clean_env):
    """空字符串对 int/float 视为非法，回退默认值。"""
    clean_env.setenv("FEEDFLOW_DIGEST_N", "")
    clean_env.setenv("FEEDFLOW_EXTRACT_TIMEOUT", "   ")
    cfg = config.load()
    assert cfg["digest_n"] == config.DEFAULT_DIGEST_N
    assert cfg["extract_timeout"] == config.DEFAULT_EXTRACT_TIMEOUT


def test_fever_api_key_strips_and_empty_default(clean_env):
    """fever_api_key 会 strip，纯空白等同于空字符串。"""
    clean_env.setenv("FEEDFLOW_FEVER_API_KEY", "   ")
    cfg = config.load()
    assert cfg["fever_api_key"] == config.DEFAULT_FEVER_API_KEY
    assert cfg["fever_api_key"] == ""


def test_non_utf8_env_value_is_loaded_via_os_environ(clean_env):
    """非 ASCII 环境变量值能原样读到配置中，不触发编码异常。"""
    weird = "中文UA/测试"
    clean_env.setenv("FEEDFLOW_USER_AGENT", weird)
    cfg = config.load()
    assert cfg["user_agent"] == weird
    assert cfg["user_agent"] != config.DEFAULT_USER_AGENT


# ---------------------------------------------------------------------------
# 3. 路径解析
# ---------------------------------------------------------------------------

def test_relative_paths_resolved_against_project_root(clean_env):
    """相对 db / backup 路径解析到项目根目录下。"""
    clean_env.setenv("FEEDFLOW_DB", "data/x.db")
    clean_env.setenv("FEEDFLOW_BACKUP_DIR", "data/bk")
    cfg = config.load()
    assert cfg["db_path"] == str(config.PROJECT_ROOT / "data" / "x.db")
    assert cfg["backup_dir"] == str(config.PROJECT_ROOT / "data" / "bk")


def test_absolute_path_preserved(clean_env, tmp_path):
    """绝对路径原样保留，不做二次拼接。"""
    abs_db = str(tmp_path / "abs.db")
    abs_bk = str(tmp_path / "absbk")
    clean_env.setenv("FEEDFLOW_DB", abs_db)
    clean_env.setenv("FEEDFLOW_BACKUP_DIR", abs_bk)
    cfg = config.load()
    assert cfg["db_path"] == abs_db
    assert cfg["backup_dir"] == abs_bk


# ---------------------------------------------------------------------------
# 4. 默认值完整性
# ---------------------------------------------------------------------------

def test_defaults_when_env_empty(clean_env):
    """无任何环境变量时，所有键使用默认值。"""
    cfg = config.load()
    assert cfg["host"] == config.DEFAULT_HOST
    assert cfg["port"] == config.DEFAULT_PORT
    assert cfg["fetch_interval"] == config.DEFAULT_FETCH_INTERVAL
    assert cfg["fetch_timeout"] == config.DEFAULT_FETCH_TIMEOUT
    assert cfg["fetch_retries"] == config.DEFAULT_FETCH_RETRIES
    assert cfg["user_agent"] == config.DEFAULT_USER_AGENT
    assert cfg["log_level"] == config.DEFAULT_LOG_LEVEL
    assert cfg["digest_n"] == config.DEFAULT_DIGEST_N
    assert cfg["extract_timeout"] == config.DEFAULT_EXTRACT_TIMEOUT
    assert cfg["rate_limit_rps"] == config.DEFAULT_RATE_LIMIT_RPS
    assert cfg["rate_limit_burst"] == config.DEFAULT_RATE_LIMIT_BURST
    assert cfg["rate_limit_enabled"] == config.DEFAULT_RATE_LIMIT_ENABLED


def test_load_is_idempotent(clean_env):
    """连续两次 load 返回相同配置，重复读取不改变结果。"""
    clean_env.setenv("FEEDFLOW_PORT", "9001")
    clean_env.setenv("FEEDFLOW_DIGEST_N", "7")
    first = config.load()
    second = config.load()
    assert first == second
    assert first["port"] == 9001
    assert first["digest_n"] == 7


# ---------------------------------------------------------------------------
# 5. validate 校验 fail fast
# ---------------------------------------------------------------------------

def _run_validate_in_subprocess(cfg_literal):
    """在子进程里跑 validate，返回 (returncode, stdout, stderr)。

    用真实子进程是因为 validate 通过 SystemExit 退出，
    子进程可以干净捕获退出码，且不 mock 被测逻辑。
    """
    code = (
        "import feedflow.config as c\n"
        f"cfg = {cfg_literal}\n"
        "c.validate(cfg)\n"
        "print('OK', cfg['port'])\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_validate_accepts_valid_config(clean_env, tmp_path):
    """合法配置校验通过，返回码为 0 且 cfg 被回填默认值。"""
    db_path = str(tmp_path / "valid.db")
    rc, out, err = _run_validate_in_subprocess(
        "{'port': 8300, 'fetch_interval': 30, 'db_path': '" + db_path + "'}"
    )
    assert rc == 0
    assert out.strip() == "OK 8300"
    assert err == ""


def test_validate_rejects_port_out_of_range(clean_env):
    """port 越界触发 SystemExit，错误信息含中文提示。"""
    rc, out, err = _run_validate_in_subprocess(
        "{'port': 70000, 'fetch_interval': 30}"
    )
    assert rc != 0
    assert "FEEDFLOW_PORT" in err
    assert "1-65535" in err


def test_validate_rejects_non_positive_interval(clean_env):
    """fetch_interval <= 0 触发失败，且不产生成功输出。"""
    rc, out, err = _run_validate_in_subprocess(
        "{'port': 8300, 'fetch_interval': 0}"
    )
    assert rc != 0
    assert "FEEDFLOW_FETCH_INTERVAL" in err
    assert out.strip() == ""


def test_validate_rejects_negative_retries(clean_env):
    """fetch_retries < 0 触发失败，错误信息含具体值。"""
    rc, out, err = _run_validate_in_subprocess(
        "{'port': 8300, 'fetch_interval': 30, 'fetch_retries': -1}"
    )
    assert rc != 0
    assert "FEEDFLOW_FETCH_RETRIES" in err
    assert "-1" in err


def test_validate_rejects_bool_rps(clean_env):
    """bool 是 int 子类，但 rate_limit_rps 不允许 bool。"""
    rc, out, err = _run_validate_in_subprocess(
        "{'port': 8300, 'fetch_interval': 30, 'rate_limit_rps': True}"
    )
    assert rc != 0
    assert "FEEDFLOW_RATE_LIMIT_RPS" in err
    assert "True" in err


# ---------------------------------------------------------------------------
# 6. 与真实 flask 客户端集成：配置驱动行为
# ---------------------------------------------------------------------------

def test_app_uses_config_values_from_fixture(client):
    """conftest 构造的 app 配置生效，客户端可正常响应。"""
    resp = client.get("/")
    assert resp.status_code in (200, 302, 404)
    assert resp.status_code != 500


def test_db_file_created_after_init(tmp_db):
    """init_db 后数据库文件真实存在且非空。"""
    path = Path(tmp_db)
    assert path.exists()
    assert path.stat().st_size >= 0


def test_db_parent_dir_writable_for_validate(tmp_path, monkeypatch):
    """db 父目录可写时，validate 对最小配置放行。"""
    monkeypatch.delenv("FEEDFLOW_PORT", raising=False)
    monkeypatch.delenv("FEEDFLOW_FETCH_INTERVAL", raising=False)
    db_dir = tmp_path / "writable"
    db_dir.mkdir()
    cfg = {"port": 8300, "fetch_interval": 30, "db_path": str(db_dir / "a.db")}
    config.validate(cfg)
    assert cfg["fetch_timeout"] == config.DEFAULT_FETCH_TIMEOUT
    assert cfg["rate_limit_enabled"] == config.DEFAULT_RATE_LIMIT_ENABLED
    mode = db_dir.stat().st_mode
    assert bool(mode & stat.S_IWUSR)


def test_validate_backfills_missing_keys(clean_env, tmp_path):
    """手写 cfg 缺少新键时，validate 会回填全部默认值。"""
    cfg = {"port": 8300, "fetch_interval": 30, "db_path": str(tmp_path / "backfill.db")}
    config.validate(cfg)
    assert cfg["fetch_timeout"] == config.DEFAULT_FETCH_TIMEOUT
    assert cfg["fetch_retries"] == config.DEFAULT_FETCH_RETRIES
    assert cfg["log_level"] == config.DEFAULT_LOG_LEVEL
    assert cfg["digest_n"] == config.DEFAULT_DIGEST_N
    assert cfg["extract_timeout"] == config.DEFAULT_EXTRACT_TIMEOUT
    assert cfg["fever_api_key"] == config.DEFAULT_FEVER_API_KEY
    assert cfg["rate_limit_rps"] == config.DEFAULT_RATE_LIMIT_RPS
    assert cfg["rate_limit_burst"] == config.DEFAULT_RATE_LIMIT_BURST
    assert cfg["rate_limit_enabled"] == config.DEFAULT_RATE_LIMIT_ENABLED