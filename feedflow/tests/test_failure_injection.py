# tests/test_failure_injection.py
# 失败注入测试（B 批）。
#
# 场景速览（每个用例一句话）：
# 1. DB 连接被斩断：sqlite3.connect 抛 OperationalError，GET / 500 不崩，恢复后 /healthz 200 且 db==ok。
# 2. healthz 降级不断服务：同一注入下 /healthz 仍 200，status=degraded、db=error。
# 3. 抓取 500 重试耗尽：本地 http.server 返回 500，fetch_feed retries=0 -> status=error 且库中失败计数递增。
# 4. 抓取超时：本地服务 sleep 3s，timeout=1、retries=0 -> status=error，且总耗时 < 5s。
# 5. 连接被拒绝：不可达端口，retries=0 -> status=error，error_kind 属于 {"unknown"}。
# 6. 坏备份拒绝恢复：64 字节垃圾文件 -> restore 抛 ValueError 且信息含“不是合法的 SQLite 数据库”，目标库未被污染。
# 7. trafilatura 失败回落摘要：不可达 URL + 简单 HTML -> content_text 含去标签后的摘要文本。
# 8. Fever 未配置即关闭：无 fever_api_key -> POST /fever 200 且 auth==0。
# 9. 无效 OPML 不炸：垃圾字节与空 OPML 均 302 且 Location 含 imported=0。
# 10. 单条目失败不影响整源：本地 RSS 含缺 link/id 条目 -> status=ok 且 added 只计合法条目。
# 11. 404 不带敏感信息：GET 不存在路径 -> 404。
# 12. dedup 坏输入防御：空文本 simhash/hamming 确定性行为，不抛异常。

import contextlib
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from feedflow import backup, fetcher, store

# ---------------------------------------------------------------------------
# 通用本地 HTTP 服务工具（daemon 线程 + 用完即关）
# ---------------------------------------------------------------------------

class _Handler500(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(500)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"server error")

    def log_message(self, *a, **k):
        pass


