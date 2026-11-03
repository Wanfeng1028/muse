import importlib
import os

import pytest

from ledger import config as config_module

_ENV_KEYS = ("LEDGER_DB", "LEDGER_HOST", "LEDGER_PORT", "LEDGER_LOG_LEVEL", "LEDGER_BASE_CURRENCY")


@pytest.fixture(autouse=True)
def env_guard():
    snapshot = {k: os.environ.get(k) for k in _ENV_KEYS}
    yield
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def fresh_config():
    mod = importlib.reload(config_module)
    mod.get_settings.cache_clear()
    yield mod
    mod.get_settings.cache_clear()


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_invalid_host_raises(fresh_config, value):
    os.environ["LEDGER_HOST"] = value
    with pytest.raises(ValueError) as exc_info:
        fresh_config.get_settings()
    message = str(exc_info.value)
    assert "LEDGER_HOST" in message
    if value:
        assert repr(value) in message


def test_default_host_without_env(fresh_config):
    os.environ.pop("LEDGER_HOST", None)
    settings = fresh_config.get_settings()
    assert settings.host == "127.0.0.1"


@pytest.mark.parametrize("value", ["0.0.0.0", "localhost"])
def test_valid_host_passes_through(fresh_config, value):
    os.environ["LEDGER_HOST"] = value
    settings = fresh_config.get_settings()
    assert settings.host == value


def test_whitespace_padded_host_passes_unchanged(fresh_config):
    value = " 127.0.0.1 "
    os.environ["LEDGER_HOST"] = value
    settings = fresh_config.get_settings()
    assert settings.host == value
