import os

os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"

import tempfile

import pytest
from werkzeug.security import generate_password_hash

from feedflow import config, create_app
from feedflow.login_lockout import LoginLockout


def _make_client(extra_cfg=None):
    tmp = tempfile.mkdtemp()
    cfg = {
        "db_path": os.path.join(tmp, "test.db"),
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 3600,
        "user_agent": "test",
        "auth_password_hash": generate_password_hash("pw123"),
        "secret_key": "test-secret-key",
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    return create_app(cfg).test_client()


# ---------- Unit tests ----------

def test_lockout_threshold():
    clock = [0.0]
    lk = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900, time_fn=lambda: clock[0])

    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0
    assert lk.is_locked("user1") is False

    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0
    assert lk.is_locked("user1") is False

    locked, remaining = lk.record_failure("user1")
    assert locked is True
    assert remaining == 900.0
    assert lk.is_locked("user1") is True
    assert lk.retry_after("user1") > 0


def test_lockout_success_clears():
    clock = [0.0]
    lk = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900, time_fn=lambda: clock[0])

    lk.record_failure("user1")
    lk.record_failure("user1")
    lk.record_success("user1")

    lk.record_failure("user1")
    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0
    assert lk.is_locked("user1") is False


def test_lockout_window_reset():
    clock = [0.0]
    lk = LoginLockout(max_attempts=3, window_seconds=60, lock_seconds=900, time_fn=lambda: clock[0])

    lk.record_failure("user1")
    clock[0] = 61.0

    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0

    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0
    assert lk.is_locked("user1") is False

    locked, remaining = lk.record_failure("user1")
    assert locked is True
    assert lk.is_locked("user1") is True


def test_lockout_expiry():
    clock = [0.0]
    lk = LoginLockout(max_attempts=3, window_seconds=900, lock_seconds=900, time_fn=lambda: clock[0])

    lk.record_failure("user1")
    lk.record_failure("user1")
    lk.record_failure("user1")
    assert lk.is_locked("user1") is True

    clock[0] = 901.0

    assert lk.is_locked("user1") is False
    assert lk.retry_after("user1") == 0

    locked, remaining = lk.record_failure("user1")
    assert locked is False
    assert remaining == 0.0


def test_lockout_invalid_params():
    with pytest.raises(ValueError):
        LoginLockout(max_attempts=0)
    with pytest.raises(ValueError):
        LoginLockout(lock_seconds=0)


# ---------- HTTP integration tests ----------

def test_http_locks_on_threshold():
    client = _make_client({
        "auth_max_attempts": 3,
        "auth_lock_seconds": 900,
        "auth_window_seconds": 900,
    })

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 429
    assert "尝试次数过多，请稍后再试" in resp.data.decode()
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after > 0

    resp = client.post("/login", data={"password": "pw123"})
    assert resp.status_code == 429

    resp = client.get("/")
    assert resp.status_code == 302


def test_http_success_resets_counter():
    client = _make_client({
        "auth_max_attempts": 3,
        "auth_lock_seconds": 900,
        "auth_window_seconds": 900,
    })

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "pw123"})
    assert resp.status_code == 302

    client.get("/logout")

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert "密码不正确" in resp.data.decode()


def test_http_default_threshold():
    client = _make_client()

    for _ in range(4):
        resp = client.post("/login", data={"password": "wrong"})
        assert resp.status_code == 200
        assert "密码不正确" in resp.data.decode()

    resp = client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 429
    assert "尝试次数过多，请稍后再试" in resp.data.decode()
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after > 0


def test_http_lockout_config_validation():
    base_cfg = {
        "db_path": "/tmp/test_lockout.db",
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 3600,
        "fetch_timeout": 30,
        "fetch_retries": 3,
        "digest_n": 5,
        "extract_timeout": 30,
        "rate_limit_rps": 10,
        "rate_limit_burst": 20,
        "rate_limit_enabled": False,
        "feed_dead_after": 30,
        "user_agent": "test",
        "auth_password_hash": generate_password_hash("pw123"),
        "secret_key": "test-secret-key",
    }

    with pytest.raises(SystemExit):
        config.validate({**base_cfg, "auth_max_attempts": 0})

    with pytest.raises(SystemExit):
        config.validate({**base_cfg, "auth_lock_seconds": 30})

    with pytest.raises(SystemExit):
        config.validate({**base_cfg, "auth_window_seconds": 0})
