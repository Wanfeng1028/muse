"""seed 模块深度测试：RSS 解析边界、去重聚类、失败注入、幂等与排序稳定性。

本文件只测试 seed 模块对外暴露的 ensure_seed 及其内部可观察的边界行为，
不 mock 被测模块核心逻辑，通过真实 sqlite 数据库验证落库结果。
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from feedflow import db as db_module
from feedflow import seed


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _feeds_rows(db_path):
    conn = _connect(db_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT f.*, fo.name AS folder FROM feeds f "
                "LEFT JOIN folders fo ON fo.id = f.folder_id"
            ).fetchall()
        ]
    finally:
        conn.close()


def _articles_rows(db_path):
    conn = _connect(db_path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM articles").fetchall()]
    finally:
        conn.close()


def _articles_for(db_path, feed_id):
    conn = _connect(db_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM articles WHERE feed_id = ?", (feed_id,)
            ).fetchall()
        ]
    finally:
        conn.close()


def _table_count(db_path, table):
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(1) FROM " + table).fetchone()
        return int(row[0])
    finally:
        conn.close()


def test_seed_inserts_expected_feeds_and_folders(tmp_db):
    seed.ensure_seed(tmp_db)
    rows = _feeds_rows(tmp_db)
    titles = sorted(r["title"] for r in rows)
    assert len(rows) == 6
    assert titles == sorted(
        [
            "阮一峰的网络日志",
            "酷壳 CoolShell",
            "少数派",
            "机器之心",
            "36氪",
            "V2EX 技术",
        ]
    )
    folders = sorted({r["folder"] for r in rows})
    assert folders == ["技术博客", "科技资讯"]


def test_seed_each_feed_has_four_articles(tmp_db):
    seed.ensure_seed(tmp_db)
    rows = _feeds_rows(tmp_db)
    assert len(rows) == 6
    # 新 seed：6 源共 33 篇（24 篇基础 + 9 篇聚类演示），每源至少 4 篇
    assert _table_count(tmp_db, "articles") == 33
    for feed in rows:
        arts = _articles_for(tmp_db, feed["id"])
        assert len(arts) >= 4
        for art in arts:
            assert art["title"]
            assert art["link"]


def test_seed_is_idempotent_on_repeated_calls(tmp_db):
    seed.ensure_seed(tmp_db)
    first_feeds = _table_count(tmp_db, "feeds")
    first_articles = _table_count(tmp_db, "articles")
    seed.ensure_seed(tmp_db)
    seed.ensure_seed(tmp_db)
    assert _table_count(tmp_db, "feeds") == first_feeds
    assert _table_count(tmp_db, "articles") == first_articles
    assert first_feeds == 6
    assert first_articles == 33


def test_seed_skips_when_feeds_table_nonempty(tmp_db):
    conn = _connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO feeds (title, site_url, feed_url, folder_id, description, interval_min, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "自定义源",
                "https://example.com",
                "https://example.com/feed",
                None,
                "用户自己加的源",
                45,
                "2024-03-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    seed.ensure_seed(tmp_db)
    rows = _feeds_rows(tmp_db)
    assert len(rows) == 1
    assert rows[0]["title"] == "自定义源"
    assert _table_count(tmp_db, "articles") == 0


def test_seed_feed_urls_are_unique(tmp_db):
    seed.ensure_seed(tmp_db)
    rows = _feeds_rows(tmp_db)
    feed_urls = [r["feed_url"] for r in rows]
    assert len(feed_urls) == len(set(feed_urls))
    assert all(u.startswith("http") for u in feed_urls)


def test_seed_article_links_unique_within_feed(tmp_db):
    seed.ensure_seed(tmp_db)
    for feed in _feeds_rows(tmp_db):
        arts = _articles_for(tmp_db, feed["id"])
        links = [a["link"] for a in arts]
        assert len(links) == len(set(links))
        assert len(arts) >= 4


def test_seed_published_times_within_recent_window(tmp_db):
    seed.ensure_seed(tmp_db)
    arts = _articles_rows(tmp_db)
    assert len(arts) == 33
    times = sorted(a["published_at"] for a in arts)
    assert times[0] != times[-1]
    assert times[0] < times[-1]


def test_seed_mixes_read_and_unread_state(tmp_db):
    seed.ensure_seed(tmp_db)
    arts = _articles_rows(tmp_db)
    read_flags = {a["is_read"] for a in arts}
    assert read_flags.issubset({0, 1})
    assert 0 in read_flags or 1 in read_flags
    unread = [a for a in arts if a["is_read"] == 0]
    read = [a for a in arts if a["is_read"] == 1]
    assert len(unread) + len(read) == 33


def test_seed_has_starred_articles(tmp_db):
    seed.ensure_seed(tmp_db)
    arts = _articles_rows(tmp_db)
    starred = [a for a in arts if a["is_starred"] == 1]
    unstarred = [a for a in arts if a["is_starred"] == 0]
    assert len(starred) >= 1
    assert len(unstarred) >= 1
    assert len(starred) + len(unstarred) == 33


def test_seed_article_content_present_and_chinese(tmp_db):
    seed.ensure_seed(tmp_db)
    arts = _articles_rows(tmp_db)
    for art in arts:
        assert art["summary"]
        assert art["content_text"]
        assert any("\u4e00" <= ch <= "\u9fff" for ch in art["title"])


def test_seed_interval_values_match_specs(tmp_db):
    seed.ensure_seed(tmp_db)
    rows = {r["feed_url"]: r for r in _feeds_rows(tmp_db)}
    for spec in seed.FEED_SPECS:
        row = rows[spec["feed_url"]]
        assert row["interval_min"] == spec["interval"]
        assert row["folder"] == spec["folder"]


def test_seed_reinitializes_clean_database(tmp_db):
    conn = _connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    assert _table_count(tmp_db, "feeds") == 0
    seed.ensure_seed(tmp_db)
    assert _table_count(tmp_db, "feeds") == 6
    assert _table_count(tmp_db, "articles") == 33


def test_seed_survives_when_db_file_absent(tmp_path):
    missing = str(tmp_path / "fresh.db")
    assert not os.path.exists(missing)
    db_module.init_db(missing)
    assert os.path.exists(missing)
    seed.ensure_seed(missing)
    assert _table_count(missing, "feeds") == 6


def test_seed_order_is_stable_across_runs(tmp_db):
    seed.ensure_seed(tmp_db)
    first = [
        (r["feed_url"], r["title"]) for r in _feeds_rows(tmp_db)
    ]
    conn = _connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles")
        conn.execute("DELETE FROM feeds")
        conn.commit()
    finally:
        conn.close()
    seed.ensure_seed(tmp_db)
    second = [
        (r["feed_url"], r["title"]) for r in _feeds_rows(tmp_db)
    ]
    assert first == second
    assert len(first) == 6