from __future__ import annotations

import email.message
import time
import urllib.error

import feedparser
import pytest

from feedflow import db, fetcher, store


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    return db_path


def _make_feed(db_path, feed_url="http://f/x/"):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        ("f", feed_url, db.utcnow()),
    )
    row = db.query_one(db_path, "SELECT id FROM feeds WHERE feed_url=?", (feed_url,))
    return {
        "id": row["id"],
        "feed_url": feed_url,
        "etag": "",
        "modified": "",
        "consecutive_failures": 0,
    }


def _http_error(code, headers=None):
    return urllib.error.HTTPError(
        "http://x/", code, "err", headers if headers is not None else email.message.Message(), None
    )


def test_parse_feed_info_ok(monkeypatch):
    monkeypatch.setattr(
        feedparser,
        "parse",
        lambda url: {"feed": {"title": " T ", "link": "http://x", "description": "d"}},
    )
    info = fetcher.parse_feed_info("http://example.com/feed")
    assert info["title"] == "T"
    assert info["site_url"] == "http://x"
    assert info["description"] == "d"


def test_parse_feed_info_no_title_raises(monkeypatch):
    monkeypatch.setattr(feedparser, "parse", lambda url: {"feed": {}})
    with pytest.raises(ValueError):
        fetcher.parse_feed_info("http://example.com/feed")

    def _boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(feedparser, "parse", _boom)
    with pytest.raises(ValueError):
        fetcher.parse_feed_info("http://example.com/feed")


def test_html_to_text_entities_and_tags():
    assert fetcher._html_to_text("<p>a &amp; b</p>") == "a & b"
    assert fetcher._html_to_text("&amp;amp;") == "&"
    assert fetcher._html_to_text("") == ""


def test_html_to_text_collapses_whitespace():
    assert fetcher._html_to_text("<div>a</div>\n\n<b>b</b>") == "a b"


def test_iso_struct_time_and_none():
    iso = fetcher._iso(time.gmtime(0))
    assert iso is not None
    assert "1970" in iso
    assert iso.endswith("+00:00")
    assert fetcher._iso(None) is None


def test_download_config_cached():
    cfg15_a = fetcher._download_config(15)
    cfg15_b = fetcher._download_config(15)
    cfg16 = fetcher._download_config(16)
    assert cfg15_a is cfg15_b
    assert cfg15_a is not cfg16
    assert cfg15_a["DEFAULT"]["DOWNLOAD_TIMEOUT"] == "15"


def test_classify_error_matrix():
    assert fetcher.classify_error(TimeoutError("t")) == "timeout"
    assert fetcher.classify_error(TimeoutError("t")) == "timeout"
    assert fetcher.classify_error(_http_error(404)) == "http_4xx"
    assert fetcher.classify_error(_http_error(429)) == "http_4xx"
    assert fetcher.classify_error(_http_error(500)) == "http_5xx"
    assert fetcher.classify_error(_http_error(302)) == "unknown"
    assert (
        fetcher.classify_error(urllib.error.URLError("Name or service not known")) == "dns"
    )
    assert (
        fetcher.classify_error(urllib.error.URLError(TimeoutError("timed out")))
        == "timeout"
    )
    assert fetcher.classify_error(urllib.error.URLError("connection refused")) == "unknown"
    assert fetcher.classify_error(ValueError("x")) == "parse_error"
    assert fetcher.classify_error(RuntimeError("boom")) == "unknown"


def test_is_retryable_matrix():
    assert fetcher._is_retryable(TimeoutError("t")) is True
    assert fetcher._is_retryable(_http_error(429)) is True
    assert fetcher._is_retryable(_http_error(500)) is True
    assert fetcher._is_retryable(_http_error(404)) is False
    assert fetcher._is_retryable(urllib.error.URLError("x")) is True
    assert fetcher._is_retryable(ValueError("x")) is False
    assert fetcher._is_retryable(fetcher.FetchError("m", "k", True)) is True
    assert fetcher._is_retryable(fetcher.FetchError("m", "k", False)) is False


def test_retry_after_seconds_matrix():
    headers_120 = email.message.Message()
    headers_120["Retry-After"] = "120"
    assert fetcher._retry_after_seconds(_http_error(429, headers_120)) == 60.0

    headers_5 = email.message.Message()
    headers_5["Retry-After"] = "5"
    assert fetcher._retry_after_seconds(_http_error(429, headers_5)) == 5.0

    headers_empty = email.message.Message()
    assert fetcher._retry_after_seconds(_http_error(429, headers_empty)) is None

    headers_abc = email.message.Message()
    headers_abc["Retry-After"] = "abc"
    assert fetcher._retry_after_seconds(_http_error(429, headers_abc)) is None

    headers_404 = email.message.Message()
    headers_404["Retry-After"] = "10"
    assert fetcher._retry_after_seconds(_http_error(404, headers_404)) is None


