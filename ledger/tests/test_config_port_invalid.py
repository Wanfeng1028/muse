import importlib
import os

import pytest

from ledger import config as config_module

_ENV_KEYS = (
    "LEDGER_DB",
    "LEDGER_HOST",
    "LEDGER_PORT",
    "LEDGER_LOG_LEVEL",
    "LEDGER_BASE_CURRENCY",
)


@pytest.fixture(autouse=True)
def env_guard():
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    yield
    for key in _ENV_KEYS:
        if saved[key] is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved[key]


@pytest.fixture(autouse=True)
def fresh_config():
    mod = importlib.reload(config_module)
    mod.get_settings.cache_clear()
    yield mod
    mod.get_settings.cache_clear()


@pytest.mark.parametrize("raw_port", ["not-a-number", "8100x", "", "8100.5"])
def test_invalid_port_raises(fresh_config, raw_port):
    os.environ["LEDGER_PORT"] = raw_port
    with pytest.raises(ValueError) as exc_info:
        fresh_config.get_settings()
    message = str(exc_info.value)
    assert "LEDGER_PORT" in message
    if raw_port:
        assert raw_port in message


def test_valid_port_passes_through(fresh_config):
    os.environ["LEDGER_PORT"] = "8200"
    settings = fresh_config.get_settings()
    assert settings.port == 8200


def test_whitespace_padded_port_passes(fresh_config):
    os.environ["LEDGER_PORT"] = " 8200 "
    settings = fresh_config.get_settings()
    assert settings.port == 8200
