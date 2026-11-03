from __future__ import annotations

import pytest

from feedflow import db, dedup


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    db.init_db(db_path)
    return db_path


def _make_feed(db_path, url="http://f/x/"):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        ("f", url, db.utcnow()),
    )
    row = db.query_one(db_path, "SELECT id FROM feeds WHERE feed_url = ?", (url,))
    return row["id"]


def _insert(db_path, feed_id, guid, title, content_text, published_at=None):
    db.execute_write(
        db_path,
        "INSERT INTO articles (feed_id, guid, title, author, link, summary, content_html, content_text, published_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            feed_id,
            guid,
            title,
            "author",
            "http://example.com/" + guid,
            "summary",
            "<p>content</p>",
            content_text,
            published_at or db.utcnow(),
            db.utcnow(),
        ),
    )
    row = db.query_one(db_path, "SELECT id FROM articles WHERE guid = ?", (guid,))
    return row["id"]


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


def test_tokenize_empty_and_none():
    assert dedup.tokenize("") == []
    assert dedup.tokenize(None) == []


def test_tokenize_fullwidth_nfkc():
    assert dedup.tokenize("ＡＢＣ１２３") == ["abc123"]


def test_tokenize_single_cjk():
    assert dedup.tokenize("中") == ["中"]


def test_tokenize_mixed_bigrams():
    assert dedup.tokenize("中文abc测试") == ["中文", "abc", "测试"]


def test_tokenize_punctuation_skipped():
    assert dedup.tokenize("hello, world!") == ["hello", "world"]


def test_tokenize_cjk_run_of_three():
    assert dedup.tokenize("中文测试") == ["中文", "文测", "测试"]


# ---------------------------------------------------------------------------
# hashing / simhash
# ---------------------------------------------------------------------------


def test_hash64_deterministic_and_distinct():
    a1 = dedup._hash64("apple")
    a2 = dedup._hash64("apple")
    b = dedup._hash64("banana")
    assert a1 == a2
    assert a1 != b
    assert 0 <= a1 < (1 << 64)


def test_simhash_features_zero_weight_treated_as_1():
    fp_zero = dedup.simhash_features([("x", 0)])
    fp_one = dedup.simhash_features([("x", 1)])
    assert fp_zero == fp_one
    assert len(fp_zero) == 16


def test_simhash_case_and_punct_insensitive():
    assert dedup.simhash("Hello, World") == dedup.simhash("hello world")


def test_simhash_different_texts_differ():
    a = dedup.simhash("苹果发布新手机")
    b = dedup.simhash("今天天气真好适合出门")
    assert a != b


# ---------------------------------------------------------------------------
# hamming / is_near_dup
# ---------------------------------------------------------------------------


def test_hamming_none_invalid_unequal_length():
    assert dedup.hamming(None, "ff") == 64
    assert dedup.hamming("zz", "ff") == 64
    # 文档化行为：不校验长度，按数值异或计汉明距离
    # "ff" -> 255, "ffff" -> 65535, 异或 = 0xff00, bit_count = 8
    assert dedup.hamming("ff", "ffff") == 8


def test_is_near_dup_custom_threshold():
    assert dedup.is_near_dup("ff", "fe", threshold=0) is False
    assert dedup.is_near_dup("ff", "fe", threshold=1) is True


# ---------------------------------------------------------------------------
# get_text_for
# ---------------------------------------------------------------------------


def test_get_text_for_title_weighted():
    result = dedup.get_text_for({"title": "T", "content_text": "C"})
    assert result == "T T C"


# ---------------------------------------------------------------------------
# jaccard
# ---------------------------------------------------------------------------


def test_jaccard_identical_disjoint_partial():
    assert dedup.jaccard_similarity("a b c", "a b c") == 1.0
    assert dedup.jaccard_similarity("a b c", "x y z") == 0.0
    sim = dedup.jaccard_similarity("a b c", "a b d")
    assert abs(sim - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# find_or_create_cluster
# ---------------------------------------------------------------------------


def test_find_or_create_cluster_empty_simhash_none(tmp_db):
    assert dedup.find_or_create_cluster(tmp_db, "") is None
    assert dedup.find_or_create_cluster(tmp_db, None) is None


def test_find_or_create_cluster_joins_near_dup(tmp_db):
    feed_id = _make_feed(tmp_db)
    text_a = (
        "苹果公司今日发布了全新的智能手机产品线，"
        "这款新手机采用了最新的芯片技术，"
        "在性能和续航方面都有显著提升，"
        "同时摄像头系统也进行了全面升级，"
        "受到消费者的广泛关注和期待。"
    )
    id_a = _insert(tmp_db, feed_id, "guid-a", "苹果发布新手机", text_a)
    assert dedup.backfill_clusters(tmp_db) == 1
    row_a = db.query_one(tmp_db, "SELECT cluster_id, simhash FROM articles WHERE id = ?", (id_a,))
    assert row_a["cluster_id"] == id_a

    # B：与 A 高度相似，改几个字
    text_b = (
        "苹果公司今日发布了全新的智能手机产品线，"
        "这款新手机采用了最新的芯片技术，"
        "在性能和续航方面都有显著提升，"
        "同时摄像头系统也进行了全面升级，"
        "受到消费者的广泛关注与期待。"
    )
    simhash_b = dedup.simhash(dedup.get_text_for({"title": "苹果发布新手机", "content_text": text_b}))
    cluster_b = dedup.find_or_create_cluster(tmp_db, simhash_b, text_b)
    assert cluster_b == row_a["cluster_id"]

    # C：完全无关
    text_c = (
        "今天天气晴朗，阳光明媚，"
        "适合出门散步和户外运动，"
        "公园里的花都开了，"
        "许多市民带着家人一起出游，"
        "享受周末的美好时光。"
    )
    simhash_c = dedup.simhash(dedup.get_text_for({"title": "周末天气真好", "content_text": text_c}))
    cluster_c = dedup.find_or_create_cluster(tmp_db, simhash_c, text_c)
    assert cluster_c is None


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


def test_backfill_idempotent(tmp_db):
    feed_id = _make_feed(tmp_db)
    id_1 = _insert(
        tmp_db,
        feed_id,
        "g1",
        "第一篇",
        "这是第一篇文章的内容，讲的是苹果发布新手机，性能提升明显，摄像头也升级了。",
    )
    id_2 = _insert(
        tmp_db,
        feed_id,
        "g2",
        "第二篇",
        "这是第二篇文章的内容，讲的是今天天气很好，适合出门散步和户外运动。",
    )
    first = dedup.backfill_clusters(tmp_db)
    assert first == 2

    row_1_before = db.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (id_1,))
    row_2_before = db.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (id_2,))

    second = dedup.backfill_clusters(tmp_db)
    assert second == 0

    row_1_after = db.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (id_1,))
    row_2_after = db.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (id_2,))

    assert row_1_before["cluster_id"] == row_1_after["cluster_id"]
    assert row_2_before["cluster_id"] == row_2_after["cluster_id"]


def test_backfill_first_article_self_cluster(tmp_db):
    feed_id = _make_feed(tmp_db)
    article_id = _insert(
        tmp_db,
        feed_id,
        "solo",
        "独立文章",
        "这是一篇独立的文章，内容涉及科技新闻和产品发布的相关信息，没有任何重复。",
    )
    assert dedup.backfill_clusters(tmp_db) == 1
    row = db.query_one(tmp_db, "SELECT cluster_id FROM articles WHERE id = ?", (article_id,))
    assert row["cluster_id"] == article_id