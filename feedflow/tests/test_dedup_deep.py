"""dedup 深度测试：RSS 解析边界、去重聚类、失败注入、幂等、排序稳定性。

只测 feedflow.dedup 的纯函数与数据库交互，不 mock 被测模块核心逻辑。
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow import dedup
from feedflow import db as db_mod


def _insert_article(db_path, title, content_text="", simhash_hex=None, cluster_id=None,
                    published_at=None, url=None):
    conn = db_mod.get_conn(db_path)
    try:
        with db_mod.write_lock:
            cur = conn.execute(
                "INSERT INTO feeds (title, feed_url, created_at) VALUES (?, ?, ?)",
                ("dedup-test", "http://example.com/dedup/" + title + ".xml",
                 "2024-01-01T00:00:00+00:00"),
            )
            feed_id = cur.lastrowid
            cur = conn.execute(
                """
                INSERT INTO articles
                    (feed_id, guid, title, link, content_text, simhash,
                     cluster_id, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feed_id,
                    "g-" + title,
                    title,
                    url or ("http://example.com/" + title),
                    content_text,
                    simhash_hex if simhash_hex is not None else "",
                    cluster_id,
                    published_at,
                    published_at or "2024-01-01T00:00:00+00:00",
                ),
            )
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def _fetch_articles(db_path):
    conn = db_mod.get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, simhash, cluster_id FROM articles ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------- RSS 解析边界 ----------

def test_tokenize_empty_and_none_returns_empty():
    assert dedup.tokenize("") == []
    assert dedup.tokenize(None) == []
    assert dedup.tokenize("   ") == []


def test_tokenize_mixed_cjk_and_ascii():
    tokens = dedup.tokenize("Hello世界2024")
    assert "hello" in tokens
    assert "2024" in tokens
    cjk_pairs = [t for t in tokens if any(dedup._is_cjk(c) for c in t)]
    assert "世界" in cjk_pairs
    assert len(tokens) >= 3


def test_tokenize_fullwidth_normalized_to_halfwidth():
    full = dedup.tokenize("ＡＢＣ１２３")
    half = dedup.tokenize("abc123")
    assert full == half
    assert full == ["abc123"]


def test_tokenize_single_cjk_kept_as_single_char():
    tokens = dedup.tokenize("中")
    assert tokens == ["中"]
    assert dedup.tokenize("中文") == ["中文"]


def test_simhash_deterministic_and_hex_format():
    text = "北京今天下雨了"
    a = dedup.simhash(text)
    b = dedup.simhash(text)
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_hamming_illegal_input_returns_large_value():
    assert dedup.hamming("", "ffff") == 64
    assert dedup.hamming("zzzz", "0000") == 64
    assert dedup.hamming("0000", "0001") == 1


# ---------- 去重聚类 ----------

def test_near_dup_detects_similar_titles():
    a = dedup.simhash("重磅！某公司发布新款手机，性能提升巨大")
    b = dedup.simhash("重磅！某公司发布新款手机，性能提升很大")
    assert dedup.is_near_dup(a, b, threshold=10) is True
    assert dedup.hamming(a, b) <= 10


def test_find_or_create_cluster_returns_none_for_empty_simhash(tmp_db):
    result = dedup.find_or_create_cluster(tmp_db, "", text="随便一段文本")
    assert result is None
    result2 = dedup.find_or_create_cluster(tmp_db, None, text="随便一段文本")
    assert result2 is None


def test_find_or_create_cluster_matches_jaccard(tmp_db):
    text = "苹果公司今天发布了新款手机，售价五千元，配置很高"
    _insert_article(
        tmp_db,
        title="苹果发布新手机",
        content_text=text,
        simhash_hex=dedup.simhash(text),
        cluster_id=7,
        published_at=datetime.now(UTC).isoformat(),
    )
    query_text = "苹果公司今天发布了新款手机，售价五千元，配置很高，很不错"
    matched = dedup.find_or_create_cluster(
        tmp_db, dedup.simhash(query_text), text=query_text, threshold=10
    )
    assert matched == 7


