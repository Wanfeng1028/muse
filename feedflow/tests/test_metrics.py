"""Prometheus 指标测试（A 批）。"""

import pytest

from feedflow import fetcher, store
from feedflow import metrics as metrics_mod


def _db_path(app):
    return app.config["FEEDFLOW"]["db_path"]


def test_metrics_endpoint_basic(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    ct = resp.headers.get("Content-Type", "")
    assert "text/plain" in ct
    body = resp.get_data(as_text=True)
    assert "# HELP feedflow_fetch_total" in body
    for name in (
        "feedflow_feeds_total",
        "feedflow_articles_total",
        "feedflow_unread_total",
        "feedflow_starred_total",
    ):
        assert name in body


def test_fetch_ok_increments(app, tmp_path):
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>t</title><link>http://example.com</link>"
        "<description>d</description>"
        "<item><title>a</title><link>http://example.com/a</link>"
        "<guid>a</guid></item>"
        "</channel></rss>",
        encoding="utf-8",
    )
    db_path = _db_path(app)
    feed_id = store.create_feed(db_path, str(feed_file))
    feed = {"id": feed_id, "feed_url": str(feed_file)}
    before = metrics_mod._fetch_total.get("ok", 0)
    result = fetcher.fetch_feed(db_path, feed, "test-agent")
    assert result["status"] == "ok"
    assert result["added"] == 1
    assert metrics_mod._fetch_total.get("ok", 0) >= before + 1
    text = metrics_mod.render(db_path)
    assert 'feedflow_fetch_total{status="ok"}' in text
    assert "feedflow_articles_stored_total" in text


def test_fetch_error_unknown(app):
    db_path = _db_path(app)
    feed_id = store.create_feed(db_path, "http://127.0.0.1:9/rss.xml")
    feed = {"id": feed_id, "feed_url": "http://127.0.0.1:9/"}
    before = metrics_mod._fetch_errors_total.get("unknown", 0)
    result = fetcher.fetch_feed(
        db_path, feed, "test-agent", timeout=1, retries=0
    )
    assert result["status"] == "error"
    assert metrics_mod._fetch_errors_total.get("unknown", 0) >= before + 1
    text = metrics_mod.render(db_path)
    assert 'feedflow_fetch_errors_total{kind="unknown"}' in text


def test_unread_gauge_realtime(app, client):
    db_path = _db_path(app)
    before = store.stats(db_path)["unread"]
    feed_id = store.create_feed(db_path, "http://example.com/feed")
    store.insert_article(
        db_path,
        feed_id=feed_id,
        guid="g1",
        title="title",
        author="",
        link="http://example.com/a",
        summary="",
        content_html="",
        content_text="body text",
        published_at=None,
    )
    after = store.stats(db_path)["unread"]
    assert after >= before + 1
    body = client.get("/metrics").get_data(as_text=True)
    assert "feedflow_unread_total" in body
    # gauge 值与 store.stats 一致
    for line in body.splitlines():
        if line.startswith("feedflow_unread_total "):
            assert int(line.split()[-1]) == after
            break
    else:
        pytest.fail("feedflow_unread_total gauge line missing")


def test_route_normalization(client):
    client.get("/metrics")
    client.get("/healthz")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'route="/metrics"' in body
    assert 'route="/metrics?x=1"' not in body
    assert "?x=1" not in body


def test_render_tolerates_bad_db(tmp_path):
    bad = str(tmp_path / "nonexistent_dir" / "bad.db")
    text = metrics_mod.render(bad)
    assert "feedflow_feeds_total" in text
