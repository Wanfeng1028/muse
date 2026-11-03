# tests/conftest.py
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow import create_app
from feedflow import db as db_mod


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / "t.db")
    db_mod.init_db(path)
    return path


@pytest.fixture
def app(tmp_db):
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    application = create_app({
        "db_path": tmp_db,
        "host": "127.0.0.1",
        "port": 8300,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    })
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
