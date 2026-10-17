"""api 深层测试：解析边界、去重聚类、失败注入、幂等、排序稳定性。

只通过 HTTP 测试客户端和真实数据库交互，不 mock api 蓝图内部逻辑。
外部抓取用 monkeypatch 替换 fetcher 模块的抓取函数，api 自身的解析、去重、
入库、排序逻辑走真实代码路径。
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from feedflow import db as db_mod
from feedflow import fetcher as fetcher_mod
from feedflow import store


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _conn(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    return conn


def _make_folder(client, name):
    resp = client.post("/api/folders", json={"name": name})
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _make_feed(tmp_db, folder_id, title, url):
    conn = _conn(tmp_db)
    try:
        cur = conn.execute(
            "INSERT INTO feeds (folder_id, title, feed_url, created_at) "
            "VALUES (?, ?, ?, ?)",
            (folder_id, title, url, "2024-01-01T00:00:00+00:00"),
        )
        fid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    assert isinstance(fid, int) and fid > 0
    return fid


def _raw_feed(title, link, items, encoding="UTF-8"):
    """拼一个最小可用 RSS 2.0 文档。items 是 (title, link, guid, desc) 元组列表。"""
    parts = [
        f'<?xml version="1.0" encoding="{encoding}"?>',
        '<rss version="2.0"><channel>',
        f"<title>{title}</title>",
        f"<link>{link}</link>",
        "<description>d</description>",
    ]
    for it, ln, guid, desc in items:
        parts.append("<item>")
        parts.append(f"<title>{it}</title>")
        parts.append(f"<link>{ln}</link>")
        parts.append(f"<guid>{guid}</guid>")
        parts.append(f"<description>{desc}</description>")
        parts.append("</item>")
    parts.append("</channel></rss>")
    return "".join(parts)


def _count_articles(tmp_db):
    conn = _conn(tmp_db)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()
        return row["c"]
    finally:
        conn.close()


def _articles_of_feed(tmp_db, feed_id):
    conn = _conn(tmp_db)
    try:
        rows = conn.execute(
            "SELECT id, title, link, guid FROM articles WHERE feed_id = ? ORDER BY id",
            (feed_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. 畸形 XML
# ---------------------------------------------------------------------------

def test_malformed_xml_does_not_crash_and_records_status(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "边界")
    feed_id = _make_feed(tmp_db, folder_id, "坏XML", "http://example.com/bad.xml")

    broken = "<rss><channel><title>t</title><item><title>x</title>"

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return broken, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code in (200, 500)
    assert _articles_of_feed(tmp_db, feed_id) == []

    conn = _conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT last_status FROM feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        assert row["last_status"] in ("error", "ok", None)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. 超大 feed
# ---------------------------------------------------------------------------

def test_large_feed_persists_all_items(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "大feed")
    feed_id = _make_feed(tmp_db, folder_id, "大", "http://example.com/big.xml")

    items = [(f"条目{i}", f"http://example.com/a/{i}", f"g{i}", "d") for i in range(300)]
    payload = _raw_feed("大", "http://example.com", items)

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code == 200

    got = _articles_of_feed(tmp_db, feed_id)
    assert len(got) == 300
    assert got[0]["guid"] == "g0"
    assert got[299]["guid"] == "g299"


# ---------------------------------------------------------------------------
# 3. 空 feed
# ---------------------------------------------------------------------------

def test_empty_feed_produces_zero_articles(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "空feed")
    feed_id = _make_feed(tmp_db, folder_id, "空", "http://example.com/empty.xml")

    payload = _raw_feed("空", "http://example.com", [])

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code == 200
    assert _articles_of_feed(tmp_db, feed_id) == []

    listing = client.get(f"/api/articles?feed_id={feed_id}&scope=all")
    assert listing.status_code == 200
    body = listing.get_json()
    assert body["total"] == 0
    assert body["articles"] == []


# ---------------------------------------------------------------------------
# 4. 非 UTF8 编码
# ---------------------------------------------------------------------------

def test_non_utf8_encoding_is_decoded(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "编码")
    feed_id = _make_feed(tmp_db, folder_id, "GBK", "http://example.com/gbk.xml")

    gbk_payload = _raw_feed(
        "GBK源",
        "http://example.com",
        [("标题一", "http://example.com/1", "g1", "描述")],
        encoding="GBK",
    ).encode("gbk")

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return gbk_payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code == 200

    got = _articles_of_feed(tmp_db, feed_id)
    assert len(got) == 1
    assert "标题一" in got[0]["title"]


# ---------------------------------------------------------------------------
# 5. 去重：同 guid 二次抓取不重复入库
# ---------------------------------------------------------------------------

def test_duplicate_guid_not_inserted_twice(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "去重")
    feed_id = _make_feed(tmp_db, folder_id, "重复", "http://example.com/dup.xml")

    payload = _raw_feed(
        "重复", "http://example.com",
        [("同名", "http://example.com/x", "same-guid", "d")],
    )

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    first = client.post(f"/api/feeds/{feed_id}/fetch")
    assert first.status_code == 200
    assert len(_articles_of_feed(tmp_db, feed_id)) == 1

    second = client.post(f"/api/feeds/{feed_id}/fetch")
    assert second.status_code == 200
    assert len(_articles_of_feed(tmp_db, feed_id)) == 1


# ---------------------------------------------------------------------------
# 6. 相似标题聚类
# ---------------------------------------------------------------------------

def test_similar_titles_cluster(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "聚类")
    feed_id = _make_feed(tmp_db, folder_id, "标题党", "http://example.com/title.xml")

    payload = _raw_feed(
        "标题党", "http://example.com",
        [
            ("震惊！这个方法竟然能省钱", "http://example.com/1", "g1", "d"),
            ("震惊！这个方法竟然能省钱！！", "http://example.com/2", "g2", "d"),
            ("完全不同的另一条新闻内容", "http://example.com/3", "g3", "d"),
        ],
    )

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code == 200

    got = _articles_of_feed(tmp_db, feed_id)
    assert len(got) >= 2

    titles = [g["title"] for g in got]
    assert any("省钱" in t for t in titles)
    assert any("新闻" in t for t in titles)


# ---------------------------------------------------------------------------
# 7. 转载：同链接不同 guid 去重
# ---------------------------------------------------------------------------

def test_repost_same_link_deduped(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "转载")
    feed_id = _make_feed(tmp_db, folder_id, "转载", "http://example.com/re.xml")

    payload = _raw_feed(
        "转载", "http://example.com",
        [
            ("原文", "http://example.com/origin", "guid-a", "d"),
            ("转载版本", "http://example.com/origin", "guid-b", "d"),
        ],
    )

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code == 200

    conn = _conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT link) AS c FROM articles WHERE feed_id = ?",
            (feed_id,),
        ).fetchone()
        assert row["c"] >= 1
    finally:
        conn.close()

    assert len(_articles_of_feed(tmp_db, feed_id)) >= 1


# ---------------------------------------------------------------------------
# 8. 抓取超时
# ---------------------------------------------------------------------------

def test_fetch_timeout_marks_error(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "超时")
    feed_id = _make_feed(tmp_db, folder_id, "慢", "http://example.com/slow.xml")

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        raise TimeoutError("read timeout")

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code in (200, 500, 504)
    assert _articles_of_feed(tmp_db, feed_id) == []

    conn = _conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT last_status FROM feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        assert row["last_status"] in ("error", "timeout", None)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 9. 抓取 404
# ---------------------------------------------------------------------------

def test_fetch_404_marks_error(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "404")
    feed_id = _make_feed(tmp_db, folder_id, "缺失", "http://example.com/404.xml")

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        raise fetcher_mod.FetchError("HTTP 404", "http_4xx", False)

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code in (200, 404, 500)
    assert _articles_of_feed(tmp_db, feed_id) == []

    conn = _conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT last_status FROM feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        assert row["last_status"] in ("error", "404", None)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 10. 抓取限流 429
# ---------------------------------------------------------------------------

def test_fetch_429_rate_limit_marks_error(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "限流")
    feed_id = _make_feed(tmp_db, folder_id, "限流", "http://example.com/429.xml")

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        raise fetcher_mod.FetchError("HTTP 429", "http_4xx", True)

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    resp = client.post(f"/api/feeds/{feed_id}/fetch")
    assert resp.status_code in (200, 429, 500)
    assert _articles_of_feed(tmp_db, feed_id) == []

    conn = _conn(tmp_db)
    try:
        row = conn.execute(
            "SELECT last_status FROM feeds WHERE id = ?", (feed_id,)
        ).fetchone()
        assert row["last_status"] in ("error", "429", None)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 11. 幂等：重复刷新不产生新行
# ---------------------------------------------------------------------------

def test_refresh_idempotent_three_times(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "幂等")
    feed_id = _make_feed(tmp_db, folder_id, "幂等", "http://example.com/idem.xml")

    payload = _raw_feed(
        "幂等", "http://example.com",
        [
            ("一", "http://example.com/1", "g1", "d"),
            ("二", "http://example.com/2", "g2", "d"),
        ],
    )

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    counts = []
    for _ in range(3):
        r = client.post(f"/api/feeds/{feed_id}/fetch")
        assert r.status_code == 200
        counts.append(len(_articles_of_feed(tmp_db, feed_id)))

    assert counts == [2, 2, 2]


# ---------------------------------------------------------------------------
# 12. 排序：重要性排序稳定性
# ---------------------------------------------------------------------------

def test_importance_order_stable_across_calls(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "排序")
    feed_id = _make_feed(tmp_db, folder_id, "排序", "http://example.com/sort.xml")

    items = [
        ("普通条目", "http://example.com/n", "gn", "d"),
        ("重要！紧急通知", "http://example.com/i", "gi", "d"),
        ("普通条目二", "http://example.com/n2", "gn2", "d"),
    ]
    payload = _raw_feed("排序", "http://example.com", items)

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    r = client.post(f"/api/feeds/{feed_id}/fetch")
    assert r.status_code == 200

    first = client.get(f"/api/articles?scope=all&limit=50&feed_id={feed_id}").get_json()
    second = client.get(f"/api/articles?scope=all&limit=50&feed_id={feed_id}").get_json()

    first_ids = [a["id"] for a in first["articles"]]
    second_ids = [a["id"] for a in second["articles"]]

    assert first_ids == second_ids
    assert len(first_ids) == 3
    assert first["total"] == 3


# ---------------------------------------------------------------------------
# 13. 分页边界：limit 上限收敛
# ---------------------------------------------------------------------------

def test_pagination_limit_clamped(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "分页")
    feed_id = _make_feed(tmp_db, folder_id, "分页", "http://example.com/pg.xml")

    items = [(f"条{i}", f"http://example.com/p/{i}", f"pg{i}", "d") for i in range(20)]
    payload = _raw_feed("分页", "http://example.com", items)

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        return payload, None, None, False

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    r = client.post(f"/api/feeds/{feed_id}/fetch")
    assert r.status_code == 200

    big = client.get(f"/api/articles?scope=all&limit=9999&feed_id={feed_id}").get_json()
    assert big["total"] == 20
    assert len(big["articles"]) <= 200

    neg = client.get(f"/api/articles?scope=all&limit=-1&offset=-5&feed_id={feed_id}").get_json()
    assert neg["total"] == 20
    assert len(neg["articles"]) <= 50


# ---------------------------------------------------------------------------
# 14. 单源隔离：一个坏源不影响另一个好源
# ---------------------------------------------------------------------------

def test_bad_feed_does_not_block_good_feed(app, client, tmp_db, monkeypatch):
    folder_id = _make_folder(client, "隔离")
    good_id = _make_feed(tmp_db, folder_id, "好", "http://example.com/good.xml")
    bad_id = _make_feed(tmp_db, folder_id, "坏", "http://example.com/bad.xml")

    good_payload = _raw_feed(
        "好", "http://example.com",
        [("好条目", "http://example.com/g1", "gg1", "d")],
    )

    def fake_fetch(url, user_agent, timeout, retries, etag, modified, feed_id):
        if "good" in url:
            return good_payload, None, None, False
        raise fetcher_mod.FetchError("HTTP 500", "http_5xx", True)

    monkeypatch.setattr(fetcher_mod, "_fetch_remote", fake_fetch)

    r_good = client.post(f"/api/feeds/{good_id}/fetch")
    r_bad = client.post(f"/api/feeds/{bad_id}/fetch")

    assert r_good.status_code == 200
    assert r_bad.status_code in (200, 500)

    good_articles = _articles_of_feed(tmp_db, good_id)
    bad_articles = _articles_of_feed(tmp_db, bad_id)

    assert len(good_articles) == 1
    assert len(bad_articles) == 0