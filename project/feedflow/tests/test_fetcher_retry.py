"""测试 fetcher 的下载重试逻辑。

覆盖：
- 前两次超时，第三次成功，最终 status="ok" 且下载调用 3 次
- HTTPError(404) 不重试，调用 1 次，status="error"，last_error_kind="http_4xx"
"""
import urllib.error

from feedflow import db as db_mod
from feedflow import fetcher, store

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>测试频道</title>
    <link>http://example.com</link>
    <description>测试用</description>
    <item>
      <title>第一篇</title>
      <link>http://example.com/1</link>
      <guid>http://example.com/1</guid>
      <description>hello</description>
    </item>
  </channel>
</rss>
"""


def _make_feed(db_path, feed_url):
    """直接插 feed 行（避免走网络），返回 store.get_feed 的 dict。"""
    conn = db_mod.get_conn(db_path)
    try:
        with db_mod.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description,"
                " interval_min, enabled, etag, modified, position, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("", "", feed_url, "", 0, 1, "", "", 0,
                 "2024-01-01T00:00:00+00:00"),
            )
            conn.commit()
            feed_id = cur.lastrowid
    finally:
        conn.close()
    return store.get_feed(db_path, feed_id)


def test_retry_on_timeout_then_ok(tmp_db, monkeypatch):
    """前两次超时，第三次成功，最终 status=ok，下载调用 3 次。"""
    db_mod.init_db(tmp_db)
    feed = _make_feed(tmp_db, "http://example.com/retry-ok.xml")

    calls = {"n": 0}

    def fake_http_get(url, user_agent, timeout, etag, modified):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise TimeoutError("timed out")
        return RSS_XML.encode("utf-8"), None, None, False

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)
    # 不走 trafilatura 真实网络
    monkeypatch.setattr(
        fetcher, "extract_text",
        lambda link, summary, ua, extract_timeout=15: (summary, "正文文本"),
    )
    # 加速：跳过真实退避 sleep
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    result = fetcher.fetch_feed(tmp_db, feed, "FeedFlow-test", timeout=5, retries=3)
    assert result["status"] == "ok"
    assert calls["n"] == 3
    assert result["added"] == 1

    row = store.get_feed(tmp_db, feed["id"])
    assert row["last_error_kind"] == ""
    assert int(row["consecutive_failures"]) == 0


def test_http_404_no_retry(tmp_db, monkeypatch):
    """HTTP 404 不重试：下载只调 1 次，status=error，last_error_kind=http_4xx。"""
    db_mod.init_db(tmp_db)
    feed = _make_feed(tmp_db, "http://example.com/not-found.xml")

    calls = {"n": 0}

    def fake_http_get(url, user_agent, timeout, etag, modified):
        calls["n"] += 1
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(fetcher, "_http_get", fake_http_get)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)

    result = fetcher.fetch_feed(tmp_db, feed, "FeedFlow-test", timeout=5, retries=3)
    assert result["status"] == "error"
    assert calls["n"] == 1

    row = store.get_feed(tmp_db, feed["id"])
    assert row["last_error_kind"] == "http_4xx"
    assert int(row["consecutive_failures"]) == 1


def test_classify_error_kinds():
    """失败分类函数覆盖主要类型。"""
    assert fetcher.classify_error(TimeoutError("t")) == "timeout"
    err404 = urllib.error.HTTPError("http://x", 404, "NF", {}, None)
    assert fetcher.classify_error(err404) == "http_4xx"
    err500 = urllib.error.HTTPError("http://x", 500, "SE", {}, None)
    assert fetcher.classify_error(err500) == "http_5xx"
    assert fetcher.classify_error(ValueError("bad feed")) == "parse_error"
    assert fetcher.classify_error(RuntimeError("?")) == "unknown"
