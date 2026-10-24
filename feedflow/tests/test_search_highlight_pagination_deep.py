import os

import pytest

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


def _insert_entries(db_path, feed_id, entries):
    conn = db_mod.get_conn(db_path)
    try:
        for title, summary in entries:
            conn.execute(
                "INSERT INTO articles (feed_id, guid, title, link, summary, content_text, published_at, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    feed_id,
                    "guid-" + title,
                    title,
                    "http://example.com/" + title,
                    summary,
                    summary,
                    "2024-01-01T00:00:00+00:00",
                    "2024-01-01T00:00:00+00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_highlight_snippet_basic():
    from feedflow.store import highlight_snippet

    out = highlight_snippet("hello world", "world")
    assert "<mark>world</mark>" in out


def test_highlight_snippet_no_keyword():
    from feedflow.store import highlight_snippet

    out = highlight_snippet("hello world", "")
    assert "<mark>" not in out
    assert "hello world" in out


def test_highlight_snippet_not_found():
    from feedflow.store import highlight_snippet

    out = highlight_snippet("hello world", "zzz")
    assert "<mark>" not in out


def test_highlight_snippet_escapes_html():
    from feedflow.store import highlight_snippet

    out = highlight_snippet("<script>alert(1)</script>", "alert")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<mark>alert</mark>" in out


def test_highlight_snippet_truncation_word_boundary():
    from feedflow.store import highlight_snippet

    text = "a" * 300 + " keyword " + "b" * 300
    max_len = 80
    out = highlight_snippet(text, "keyword", max_len=max_len)

    assert "<mark>keyword</mark>" in out
    assert out.count("<mark>") == out.count("</mark>")
    assert len(out) <= max_len + len("<mark></mark>")


def test_search_pagination_first_page(client, tmp_db):
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO feeds (title, site_url, feed_url, created_at) VALUES (?, ?, ?, ?)",
            ("f1", "http://f1.example.com", "http://f1.example.com/rss", "2024-01-01T00:00:00+00:00"),
        )
        conn.commit()
        feed_id = conn.execute("SELECT id FROM feeds WHERE feed_url = ?", ("http://f1.example.com/rss",)).fetchone()["id"]
    finally:
        conn.close()

    entries = [(f"t{i:d}", f"common keyword here {i:d}") for i in range(30)]
    _insert_entries(tmp_db, feed_id, entries)

    resp = client.get("/search?q=keyword&page=1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<mark>keyword</mark>" in body


def test_search_pagination_second_page(client, tmp_db):
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO feeds (title, site_url, feed_url, created_at) VALUES (?, ?, ?, ?)",
            ("f1", "http://f1.example.com", "http://f1.example.com/rss", "2024-01-01T00:00:00+00:00"),
        )
        conn.commit()
        feed_id = conn.execute("SELECT id FROM feeds WHERE feed_url = ?", ("http://f1.example.com/rss",)).fetchone()["id"]
    finally:
        conn.close()

    entries = [(f"t{i:d}", f"common keyword here {i:d}") for i in range(30)]
    _insert_entries(tmp_db, feed_id, entries)

    resp = client.get("/search?q=keyword&page=2")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<mark>keyword</mark>" in body


def test_search_pagination_beyond_last_page(client, tmp_db):
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "INSERT INTO feeds (title, site_url, feed_url, created_at) VALUES (?, ?, ?, ?)",
            ("f1", "http://f1.example.com", "http://f1.example.com/rss", "2024-01-01T00:00:00+00:00"),
        )
        conn.commit()
        feed_id = conn.execute("SELECT id FROM feeds WHERE feed_url = ?", ("http://f1.example.com/rss",)).fetchone()["id"]
    finally:
        conn.close()

    entries = [(f"t{i:d}", f"common keyword here {i:d}") for i in range(5)]
    _insert_entries(tmp_db, feed_id, entries)

    resp = client.get("/search?q=keyword&page=999")
    assert resp.status_code == 200


def test_search_no_keyword(client):
    resp = client.get("/search")
    assert resp.status_code == 200


def test_search_empty_result(client):
    resp = client.get("/search?q=nonexistentkeywordxyz")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<mark>" not in body