def test_parse_entries_skips_and_continues(tmp_db, monkeypatch):
    feed = _make_feed(tmp_db)
    fid = feed["id"]

    store.insert_article(
        tmp_db,
        feed_id=fid,
        guid="existing-guid",
        title="old",
        author="",
        link="http://old/",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )

    parsed = {
        "entries": [
            {"title": "no guid"},
            {
                "id": "existing-guid",
                "title": "dup",
                "link": "http://dup/",
                "summary": "s",
            },
            {
                "id": "boom-guid",
                "title": "boom",
                "link": "http://boom/",
                "summary": "s",
            },
            {
                "id": "ok-1",
                "title": "t1",
                "link": "http://ok1/",
                "summary": "s1",
            },
            {
                "id": "ok-2",
                "title": "t2",
                "link": "http://ok2/",
                "summary": "s2",
            },
        ]
    }

    real_extract = fetcher.extract_text

    def fake_extract(link, summary, user_agent, extract_timeout=15):
        if link == "http://boom/":
            raise RuntimeError("extract failed")
        return real_extract(link, summary, user_agent, extract_timeout=extract_timeout)

    monkeypatch.setattr(fetcher, "extract_text", fake_extract)

    added = fetcher._parse_entries(parsed, tmp_db, fid, "ua")
    assert added == 2

    row = db.query_one(
        tmp_db, "SELECT COUNT(*) AS c FROM articles WHERE feed_id=?", (fid,)
    )
    assert row["c"] == 3


def test_parse_entries_published_parsed(tmp_db):
    feed = _make_feed(tmp_db)
    fid = feed["id"]

    parsed = {
        "entries": [
            {
                "id": "pub-1",
                "title": "with pub",
                "link": "http://p/",
                "summary": "s",
                "published_parsed": time.gmtime(0),
            }
        ]
    }

    added = fetcher._parse_entries(parsed, tmp_db, fid, "ua")
    assert added == 1

    row = db.query_one(
        tmp_db,
        "SELECT published_at FROM articles WHERE feed_id=? AND guid=?",
        (fid, "pub-1"),
    )
    assert row is not None
    assert row["published_at"] is not None
    assert "1970" in row["published_at"]


def test_fetch_feed_local_file(tmp_path, tmp_db):
    rss = tmp_path / "feed.xml"
    rss.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Local Feed</title>
    <link>http://local/</link>
    <description>local</description>
    <item>
      <title>Item 1</title>
      <link>http://local/1</link>
      <description>First</description>
      <guid>local-1</guid>
    </item>
    <item>
      <title>Item 2</title>
      <link>http://local/2</link>
      <description>Second</description>
      <guid>local-2</guid>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    feed = _make_feed(tmp_db, feed_url=str(rss))
    result = fetcher.fetch_feed(tmp_db, feed, "ua")
    assert result["status"] == "ok"
    assert result["added"] == 2
    assert result["error"] == ""

    result2 = fetcher.fetch_feed(tmp_db, feed, "ua")
    assert result2["status"] == "ok"
    assert result2["added"] == 0
    assert result2["error"] == ""


def test_fetch_feed_local_invalid_file(tmp_path, tmp_db):
    bad = tmp_path / "bad.xml"
    bad.write_text("this is not xml at all", encoding="utf-8")

    feed = _make_feed(tmp_db, feed_url=str(bad))
    result = fetcher.fetch_feed(tmp_db, feed, "ua")
    assert result["status"] == "error"
    assert result["error"] != ""


def test_extract_text_no_link_fallback():
    html_in = "<p>hi &amp; bye</p>"
    content_html, content_text = fetcher.extract_text("", html_in, "ua")
    assert content_html == html_in
    assert content_text == "hi & bye"


def test_extract_text_fetch_failure_fallback(monkeypatch):
    def boom(url, **kwargs):
        raise RuntimeError("network failure")

    monkeypatch.setattr(fetcher.trafilatura, "fetch_url", boom)

    summary = "<p>fallback &amp; text</p>"
    content_html, content_text = fetcher.extract_text(
        "http://example.com/article", summary, "ua"
    )
    assert content_html == summary
    assert content_text == fetcher._html_to_text(summary)
    assert content_text == "fallback & text"
