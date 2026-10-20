"""Tests for feedflow dedup and ranking modules."""
from datetime import UTC, datetime, timedelta

import pytest

from feedflow import dedup, db as db_mod
from feedflow.ranking import score_article, rank_articles, get_digest

def _insert_feed(db_path, title="Test Feed", feed_url=None):
    if feed_url is None:
        feed_url = f"http://example.com/feed/{title}"
    now = db_mod.utcnow()
    db_mod.execute_write(
        db_path,
        """
        INSERT INTO feeds (title, site_url, feed_url, description, interval_min, enabled, etag, modified, position, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, "http://example.com", feed_url, "", 60, 1, None, None, 0, now),
    )
    row = db_mod.query_one(db_path, "SELECT id FROM feeds WHERE feed_url = ?", (feed_url,))
    return int(row["id"])

def _insert_article(db_path, feed_id, guid, title, content, published_at=None, fetched_at=None, is_read=0, is_starred=0):
    db_mod.execute_write(
        db_path,
        """
        INSERT INTO articles (feed_id, guid, title, content_text, published_at, fetched_at, is_read, is_starred)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (feed_id, guid, title, content, published_at, fetched_at, is_read, is_starred),
    )
    row = db_mod.query_one(db_path, "SELECT id FROM articles WHERE feed_id = ? AND guid = ?", (feed_id, guid))
    return int(row["id"])

def test_wlfl_tokenize_basic():
    assert dedup.tokenize("") == []
    assert dedup.tokenize(None) == []
    assert dedup.tokenize("Hello World 123") == ["hello", "world", "123"]
    assert dedup.tokenize("中文测试") == ["中文", "文测", "试测"]
    assert dedup.tokenize("中") == ["中"]
    assert dedup.tokenize("ＡＢＣ") == ["abc"]

def test_wlfl_simhash_deterministic():
    text = "这是一篇测试文章，用于验证 SimHash 的确定性。"
    sh1 = dedup.simhash(text)
    sh2 = dedup.simhash(text)
    assert sh1 == sh2
    assert len(sh1) == 16
    
    text2 = "这是一篇测试文章，用于验证 SimHash 的确定性！"
    sh3 = dedup.simhash(text2)
    assert dedup.hamming(sh1, sh3) > 0

def test_wlfl_hamming_invalid():
    assert dedup.hamming("", "abc") == 64
    assert dedup.hamming(None, "abc") == 64
    assert dedup.hamming("zzzz", "abc") == 64
    assert dedup.hamming("abc", "") == 64

def test_wlfl_is_near_dup_threshold():
    a = "0" * 16
    b = "0" * 15 + "7"
    c = "0" * 15 + "f"
    assert dedup.hamming(a, b) == 3
    assert dedup.is_near_dup(a, b, 3) is True
    assert dedup.hamming(a, c) == 4
    assert dedup.is_near_dup(a, c, 3) is False

def test_wlfl_exact_duplicate_cluster(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed A")
    title = "完全相同的标题"
    content = "完全相同的正文内容，用于测试精确去重。"
    
    aid1 = _insert_article(tmp_db, feed_id, "guid-1", title, content)
    # backfill first article to create its cluster
    dedup.backfill_clusters(tmp_db)
    
    # verify article 1 has cluster_id = its own id
    row1 = db_mod.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (aid1,))
    assert row1["cluster_id"] == aid1
    
    # insert second identical article
    aid2 = _insert_article(tmp_db, feed_id, "guid-2", title, content)
    
    text = dedup.get_text_for({"title": title, "content_text": content})
    sh = dedup.simhash(text)
    cluster_id = dedup.find_or_create_cluster(tmp_db, sh, text)
    assert cluster_id == aid1

