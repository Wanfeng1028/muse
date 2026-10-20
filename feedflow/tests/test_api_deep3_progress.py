import pytest
from feedflow import store


def _make_article(tmp_db, guid):
    feed_id = store.create_feed(tmp_db, f"https://example.com/{guid}.xml")
    article_id = store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid=guid,
        title="标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    return article_id


def test_progress_float_string(client, tmp_db):
    article_id = _make_article(tmp_db, "progress-float")
    resp = client.post(
        f"/api/articles/{article_id}/progress",
        json={"scroll_pos": "12.5"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scroll_pos"] == 12.5


def test_progress_clamped(client, tmp_db):
    article_id = _make_article(tmp_db, "progress-clamped")
    resp = client.post(
        f"/api/articles/{article_id}/progress",
        json={"scroll_pos": 200000},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scroll_pos"] == 100000.0


def test_progress_invalid(client, tmp_db):
    article_id = _make_article(tmp_db, "progress-invalid")
    resp_missing = client.post(
        f"/api/articles/{article_id}/progress",
        json={},
    )
    assert resp_missing.status_code == 400

    resp_negative = client.post(
        f"/api/articles/{article_id}/progress",
        json={"scroll_pos": -5},
    )
    assert resp_negative.status_code == 400

    resp_abc = client.post(
        f"/api/articles/{article_id}/progress",
        json={"scroll_pos": "abc"},
    )
    assert resp_abc.status_code == 400

    resp_404 = client.post(
        "/api/articles/99999/progress",
        json={"scroll_pos": 1},
    )
    assert resp_404.status_code == 404
