from feedflow import store


def _make_article(tmp_db, url, guid="g1"):
    feed_id = store.create_feed(tmp_db, url)
    article_id = store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid=guid,
        title="t",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="",
        published_at=None,
    )
    return feed_id, article_id


def test_read_string_true_400(client, tmp_db):
    _, article_id = _make_article(tmp_db, "https://example.com/read1.xml")
    resp = client.post(f"/api/articles/{article_id}/read", json={"is_read": "true"})
    assert resp.status_code == 400


def test_read_bool_and_numeric_string(client, tmp_db):
    _, article_id = _make_article(tmp_db, "https://example.com/read2.xml")
    resp = client.post(f"/api/articles/{article_id}/read", json={"is_read": True})
    assert resp.status_code == 200
    assert resp.get_json()["is_read"] == 1

    resp2 = client.post(f"/api/articles/{article_id}/read", json={"is_read": "2"})
    assert resp2.status_code == 200
    assert resp2.get_json()["is_read"] == 1


def test_read_missing_400_and_persisted(client, tmp_db):
    _, article_id = _make_article(tmp_db, "https://example.com/read3.xml")
    resp = client.post(f"/api/articles/{article_id}/read", json={})
    assert resp.status_code == 400

    ok = client.post(f"/api/articles/{article_id}/read", json={"is_read": 1})
    assert ok.status_code == 200

    listing = client.get("/api/articles?scope=all")
    assert listing.status_code == 200
    body = listing.get_json()
    target = [a for a in body["articles"] if a["id"] == article_id]
    assert len(target) == 1
    assert target[0]["is_read"] == 1