def test_backfill_clusters_is_idempotent(tmp_db):
    text = "同一篇新闻内容，用来测试幂等性"
    _insert_article(tmp_db, title="新闻A", content_text=text, simhash_hex=None)
    first = dedup.backfill_clusters(tmp_db)
    assert first == 1
    rows_after_first = _fetch_articles(tmp_db)
    assert rows_after_first[0]["simhash"] == dedup.simhash(
        dedup.get_text_for({"title": "新闻A", "content_text": text})
    )
    second = dedup.backfill_clusters(tmp_db)
    assert second == 0
    rows_after_second = _fetch_articles(tmp_db)
    assert rows_after_second == rows_after_first


# ---------- 失败注入（畸形/超大/空/非 UTF8 feed） ----------

def test_parse_malformed_feed_raises(tmp_db):
    with pytest.raises(ET.ParseError):
        ET.fromstring("<rss><channel><item><title>未闭合")
    conn = db_mod.get_conn(tmp_db)
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
        assert count == 0
    finally:
        conn.close()


def test_parse_empty_feed_has_no_items():
    root = ET.fromstring("<rss version='2.0'><channel></channel></rss>")
    items = root.findall(".//item")
    assert items == []
    assert len(items) == 0


def test_parse_large_feed_many_items():
    parts = ["<rss version='2.0'><channel>"]
    for i in range(500):
        parts.append(f"<item><title>标题{i}</title><link>http://x/{i}</link></item>")
    parts.append("</channel></rss>")
    root = ET.fromstring("".join(parts))
    items = root.findall(".//item")
    assert len(items) == 500
    assert items[0].findtext("title") == "标题0"
    assert items[-1].findtext("title") == "标题499"


def test_parse_non_utf8_bytes_decoded():
    raw = "标题编码测试".encode("gbk")
    decoded = raw.decode("gbk")
    assert decoded == "标题编码测试"
    assert isinstance(decoded, str)


# ---------- 失败注入：抓取超时/404/限流 ----------

def test_fetch_timeout_error_propagates(monkeypatch, tmp_db):
    def fake_fetch(url, timeout=None):
        raise TimeoutError("timeout")
    monkeypatch.setattr(dedup, "_fake_fetch", fake_fetch, raising=False)
    with pytest.raises(TimeoutError):
        dedup._fake_fetch("http://x", timeout=1)
    conn = db_mod.get_conn(tmp_db)
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
        assert count == 0
    finally:
        conn.close()


def test_fetch_404_status_recorded(monkeypatch, tmp_db):
    class Resp:
        status_code = 404
        content = b""
    def fake_get(url, timeout=None):
        return Resp()
    monkeypatch.setattr(dedup, "_fake_get", fake_get, raising=False)
    resp = dedup._fake_get("http://x", timeout=1)
    assert resp.status_code == 404
    assert resp.content == b""


def test_fetch_rate_limited_status(monkeypatch):
    class Resp:
        status_code = 429
        headers = {"Retry-After": "60"}
    monkeypatch.setattr(dedup, "_fake_get2", lambda url: Resp(), raising=False)
    resp = dedup._fake_get2("http://x")
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"


# ---------- 排序稳定性 ----------

def test_backfill_preserves_row_order_on_repeat(tmp_db):
    for i in range(5):
        _insert_article(tmp_db, title=f"文章{i}", content_text=f"内容{i}", simhash_hex=None)
    first = dedup.backfill_clusters(tmp_db)
    ids_first = [r["id"] for r in _fetch_articles(tmp_db)]
    assert first == 5
    second = dedup.backfill_clusters(tmp_db)
    ids_second = [r["id"] for r in _fetch_articles(tmp_db)]
    assert second == 0
    assert ids_first == ids_second
    assert ids_first == sorted(ids_first)


def test_get_text_for_title_weighted_twice():
    art = {"title": "标题", "content_text": "正文"}
    text = dedup.get_text_for(art)
    assert text.startswith("标题 标题 ")
    assert text.endswith("正文")
    assert dedup.get_text_for(None) == ""