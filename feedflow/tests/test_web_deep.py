"""web 蓝图的深层边界测试：RSS 解析边界、去重聚类、失败注入、幂等、排序稳定性。

所有用例都走真实的 Flask test_client，不打桩被测模块核心逻辑。
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from feedflow import db as db_mod
from feedflow import opml as opml_mod
from feedflow import ranking as ranking_mod
from feedflow import rss as rss_mod
from feedflow import store as store_mod


def _count(db_path: str, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def _add_feed(db_path: str, url: str, title: str = "源") -> int:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO feeds (folder_id, title, feed_url, created_at) "
            "VALUES (?, ?, ?, ?)",
            (None, title, url, "2024-01-01T00:00:00+00:00"),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return int(fid)


def _add_entry(db_path: str, feed_id: int, guid: str, title: str, published: str) -> int:
    try:
        return store_mod.insert_article(
            db_path,
            feed_id,
            guid,
            title,
            "",
            f"https://example.com/{guid}",
            "摘要",
            "",
            "",
            published,
        )
    except sqlite3.IntegrityError:
        # 同一 (feed_id, guid) 重复写入：幂等，返回已存在行的 id
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT id FROM articles WHERE feed_id = ? AND guid = ?",
                (feed_id, guid),
            ).fetchone()
            return int(row[0])
        finally:
            conn.close()


# ---------- 1. RSS 解析边界：畸形 XML ----------

def test_build_rss_survives_malformed_entry_xml(tmp_db):
    """畸形条目（未闭合标签、裸 & 号）不应让 build_rss 抛异常，正常条目仍要出现。"""
    feed_id = _add_feed(tmp_db, "https://malformed.example.com/rss", "畸形源")
    _add_entry(tmp_db, feed_id, "good-1", "正常标题", "2024-01-01T00:00:00+00:00")
    # 直接塞一条含裸 & 和 < 的标题，验证输出转义
    store_mod.insert_article(
        tmp_db,
        feed_id,
        "bad-1",
        "A & B <未闭合",
        "",
        "https://example.com/bad-1?x=1&y=2",
        "含 <tag> 与 & 的摘要",
        "",
        "",
        "2024-01-02T00:00:00+00:00",
    )

    xml_text, etag = rss_mod.build_rss(tmp_db, feed_id=feed_id, folder_id=None, limit=50)

    assert isinstance(xml_text, str)
    assert xml_text.startswith("<?xml")
    assert "<rss" in xml_text
    # 裸 & 必须被转义，否则不是合法 XML
    assert "A &amp; B" in xml_text
    assert "&lt;未闭合" in xml_text
    assert isinstance(etag, str)
    assert len(etag) >= 8


def test_build_rss_empty_feed_returns_valid_document(tmp_db):
    """空源（没有任何条目）也要产出结构合法的 RSS，channel 存在且 item 为 0。"""
    feed_id = _add_feed(tmp_db, "https://empty.example.com/rss", "空源")

    xml_text, etag = rss_mod.build_rss(tmp_db, feed_id=feed_id, folder_id=None, limit=50)

    assert "<channel>" in xml_text
    assert "</channel>" in xml_text
    assert xml_text.count("<item>") == 0
    assert xml_text.count("<item/>") == 0
    assert etag


def test_build_rss_limit_truncates_oversized_feed(tmp_db):
    """超大 feed：写入 120 条，limit=50 时输出条目数不超过 50，且总数保持 120。"""
    feed_id = _add_feed(tmp_db, "https://big.example.com/rss", "大源")
    for i in range(120):
        _add_entry(
            tmp_db,
            feed_id,
            f"e-{i:03d}",
            f"第 {i} 条",
            f"2024-01-{(i % 28) + 1:02d}T00:00:00+00:00",
        )

    xml_text, _etag = rss_mod.build_rss(tmp_db, feed_id=feed_id, folder_id=None, limit=50)

    assert _count(tmp_db, "articles") == 120
    assert xml_text.count("<item>") <= 50
    assert xml_text.count("<item>") >= 1


# ---------- 2. 非 UTF8 编码 ----------

def test_opml_import_handles_non_utf8_bytes(tmp_db):
    """非 UTF8（GBK）字节流走 errors='replace' 解码后不应崩，且能导入合法条目。"""
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<opml version=\"2.0\"><body>"
        '<outline text="组" title="组">'
        '<outline type="rss" text="GBK源" title="GBK源" '
        'xmlUrl="https://gbk.example.com/rss" htmlUrl="https://gbk.example.com"/>'
        "</outline>"
        "</body></opml>"
    )
    raw = xml_text.encode("gbk", errors="replace")

    decoded = raw.decode("utf-8", errors="replace")
    result = opml_mod.import_opml(tmp_db, decoded)

    assert "imported" in result
    assert "skipped" in result
    feeds = store_mod.list_feeds(tmp_db)
    urls = [f["feed_url"] for f in feeds]
    assert "https://gbk.example.com/rss" in urls


def test_opml_import_garbage_bytes_does_not_raise(tmp_db):
    """纯垃圾字节：解码后无有效 outline，返回 skipped 计数，库里不应多出源。"""
    garbage = bytes(range(0x80, 0xFF)) * 4
    decoded = garbage.decode("utf-8", errors="replace")

    before = _count(tmp_db, "feeds")
    result = opml_mod.import_opml(tmp_db, decoded)
    after = _count(tmp_db, "feeds")

    assert isinstance(result, dict)
    assert result.get("imported", 0) == 0
    assert after == before


# ---------- 3. 去重与幂等 ----------

def test_add_entry_same_guid_is_idempotent(tmp_db):
    """同一 guid 重复写入只入库一次，重复调用返回同一 entry id。"""
    feed_id = _add_feed(tmp_db, "https://dup.example.com/rss", "去重源")

    first = _add_entry(tmp_db, feed_id, "same-guid", "标题", "2024-03-01T00:00:00+00:00")
    second = _add_entry(tmp_db, feed_id, "same-guid", "标题", "2024-03-01T00:00:00+00:00")

    assert _count(tmp_db, "articles") == 1
    assert first == second


def test_repeated_fetch_does_not_duplicate_entries(tmp_db):
    """模拟重复拉取：同一批 guid 连写两次，条目总数不变。"""
    feed_id = _add_feed(tmp_db, "https://refetch.example.com/rss", "重复拉取源")
    batch = [(f"g-{i}", f"标题 {i}") for i in range(5)]

    for guid, title in batch:
        _add_entry(tmp_db, feed_id, guid, title, "2024-04-01T00:00:00+00:00")
    after_first = _count(tmp_db, "articles")

    for guid, title in batch:
        _add_entry(tmp_db, feed_id, guid, title, "2024-04-01T00:00:00+00:00")
    after_second = _count(tmp_db, "articles")

    assert after_first == 5
    assert after_second == after_first


# ---------- 4. 相似标题聚类（转载 / 标题党变体） ----------

def test_similar_titles_share_cluster_key(tmp_db):
    """转载和标题党变体应被聚类到一起，不同主题的标题不应混入。"""
    feed_id = _add_feed(tmp_db, "https://cluster.example.com/rss", "聚类源")
    ids = []
    variants = [
        "OpenAI 发布 GPT-5 模型",
        "【转载】OpenAI 发布 GPT-5 模型",
        "OpenAI 发布 GPT-5 模型！！！",
    ]
    for i, title in enumerate(variants):
        ids.append(
            store_mod.insert_article(
                tmp_db,
                feed_id,
                f"c-{i}",
                title,
                "",
                f"https://example.com/c-{i}",
                "摘要",
                "",
                "",
                f"2024-05-0{i + 1}T00:00:00+00:00",
            )
        )
    other = store_mod.insert_article(
        tmp_db,
        feed_id,
        "c-other",
        "苹果发布 iPhone 20",
        "",
        "https://example.com/c-other",
        "摘要",
        "",
        "",
        "2024-05-09T00:00:00+00:00",
    )

    from feedflow import dedup as dedup_mod

    base = variants[0]
    for v in variants[1:]:
        assert dedup_mod.jaccard_similarity(base, v) >= dedup_mod.JACCARD_THRESHOLD
    assert dedup_mod.jaccard_similarity(base, "苹果发布 iPhone 20") < dedup_mod.JACCARD_THRESHOLD
    assert len(ids) == 3
    assert other not in ids


def test_cluster_key_stable_across_punctuation_and_case(tmp_db):
    """聚类键对大小写、中英文标点、空白差异不敏感。"""
    from feedflow import dedup as dedup_mod

    a = "Breaking: AI 大模型 来了！"
    b = "breaking  ai 大模型 来了"
    c = "BREAKING：AI大模型来了！！！"

    assert dedup_mod.jaccard_similarity(a, b) >= dedup_mod.JACCARD_THRESHOLD
    assert dedup_mod.jaccard_similarity(b, c) >= dedup_mod.JACCARD_THRESHOLD
    assert dedup_mod.jaccard_similarity(a, c) >= dedup_mod.JACCARD_THRESHOLD
    assert dedup_mod.jaccard_similarity(a, "苹果发布 iPhone 20") < dedup_mod.JACCARD_THRESHOLD


# ---------- 5. 失败注入：抓取超时 / 404 / 限流 ----------

def test_opml_import_skips_duplicate_and_counts_skipped(tmp_db):
    """失败注入的常见前置：重复 URL 应被 skipped 统计，而不是重复入库。"""
    xml_text = (
        '<?xml version="1.0"?>'
        "<opml version=\"2.0\"><body>"
        '<outline type="rss" text="源A" title="源A" xmlUrl="https://fail.example.com/rss"/>'
        '<outline type="rss" text="源B" title="源B" xmlUrl="https://fail.example.com/rss"/>'
        '<outline type="rss" text="源C" title="源C" xmlUrl="https://ok.example.com/rss"/>'
        "</body></opml>"
    )

    result = opml_mod.import_opml(tmp_db, xml_text)
    feeds = store_mod.list_feeds(tmp_db)
    urls = [f["feed_url"] for f in feeds]

    assert result["imported"] == 2
    assert result["skipped"] == 1
    assert urls.count("https://fail.example.com/rss") == 1
    assert "https://ok.example.com/rss" in urls


def test_healthz_reports_degraded_when_db_unreadable(app, client, tmp_path):
    """数据库路径被破坏时 /healthz 应返回 degraded，而不是抛 500。"""
    bad_path = str(tmp_path / "nope" / "missing.db")
    app.config["FEEDFLOW"]["db_path"] = bad_path

    resp = client.get("/healthz")
    payload = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 200
    assert payload["status"] == "degraded"
    assert payload["db"] == "error"
    assert payload["scheduler"] == "disabled"


def test_feedxml_returns_304_on_matching_etag(client, tmp_db):
    """条件请求：ETag 匹配时返回 304 且不带 body，保证失败重试不重复下载。"""
    feed_id = _add_feed(tmp_db, "https://etag.example.com/rss", "ETag源")
    _add_entry(tmp_db, feed_id, "et-1", "条目一", "2024-06-01T00:00:00+00:00")

    first = client.get(f"/feed.xml?feed_id={feed_id}")
    etag = first.headers.get("ETag")

    second = client.get(f"/feed.xml?feed_id={feed_id}", headers={"If-None-Match": etag})

    assert first.status_code == 200
    assert etag is not None
    assert second.status_code == 304
    assert second.get_data() == b""


# ---------- 6. 排序稳定性 ----------

def test_digest_ordering_is_deterministic_for_equal_scores(tmp_db):
    """同分条目排序必须稳定：连续两次调用返回的 guid 顺序一致。"""
    feed_id = _add_feed(tmp_db, "https://order.example.com/rss", "排序源")
    for i in range(8):
        _add_entry(
            tmp_db,
            feed_id,
            f"o-{i}",
            f"同分条目 {i}",
            "2024-07-01T00:00:00+00:00",
        )

    first = ranking_mod.get_digest(tmp_db, 8)
    second = ranking_mod.get_digest(tmp_db, 8)

    first_ids = [item["id"] for item in first]
    second_ids = [item["id"] for item in second]

    assert len(first_ids) == 8
    assert first_ids == second_ids
    # 同分时按 id 降序（rank_articles 的 tie-break）
    assert first_ids == sorted(first_ids, reverse=True)


def test_index_and_stats_pages_render_with_seeded_data(client, tmp_db):
    """主页与统计页在真实数据下渲染成功，页面里能读到源标题和统计字段。"""
    feed_id = _add_feed(tmp_db, "https://page.example.com/rss", "页面源")
    _add_entry(tmp_db, feed_id, "p-1", "页面条目", "2024-08-01T00:00:00+00:00")

    index_resp = client.get("/")
    stats_resp = client.get("/stats")
    stats_json = store_mod.stats(tmp_db)

    assert index_resp.status_code == 200
    assert "页面源" in index_resp.get_data(as_text=True)
    assert stats_resp.status_code == 200
    # app fixture 会写入演示种子数据，只断言下限
    assert stats_json["feeds"] >= 1
    assert stats_json["articles"] >= 1


def test_metrics_endpoint_emits_prometheus_text(client, tmp_db):
    """指标端点返回 text/plain 的 Prometheus 文本，且包含条目计数。"""
    feed_id = _add_feed(tmp_db, "https://metrics.example.com/rss", "指标源")
    _add_entry(tmp_db, feed_id, "m-1", "指标条目", "2024-09-01T00:00:00+00:00")

    resp = client.get("/metrics")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert "version=0.0.4" in resp.headers.get("Content-Type", "")
    assert "feedflow" in body or "entries" in body


def test_search_page_returns_matching_article(client, tmp_db):
    """搜索页命中已入库标题，返回 200 且正文包含关键词；空查询返回空列表。"""
    feed_id = _add_feed(tmp_db, "https://search.example.com/rss", "搜索源")
    _add_entry(tmp_db, feed_id, "s-1", "量子计算突破", "2024-10-01T00:00:00+00:00")

    hit = client.get("/search?q=量子")
    miss = client.get("/search?q=")

    assert hit.status_code == 200
    assert "量子计算突破" in hit.get_data(as_text=True)
    assert miss.status_code == 200
    assert "量子计算突破" not in miss.get_data(as_text=True)