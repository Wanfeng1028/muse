"""抓取源健康检查（死源标记/复活）测试。"""

import os

import pytest

from feedflow import config, create_app, db, store


def _write_feed(db_path, feed_url="http://example.com/feed.xml", **overrides):
    """直插 feeds 表，避开网络解析。"""
    fields = {
        "folder_id": None,
        "title": "测试源",
        "site_url": "http://example.com",
        "feed_url": feed_url,
        "description": "",
        "interval_min": 30,
        "enabled": 1,
        "last_fetched_at": "",
        "last_status": "",
        "last_error": "",
        "last_error_kind": "",
        "consecutive_failures": 0,
        "etag": "",
        "modified": "",
        "position": 0,
        "created_at": db.utcnow(),
    }
    fields.update(overrides)
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    with db.write_lock:
        conn = db.get_conn(db_path)
        try:
            cur = conn.execute(
                f"INSERT INTO feeds ({cols}) VALUES ({placeholders})",
                list(fields.values()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


# ---------- config ----------

def test_config_feed_dead_after_default(monkeypatch):
    monkeypatch.delenv("FEEDFLOW_FEED_DEAD_AFTER", raising=False)
    cfg = config.load()
    assert cfg["feed_dead_after"] == 10


def test_config_feed_dead_after_env_override(monkeypatch):
    monkeypatch.setenv("FEEDFLOW_FEED_DEAD_AFTER", "3")
    cfg = config.load()
    assert cfg["feed_dead_after"] == 3


def test_config_feed_dead_after_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("FEEDFLOW_FEED_DEAD_AFTER", "abc")
    cfg = config.load()
    assert cfg["feed_dead_after"] == 10


def test_config_feed_dead_after_zero_falls_back(monkeypatch):
    monkeypatch.setenv("FEEDFLOW_FEED_DEAD_AFTER", "0")
    cfg = config.load()
    assert cfg["feed_dead_after"] == 10


def test_config_validate_setdefault_feed_dead_after(tmp_path):
    cfg = {
        "db_path": str(tmp_path / "t.db"),
        "port": 8300,
        "fetch_interval": 30,
    }
    config.validate(cfg)
    assert cfg["feed_dead_after"] == 10


# ---------- migration ----------

def test_migration_adds_dead_columns(tmp_path):
    db_path = str(tmp_path / "m.db")
    db.init_db(db_path)
    conn = db.get_conn(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(feeds)").fetchall()}
    finally:
        conn.close()
    assert "is_dead" in cols
    assert "dead_at" in cols


# ---------- set_fetch_result ----------

def test_set_fetch_result_marks_dead_on_threshold(tmp_path):
    db_path = str(tmp_path / "s.db")
    db.init_db(db_path)
    fid = _write_feed(db_path)
    store.set_fetch_result(
        db_path, fid, "error", "boom", "", "",
        error_kind="network", failures=10, dead_after=10,
    )
    feed = store.get_feed(db_path, fid)
    assert feed["is_dead"] == 1
    assert feed["dead_at"] != ""
    assert feed["consecutive_failures"] == 10


def test_set_fetch_result_below_threshold_not_dead(tmp_path):
    db_path = str(tmp_path / "s.db")
    db.init_db(db_path)
    fid = _write_feed(db_path)
    store.set_fetch_result(
        db_path, fid, "error", "boom", "", "",
        error_kind="network", failures=9, dead_after=10,
    )
    feed = store.get_feed(db_path, fid)
    assert feed["is_dead"] == 0
    assert feed["dead_at"] == ""


def test_set_fetch_result_ok_resets_dead(tmp_path):
    db_path = str(tmp_path / "s.db")
    db.init_db(db_path)
    fid = _write_feed(db_path)
    store.set_fetch_result(
        db_path, fid, "error", "boom", "", "",
        error_kind="network", failures=10, dead_after=10,
    )
    store.set_fetch_result(
        db_path, fid, "ok", "", "etag1", "mod1",
        error_kind="", failures=0, dead_after=10,
    )
    feed = store.get_feed(db_path, fid)
    assert feed["is_dead"] == 0
    assert feed["dead_at"] == ""
    assert feed["consecutive_failures"] == 0


def test_due_feeds_excludes_dead(tmp_path):
    db_path = str(tmp_path / "d.db")
    db.init_db(db_path)
    alive_id = _write_feed(db_path, feed_url="http://a.example/feed.xml")
    dead_id = _write_feed(db_path, feed_url="http://b.example/feed.xml")
    store.set_fetch_result(
        db_path, dead_id, "error", "boom", "", "",
        error_kind="network", failures=10, dead_after=10,
    )
    ids = {f["id"] for f in store.due_feeds(db_path, store._now_iso(), 30)}
    assert alive_id in ids
    assert dead_id not in ids


def test_reactivate_feed_missing_returns_false(tmp_path):
    db_path = str(tmp_path / "r.db")
    db.init_db(db_path)
    assert store.reactivate_feed(db_path, 9999) is False


def test_reactivate_feed_clears_state(tmp_path):
    db_path = str(tmp_path / "r.db")
    db.init_db(db_path)
    fid = _write_feed(db_path)
    store.set_fetch_result(
        db_path, fid, "error", "boom", "", "",
        error_kind="network", failures=10, dead_after=10,
    )
    assert store.reactivate_feed(db_path, fid) is True
    feed = store.get_feed(db_path, fid)
    assert feed["is_dead"] == 0
    assert feed["dead_at"] == ""
    assert feed["consecutive_failures"] == 0


# ---------- API ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FEEDFLOW_DB", str(tmp_path / "api.db"))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_reactivate_404(client, tmp_path):
    resp = client.post("/api/feeds/9999/reactivate")
    assert resp.status_code == 404


def test_api_reactivate_200(client, tmp_path):
    db_path = os.environ["FEEDFLOW_DB"]
    db.init_db(db_path)
    fid = _write_feed(db_path)
    store.set_fetch_result(
        db_path, fid, "error", "boom", "", "",
        error_kind="network", failures=10, dead_after=10,
    )
    resp = client.post(f"/api/feeds/{fid}/reactivate")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_dead"] == 0
    assert data["dead_at"] == ""
    assert data["consecutive_failures"] == 0
