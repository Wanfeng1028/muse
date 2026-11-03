import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow import db as db_mod
from feedflow import store


@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / "t.db")
    db_mod.init_db(path)
    return path


def test_create_tag_normalizes(tmp_db):
    first = store.create_tag(tmp_db, "  AI  News ")
    assert first["name"] == "ai news"
    second = store.create_tag(tmp_db, "ai news")
    assert second["id"] == first["id"]


def test_create_tag_empty_raises(tmp_db):
    with pytest.raises(ValueError):
        store.create_tag(tmp_db, "")
    with pytest.raises(ValueError):
        store.create_tag(tmp_db, "   ")


def test_list_tags_counts(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    art = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    tag_a = store.create_tag(tmp_db, "alpha")
    store.create_tag(tmp_db, "beta")
    assert store.add_article_tag(tmp_db, art, tag_a["id"]) is True
    tags = store.list_tags(tmp_db)
    assert [t["name"] for t in tags] == ["alpha", "beta"]
    assert [t["article_count"] for t in tags] == [1, 0]


def test_add_article_tag_ok(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    art = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    tag = store.create_tag(tmp_db, "tech")
    assert store.add_article_tag(tmp_db, art, tag["id"]) is True
    tags = store.list_article_tags(tmp_db, art)
    assert [t["name"] for t in tags] == ["tech"]


def test_add_article_tag_duplicate_false(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    art = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    tag = store.create_tag(tmp_db, "tech")
    assert store.add_article_tag(tmp_db, art, tag["id"]) is True
    assert store.add_article_tag(tmp_db, art, tag["id"]) is False
    assert len(store.list_article_tags(tmp_db, art)) == 1


def test_add_article_tag_missing_false(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    art = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    tag = store.create_tag(tmp_db, "tech")
    assert store.add_article_tag(tmp_db, art, tag["id"] + 99999) is False
    assert store.add_article_tag(tmp_db, art + 99999, tag["id"]) is False


def test_remove_article_tag(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    art = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    tag = store.create_tag(tmp_db, "tech")
    store.add_article_tag(tmp_db, art, tag["id"])
    assert store.remove_article_tag(tmp_db, art, tag["id"]) is True
    assert store.remove_article_tag(tmp_db, art, tag["id"]) is False
    assert store.list_article_tags(tmp_db, art) == []


def test_list_articles_tag_filter(tmp_db):
    feed = store.create_feed(tmp_db, "https://example.com/feed.xml")
    a1 = store.insert_article(tmp_db, feed, "g1", "T1", "A", "https://example.com/a1", "s", "<p>1</p>", "1", None)
    store.insert_article(tmp_db, feed, "g2", "T2", "A", "https://example.com/a2", "s", "<p>2</p>", "2", None)
    tag = store.create_tag(tmp_db, "tech")
    assert store.add_article_tag(tmp_db, a1, tag["id"]) is True
    assert store.list_articles(tmp_db, scope="all", tag_id=tag["id"])[0] == 1
    assert store.list_articles(tmp_db, scope="all", tag_id=99999)[0] == 0
