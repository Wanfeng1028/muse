
from feedflow import store


def test_star_missing_400(client, tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/star_missing.xml")
    article_id = store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="star-missing-1",
        title="T",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    resp = client.post(f"/api/articles/{article_id}/star", json={})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "is_starred 必填"


def test_star_invalid_400(client, tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/star_invalid.xml")
    article_id = store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="star-invalid-1",
        title="T",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    resp = client.post(
        f"/api/articles/{article_id}/star", json={"is_starred": "yes"}
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "is_starred 非法"


def test_star_404_and_values(client, tmp_db):
    resp = client.post("/api/articles/99999/star", json={"is_starred": 1})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "文章不存在"

    feed_id = store.create_feed(tmp_db, "https://example.com/star_values.xml")
    article_id = store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="star-values-1",
        title="T",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )

    resp_zero = client.post(
        f"/api/articles/{article_id}/star", json={"is_starred": 0}
    )
    assert resp_zero.status_code == 200
    body_zero = resp_zero.get_json()
    assert body_zero["id"] == article_id
    assert body_zero["is_starred"] == 0

    resp_str = client.post(
        f"/api/articles/{article_id}/star", json={"is_starred": "1"}
    )
    assert resp_str.status_code == 200
    body_str = resp_str.get_json()
    assert body_str["id"] == article_id
    assert body_str["is_starred"] == 1