class _HandlerSlow(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(3)
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.end_headers()
        self.wfile.write(b"<rss></rss>")

    def log_message(self, *a, **k):
        pass


def _start_server(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


def _stop_server(server):
    with contextlib.suppress(Exception):
        server.shutdown()
    with contextlib.suppress(Exception):
        server.server_close()


# ---------------------------------------------------------------------------
# 场景 1 & 2：DB 连接被斩断
# ---------------------------------------------------------------------------

def _boom(*a, **k):
    raise sqlite3.OperationalError("injected")


def test_db_connect_broken_root_500_then_recover_healthz_ok(client, monkeypatch):
    # 注入：sqlite3.connect 直接抛 OperationalError
    monkeypatch.setattr("sqlite3.connect", _boom)
    r = client.get("/")
    assert r.status_code == 500

    # 恢复：解除 monkeypatch
    monkeypatch.undo()

    r2 = client.get("/healthz")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body is not None
    assert body.get("db") == "ok"


def test_db_connect_broken_healthz_degraded_but_alive(client, monkeypatch):
    # 注入：sqlite3.connect 抛错，healthz 应宽捕获并降级
    monkeypatch.setattr("sqlite3.connect", _boom)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None
    assert body.get("status") == "degraded"
    assert body.get("db") == "error"


# ---------------------------------------------------------------------------
# 场景 3：抓取 500 重试耗尽
# ---------------------------------------------------------------------------

def test_fetch_500_retries_exhausted(tmp_db):
    server, port = _start_server(_Handler500)
    try:
        feed_url = f"http://127.0.0.1:{port}/rss.xml"
        feed_id = store.create_feed(tmp_db, feed_url)
        feed = {"id": feed_id, "feed_url": feed_url}

        result = fetcher.fetch_feed(
            tmp_db, feed, user_agent="FeedFlow-test",
            timeout=5, retries=0,
        )
        assert result.get("status") == "error"
        assert result.get("error")

        # 直接读库验证失败被写入：consecutive_failures 递增
        conn = sqlite3.connect(tmp_db)
        try:
            cur = conn.execute(
                "SELECT consecutive_failures, last_status FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        assert row is not None
        consecutive_failures, last_status = row
        assert (consecutive_failures or 0) >= 1
        assert last_status == "error"
    finally:
        _stop_server(server)


# ---------------------------------------------------------------------------
# 场景 4：抓取超时
# ---------------------------------------------------------------------------

def test_fetch_timeout_is_bounded(tmp_db):
    server, port = _start_server(_HandlerSlow)
    try:
        feed_url = f"http://127.0.0.1:{port}/rss.xml"
        feed_id = store.create_feed(tmp_db, feed_url)
        feed = {"id": feed_id, "feed_url": feed_url}
        t0 = time.monotonic()
        result = fetcher.fetch_feed(
            tmp_db, feed, user_agent="FeedFlow-test",
            timeout=1, retries=0,
        )
        elapsed = time.monotonic() - t0
        assert result.get("status") == "error"
        assert result.get("error")
        # 服务端 sleep 3s，客户端 timeout=1 且不重试，必须远小于 5s
        assert elapsed < 5.0
    finally:
        _stop_server(server)


# ---------------------------------------------------------------------------
# 场景 5：连接被拒绝
# ---------------------------------------------------------------------------

def test_fetch_connection_refused(tmp_db):
    # 端口 9 上无服务：连接被拒绝
    feed_id = store.create_feed(tmp_db, "http://127.0.0.1:9/rss.xml")
    feed = {"id": feed_id, "feed_url": "http://127.0.0.1:9/rss.xml"}
    result = fetcher.fetch_feed(
        tmp_db, feed, user_agent="FeedFlow-test",
        timeout=5, retries=0,
    )
    assert result.get("status") == "error"
    assert result.get("error")

    # classify_error 对 ConnectionRefusedError 包装的 URLError 归类为 unknown
    import urllib.error
    exc = urllib.error.URLError(ConnectionRefusedError("refused"))
    kind = fetcher.classify_error(exc)
    assert kind in {"unknown"}


# ---------------------------------------------------------------------------
# 场景 6：坏备份拒绝恢复
# ---------------------------------------------------------------------------

def test_restore_rejects_garbage_backup(tmp_path):
    garbage = tmp_path / "garbage.bak"
    garbage.write_bytes(os.urandom(64))
    target = tmp_path / "restored.db"

    with pytest.raises(ValueError) as ei:
        backup.restore(str(garbage), str(target))
    assert "不是合法的 SQLite 数据库" in str(ei.value)

    # 目标文件未被垃圾覆盖：不存在，或大小为 0
    if os.path.exists(str(target)):
        assert os.path.getsize(str(target)) == 0


# ---------------------------------------------------------------------------
# 场景 7：trafilatura 失败回落摘要
# ---------------------------------------------------------------------------

def test_extract_text_falls_back_to_summary():
    _content_html, content_text = fetcher.extract_text(
        "http://127.0.0.1:9/x",
        "<p>摘要<b>文本</b></p>",
        "FeedFlow-test",
        extract_timeout=1,
    )
    assert isinstance(content_text, str)
    # 回落走 _html_to_text：标签被替换为空格后压缩，所以断言分词存在而非连写
    assert "摘要" in content_text and "文本" in content_text


# ---------------------------------------------------------------------------
# 场景 8：Fever 未配置即关闭
# ---------------------------------------------------------------------------

def test_fever_disabled_returns_auth_zero(client):
    r = client.post("/fever", data={"api_key": "xxx"})
    assert r.status_code == 200
    body = r.get_json()
    assert body is not None
    assert body.get("auth") == 0


# ---------------------------------------------------------------------------
# 场景 9：无效 OPML 不炸
# ---------------------------------------------------------------------------

def test_opml_import_garbage_and_empty(client):
    # 垃圾字节
    r1 = client.post(
        "/opml/import",
        data={"file": (b"not xml at all", "x.opml")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r1.status_code == 302
    loc1 = r1.headers.get("Location", "")
    assert "imported=0" in loc1

    # 合法但空的 OPML
    empty_opml = b'<opml version="1.0"><body></body></opml>'
    r2 = client.post(
        "/opml/import",
        data={"file": (empty_opml, "empty.opml")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r2.status_code == 302
    loc2 = r2.headers.get("Location", "")
    assert "imported=0" in loc2


# ---------------------------------------------------------------------------
# 场景 10：单条目失败不影响整源（本地文件分支）
# ---------------------------------------------------------------------------

def test_local_feed_partial_entries(tmp_db, tmp_path):
    # 一篇合法 entry（有 link 与 guid），一篇缺 link/id（会被跳过）
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>local</title>
    <link>http://example.com/</link>
    <description>d</description>
    <item>
      <title>good</title>
      <link>http://example.com/good</link>
      <guid>http://example.com/good</guid>
      <description>hello</description>
    </item>
    <item>
      <title>bad</title>
      <description>no link no guid</description>
    </item>
  </channel>
</rss>
"""
    p = tmp_path / "feed.xml"
    p.write_text(rss, encoding="utf-8")

    feed_id = store.create_feed(tmp_db, str(p))
    feed = {"id": feed_id, "feed_url": str(p)}

    result = fetcher.fetch_feed(
        tmp_db, feed, user_agent="FeedFlow-test",
        timeout=5, retries=0,
    )
    assert result.get("status") == "ok"
    # 只有一篇合法条目被计入
    assert result.get("added") == 1


# ---------------------------------------------------------------------------
# 场景 11：404 不带敏感信息
# ---------------------------------------------------------------------------

def test_404_on_unknown_path(client):
    r = client.get("/no-such-page-xyz")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 场景 12：dedup 坏输入防御
# ---------------------------------------------------------------------------

def test_dedup_defensive_on_bad_input():
    from feedflow import dedup

    # 空文本：tokenize 为空，simhash 应返回全零指纹且不抛异常
    h1 = dedup.simhash("")
    assert isinstance(h1, str) and len(h1) == 16
    assert dedup.hamming(h1, h1) == 0
    assert dedup.is_near_dup(h1, h1) is True
    # 非法输入的 hamming 按契约返回大值 64
    assert dedup.hamming("", h1) == 64
    assert dedup.hamming(None, h1) == 64
    # 正常文本同样确定性
    h2 = dedup.simhash("完全不同的一段文字内容填充长度")
    assert isinstance(h2, str) and len(h2) == 16
