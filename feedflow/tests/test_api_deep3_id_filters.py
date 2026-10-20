import pytest
from feedflow import store


def _seed(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/deep3.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="deep3-1",
        title="Deep3 One",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="deep3-2",
        title="Deep3 Two",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    return feed_id


def test_feed_id_invalid_no_filter(client, tmp_db):
    resp0 = client.get("/api/articles")
    total0 = resp0.get_json()["total"]
    _seed(tmp_db)
    resp = client.get("/api/articles?feed_id=xyz")
    data = resp.get_json()
    assert data["total"] == total0 + 2


def test_folder_id_invalid_no_filter(client, tmp_db):
    resp0 = client.get("/api/articles")
    total0 = resp0.get_json()["total"]
    _seed(tmp_db)
    resp = client.get("/api/articles?folder_id=xyz")
    data = resp.get_json()
    assert data["total"] == total0 + 2


def test_feed_id_missing_zero(client, tmp_db):
    _seed(tmp_db)
    resp = client.get("/api/articles?feed_id=99999")
    data = resp.get_json()
    assert data["total"] == 0
    assert data["articles"] == []
