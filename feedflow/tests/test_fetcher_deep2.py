import http.client
import time
import urllib.error
import urllib.request

import pytest

from feedflow import db, fetcher


def _make_http_error(url, code, msg, headers=None, fp=None):
    return urllib.error.HTTPError(url, code, msg, headers, fp)


def _make_headers(pairs):
    msg = http.client.HTTPMessage()
    for k, v in pairs:
        msg[k] = v
    return msg


def _insert_feed(db_path, title, feed_url):
    cur = db.execute_write(db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (title, feed_url, "2025-01-01T00:00:00+00:00"),
    )
    return cur


class _FakeResponse:
    def __init__(self, body, headers):
        self._body = body
        self.headers = headers

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_fetch_remote_non_retryable_attempts_once(monkeypatch):
    calls = {"n": 0}

    def fake_http_get(url, user_agent, timeout, etag, modified):
        calls["n"] += 1
        raise _make_http_error(url, 404, "nf", None, None)

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)

    with pytest.raises(urllib.error.HTTPError):
        fetcher._fetch_remote(
            "http://example.com/feed", "UA", 5.0, 3, None, None, 1
        )

    assert calls["n"] == 1


def test_fetch_remote_exponential_backoff_delays(monkeypatch):
    state = {"n": 0}
    delays = []

    def fake_http_get(url, user_agent, timeout, etag, modified):
        state["n"] += 1
        if state["n"] <= 2:
            raise urllib.error.URLError("boom")
        return (b"x", None, None, False)

    def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    result = fetcher._fetch_remote(
        "http://example.com/feed", "UA", 5.0, 2, None, None, 1
    )

    assert state["n"] == 3
    assert result == (b"x", None, None, False)
    assert len(delays) == 2
    assert 2.0 <= delays[0] < 2.5
    assert 4.0 <= delays[1] < 4.5


def test_fetch_remote_honors_retry_after_header(monkeypatch):
    state = {"n": 0}
    delays = []

    def fake_http_get(url, user_agent, timeout, etag, modified):
        state["n"] += 1
        if state["n"] == 1:
            headers = _make_headers([("Retry-After", "10")])
            raise _make_http_error(url, 429, "slow", headers, None)
        return (b"ok", None, None, False)

    def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    result = fetcher._fetch_remote(
        "http://example.com/feed", "UA", 5.0, 2, None, None, 1
    )

    assert state["n"] == 2
    assert result == (b"ok", None, None, False)
    assert len(delays) == 1
    assert 10.0 <= delays[0] < 10.6


def test_fetch_remote_retry_after_capped(monkeypatch):
    state = {"n": 0}
    delays = []

    def fake_http_get(url, user_agent, timeout, etag, modified):
        state["n"] += 1
        if state["n"] == 1:
            headers = _make_headers([("Retry-After", "120")])
            raise _make_http_error(url, 429, "slow", headers, None)
        return (b"ok", None, None, False)

    def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)
    monkeypatch.setattr(time, "sleep", fake_sleep)

    fetcher._fetch_remote(
        "http://example.com/feed", "UA", 5.0, 2, None, None, 1
    )

    assert len(delays) == 1
    assert 60.0 <= delays[0] < 60.6


def test_http_get_conditional_request_headers(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        captured["timeout"] = timeout
        headers = _make_headers(
            [("ETag", '"new-etag"'), ("Last-Modified", "Thu, 02 Jan 2025 00:00:00 GMT")]
        )
        return _FakeResponse(b"<rss/>", headers)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    body, new_etag, new_modified, not_modified = fetcher._http_get(
        "http://example.com/feed",
        "UA",
        5,
        etag='"abc"',
        modified="Wed, 01 Jan 2025 00:00:00 GMT",
    )

    req = captured["req"]
    assert isinstance(req, urllib.request.Request)
    assert req.get_header("If-none-match") == '"abc"'
    assert req.get_header("If-modified-since") == "Wed, 01 Jan 2025 00:00:00 GMT"
    assert body == b"<rss/>"
    assert new_etag == '"new-etag"'
    assert new_modified == "Thu, 02 Jan 2025 00:00:00 GMT"
    assert not_modified is False


def test_http_get_handles_304(monkeypatch):
    def fake_urlopen(req, timeout=None):
        headers = _make_headers([("ETag", '"e1"'), ("Last-Modified", '"m1"')])
        raise _make_http_error(req.full_url, 304, "nm", headers, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    body, new_etag, new_modified, not_modified = fetcher._http_get(
        "http://example.com/feed", "UA", 5, etag='"x"', modified="some"
    )

    assert body is None
    assert new_etag == '"e1"'
    assert new_modified == '"m1"'
    assert not_modified is True


def test_local_feed_bozo_with_entries_still_succeeds(tmp_db, tmp_path):
    feed_path = tmp_path / "feed.xml"
    feed_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>http://example.com</link>
    <description>desc</description>
    <item>
      <title>A &amp; B</title>
      <link></link>
      <guid>guid-1</guid>
      <description>first</description>
    </item>
    <item>
      <title>Second &amp; More</title>
      <link></link>
      <guid>guid-2</guid>
      <description>second</description>
    </item>
  </channel>
</rss>
""",
        encoding="utf-8",
    )

    fid = _insert_feed(tmp_db, "Test Feed", str(feed_path))

    feed = {
        "id": fid,
        "feed_url": str(feed_path),
        "etag": "",
        "modified": "",
        "consecutive_failures": 0,
    }

    result = fetcher.fetch_feed(str(tmp_db), feed, "UA")

    assert result["status"] == "ok"
    assert result["added"] == 2


def test_classify_error_passthrough_fetch_error_kind():
    exc = fetcher.FetchError("x", "dns", True)
    assert fetcher.classify_error(exc) == "dns"


def test_retry_after_seconds_fetch_error_capped():
    exc = fetcher.FetchError("x", "k", True, retry_after=100)
    assert fetcher._retry_after_seconds(exc) == 60.0