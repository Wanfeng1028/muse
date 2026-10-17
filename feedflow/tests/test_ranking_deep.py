"""ranking 模块深度测试：排序稳定性、权重边界、学习权重、设置项。

覆盖：关键词去重与大小写、权重上下界、learned 计算、digest_n 容错、
排序确定性、settings upsert、feed 权重与 feed 顺序。
"""

from __future__ import annotations

import pytest

from feedflow import db as db_mod
from feedflow.ranking import (
    FEED_WEIGHT_MAX,
    FEED_WEIGHT_MIN,
    LEARNED_MAX,
    LEARNED_MIN,
    add_keyword,
    delete_keyword,
    get_digest_n,
    get_feed_weights,
    get_keywords,
    get_setting,
    learn_source_weights,
    set_feed_weight,
    set_setting,
)


def _insert_feed(db_path, title, position=0):
    return db_mod.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, ?, ?)",
        (title, f"http://example.com/{title}.xml", position, db_mod.utcnow()),
    )


def _insert_article(db_path, feed_id, title, is_read=0, is_starred=0):
    return db_mod.execute_write(
        db_path,
        """
        INSERT INTO articles
            (feed_id, guid, title, link, published_at, fetched_at, is_read, is_starred, cluster_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            feed_id,
            "g-" + title,
            title,
            f"http://example.com/a/{title}",
            "2024-01-01T00:00:00+00:00",
            db_mod.utcnow(),
            is_read,
            is_starred,
        ),
    )


def test_keyword_add_dedup_case_insensitive(tmp_db):
    first = add_keyword(tmp_db, "Python")
    second = add_keyword(tmp_db, "python")
    third = add_keyword(tmp_db, "  PYTHON  ")
    assert first == second
    assert second == third
    rows = get_keywords(tmp_db)
    assert len(rows) == 1
    assert rows[0]["keyword"] == "Python"


def test_keyword_empty_raises(tmp_db):
    with pytest.raises(ValueError):
        add_keyword(tmp_db, "")
    with pytest.raises(ValueError):
        add_keyword(tmp_db, "   ")
    assert get_keywords(tmp_db) == []


def test_keyword_delete_and_missing(tmp_db):
    kid = add_keyword(tmp_db, "ai")
    assert delete_keyword(tmp_db, kid) is True
    assert delete_keyword(tmp_db, kid) is False
    assert get_keywords(tmp_db) == []


def test_set_feed_weight_bounds(tmp_db):
    fid = _insert_feed(tmp_db, "feed-a")
    set_feed_weight(tmp_db, fid, FEED_WEIGHT_MAX)
    rows = get_feed_weights(tmp_db)
    assert len(rows) == 1
    assert rows[0]["weight"] == FEED_WEIGHT_MAX
    with pytest.raises(ValueError):
        set_feed_weight(tmp_db, fid, FEED_WEIGHT_MAX + 0.01)
    with pytest.raises(ValueError):
        set_feed_weight(tmp_db, fid, FEED_WEIGHT_MIN - 0.01)


def test_set_feed_weight_missing_feed(tmp_db):
    with pytest.raises(ValueError):
        set_feed_weight(tmp_db, 9999, 1.0)
    with pytest.raises(ValueError):
        set_feed_weight(tmp_db, 9999, "abc")


def test_set_feed_weight_preserves_learned(tmp_db):
    fid = _insert_feed(tmp_db, "feed-learn")
    _insert_article(tmp_db, fid, "a1", is_starred=1)
    learn_source_weights(tmp_db)
    before = get_feed_weights(tmp_db)[0]["learned"]
    set_feed_weight(tmp_db, fid, 3.0)
    after = get_feed_weights(tmp_db)[0]
    assert after["weight"] == 3.0
    assert after["learned"] == before


def test_learn_source_weights_math(tmp_db):
    fid = _insert_feed(tmp_db, "feed-math")
    for i in range(10):
        _insert_article(
            tmp_db,
            fid,
            f"a{i}",
            is_read=1 if i < 5 else 0,
            is_starred=1 if i < 2 else 0,
        )
    learn_source_weights(tmp_db)
    learned = get_feed_weights(tmp_db)[0]["learned"]
    expected = round(min(LEARNED_MAX, max(LEARNED_MIN, 1.0 + 1.0 * 0.2 + 0.3 * 0.5)), 3)
    assert learned == expected
    assert LEARNED_MIN <= learned <= LEARNED_MAX


def test_learn_source_weights_no_articles(tmp_db):
    _insert_feed(tmp_db, "empty-feed")
    learn_source_weights(tmp_db)
    rows = get_feed_weights(tmp_db)
    assert len(rows) == 1
    assert rows[0]["learned"] == 1.0


def test_learn_source_weights_deterministic(tmp_db):
    fid = _insert_feed(tmp_db, "feed-det")
    for i in range(6):
        _insert_article(tmp_db, fid, f"b{i}", is_read=1, is_starred=0)
    learn_source_weights(tmp_db)
    first = get_feed_weights(tmp_db)[0]["learned"]
    learn_source_weights(tmp_db)
    second = get_feed_weights(tmp_db)[0]["learned"]
    assert first == second
    assert first == round(min(LEARNED_MAX, max(LEARNED_MIN, 1.0 + 0.3 * 1.0)), 3)


def test_get_digest_n_defaults_and_invalid(tmp_db):
    assert get_digest_n(tmp_db) == 20
    set_setting(tmp_db, "digest_n", "abc")
    assert get_digest_n(tmp_db) == 20
    set_setting(tmp_db, "digest_n", "0")
    assert get_digest_n(tmp_db) == 20
    set_setting(tmp_db, "digest_n", "-5")
    assert get_digest_n(tmp_db) == 20


def test_get_digest_n_valid(tmp_db):
    set_setting(tmp_db, "digest_n", "7")
    assert get_digest_n(tmp_db) == 7
    set_setting(tmp_db, "digest_n", "  15  ")
    assert get_digest_n(tmp_db) == 15


def test_setting_upsert_and_default(tmp_db):
    assert get_setting(tmp_db, "missing", "fallback") == "fallback"
    set_setting(tmp_db, "mode", "compact")
    assert get_setting(tmp_db, "mode") == "compact"
    set_setting(tmp_db, "mode", "expanded")
    assert get_setting(tmp_db, "mode") == "expanded"
    assert get_setting(tmp_db, "mode") == "expanded"


def test_feed_weights_order_by_position(tmp_db):
    _insert_feed(tmp_db, "feed-c", position=3)
    _insert_feed(tmp_db, "feed-a", position=1)
    _insert_feed(tmp_db, "feed-b", position=2)
    rows = get_feed_weights(tmp_db)
    titles = [r["title"] for r in rows]
    assert titles == ["feed-a", "feed-b", "feed-c"]
    assert all(r["weight"] == 1.0 for r in rows)
    assert all(r["learned"] == 1.0 for r in rows)


def test_feed_weights_default_when_no_row(tmp_db):
    fid = _insert_feed(tmp_db, "feed-no-weight")
    rows = get_feed_weights(tmp_db)
    assert len(rows) == 1
    assert rows[0]["feed_id"] == fid
    assert rows[0]["weight"] == 1.0
    assert rows[0]["learned"] == 1.0