def test_wlfl_similar_article_cluster(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed B")
    title = "相似文章标题"
    content1 = "这是第一篇文章的正文，内容比较相似。"
    content2 = "这是第一篇文章的正文，内容比较相似！"  # differs by one char
    
    aid1 = _insert_article(tmp_db, feed_id, "guid-sim-1", title, content1)
    dedup.backfill_clusters(tmp_db)
    
    aid2 = _insert_article(tmp_db, feed_id, "guid-sim-2", title, content2)
    text2 = dedup.get_text_for({"title": title, "content_text": content2})
    sh2 = dedup.simhash(text2)
    cluster_id = dedup.find_or_create_cluster(tmp_db, sh2, text2)
    assert cluster_id == aid1
    
    # completely different topic
    title3 = "完全不同的主题"
    content3 = "关于量子计算和宇宙起源的深度讨论。"
    aid3 = _insert_article(tmp_db, feed_id, "guid-sim-3", title3, content3)
    text3 = dedup.get_text_for({"title": title3, "content_text": content3})
    sh3 = dedup.simhash(text3)
    cluster_id3 = dedup.find_or_create_cluster(tmp_db, sh3, text3)
    assert cluster_id3 is None

def test_wlfl_backfill_idempotent(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed C")
    title = "幂等测试标题"
    content1 = "这是幂等测试的第一篇正文内容。"
    content2 = "这是幂等测试的第一篇正文内容！"
    
    _insert_article(tmp_db, feed_id, "guid-idem-1", title, content1)
    _insert_article(tmp_db, feed_id, "guid-idem-2", title, content2)
    
    processed = dedup.backfill_clusters(tmp_db)
    assert processed == 2
    
    rows = db_mod.query_all(tmp_db, "SELECT id, cluster_id FROM articles ORDER BY id ASC")
    assert rows[0]["cluster_id"] == rows[1]["cluster_id"]
    
    processed2 = dedup.backfill_clusters(tmp_db)
    assert processed2 == 0

def test_wlfl_14day_window(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed D")
    title = "窗口测试标题"
    content = "这是窗口测试的正文内容。"
    
    old_date = (datetime.now(UTC) - timedelta(days=20)).isoformat()
    aid_old = _insert_article(tmp_db, feed_id, "guid-old", title, content, published_at=old_date)
    
    # set simhash and cluster_id for old article
    text = dedup.get_text_for({"title": title, "content_text": content})
    sh = dedup.simhash(text)
    db_mod.execute_write(tmp_db, "UPDATE articles SET simhash = ?, cluster_id = ? WHERE id = ?", (sh, aid_old, aid_old))
    
    # new similar article
    aid_new = _insert_article(tmp_db, feed_id, "guid-new", title, content)
    text_new = dedup.get_text_for({"title": title, "content_text": content})
    sh_new = dedup.simhash(text_new)
    cluster_id = dedup.find_or_create_cluster(tmp_db, sh_new, text_new)
    assert cluster_id is None

def test_wlfl_empty_inputs(tmp_db):
    assert dedup.tokenize("") == []
    assert rank_articles(tmp_db, []) == []
    assert get_digest(tmp_db, n=0) == []

def test_wlfl_sort_stability(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed E")
    # insert several articles with different published_at
    base = datetime.now(UTC)
    for i in range(5):
        pub = (base - timedelta(hours=i)).isoformat()
        _insert_article(tmp_db, feed_id, f"guid-sort-{i}", f"Title {i}", f"Content {i}", published_at=pub)
    
    rows = db_mod.query_all(tmp_db, "SELECT * FROM articles ORDER BY id ASC")
    articles = [dict(r) for r in rows]
    
    ranked1 = rank_articles(tmp_db, articles)
    ranked2 = rank_articles(tmp_db, articles)
    
    assert [a["id"] for a in ranked1] == [a["id"] for a in ranked2]
    
    scores = [a["score_info"]["score"] for a in ranked1]
    assert scores == sorted(scores, reverse=True)

def test_wlfl_score_article_formula():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    article = {
        "published_at": "2026-10-18T12:00:00+00:00",
        "title": "AI 技术的最新进展",
        "content_text": "人工智能正在改变世界。",
        "is_read": 1,
    }
    keywords = [{"keyword": "AI", "weight": 1.0}]
    
    info = score_article(article, now=now, cluster_size=8, feed_weight=1.0, learned=1.0, keywords=keywords)
    
    assert abs(info["parts"]["recency"] - 0.5) < 1e-9
    assert info["parts"]["heat"] == 1.0
    assert info["parts"]["keyword"] == 0.5
    assert info["parts"]["unread"] == 0.0
    
    # cluster_size=1 → heat=0.0
    info2 = score_article(article, now=now, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=keywords)
    assert info2["parts"]["heat"] == 0.0

def test_wlfl_reasons():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    article = {
        "published_at": now.isoformat(),
        "title": "刚刚发布的文章",
        "content_text": "内容",
        "is_read": 0,
    }
    info = score_article(article, now=now, cluster_size=3, feed_weight=1.0, learned=1.0, keywords=[])
    assert "刚刚发布" in info["reasons"]
    assert "同事件 3 篇在跟" in info["reasons"]

def test_wlfl_keyword_cap():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    article = {
        "published_at": now.isoformat(),
        "title": "AI ML DL 技术",
        "content_text": "内容",
        "is_read": 0,
    }
    keywords = [
        {"keyword": "AI", "weight": 1.0},
        {"keyword": "ML", "weight": 1.0},
        {"keyword": "DL", "weight": 1.0},
    ]
    info = score_article(article, now=now, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=keywords)
    assert info["parts"]["keyword"] == 1.0

def test_wlfl_get_digest_unread_only(tmp_db):
    feed_id = _insert_feed(tmp_db, "Feed F")
    _insert_article(tmp_db, feed_id, "guid-read", "已读文章", "内容", is_read=1)
    _insert_article(tmp_db, feed_id, "guid-unread", "未读文章", "内容", is_read=0)
    
    digest = get_digest(tmp_db, n=10)
    assert len(digest) == 1
    assert digest[0]["title"] == "未读文章"
