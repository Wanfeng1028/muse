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
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def fresh_config():
    importlib.reload(config_module)
    config_module.get_settings.cache_clear()
    yield config_module
    config_module.get_settings.cache_clear()


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_invalid_db_raises(fresh_config, value):
    os.environ["LEDGER_DB"] = value
    with pytest.raises(ValueError) as excinfo:
        fresh_config.get_settings()
    message = str(excinfo.value)
    assert "LEDGER_DB" in message
    if value:
        assert repr(value) in message


def test_default_db_without_env(fresh_config):
    os.environ.pop("LEDGER_DB", None)
    settings = fresh_config.get_settings()
    assert settings.db_path == str(fresh_config.PROJECT_ROOT / "data/ledger.db")


def test_relative_db_path_passes_through(fresh_config):
    os.environ["LEDGER_DB"] = "data/ledger.db"
    settings = fresh_config.get_settings()
    assert settings.db_path == str(fresh_config.PROJECT_ROOT / "data/ledger.db")


def test_absolute_db_path_passes_through(fresh_config):
    os.environ["LEDGER_DB"] = "/tmp/ledger_abs_db_invalid_test.db"
    settings = fresh_config.get_settings()
    assert settings.db_path == "/tmp/ledger_abs_db_invalid_test.db"
