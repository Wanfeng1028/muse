from feedflow import store


def _make_article(tmp_db, url, guid="g1", title="t", content_text=""):
    feed_id = store.create_feed(tmp_db, url)
    article_id = store.insert_article(
        tmp_db, feed_id=feed_id, guid=guid, title=title, author="",
        link="", summary="", content_html="", content_text=content_text,
        published_at=None,
    )
    return feed_id, article_id


def _clear_all(tmp_db):
    import sqlite3
    con = sqlite3.connect(tmp_db)
    con.execute("DELETE FROM articles")
    con.execute("DELETE FROM feeds")
    con.commit()
    con.close()


def test_empty_db_returns_empty_clusters(client, tmp_db):
    _clear_all(tmp_db)
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clusters"] == []
    assert data["total"] == 0


def test_default_n_returns_clusters(client, tmp_db):
    _make_article(tmp_db, "https://example.com/a.xml", guid="g1", title="Title One", content_text="text one")
    _make_article(tmp_db, "https://example.com/b.xml", guid="g2", title="Title Two", content_text="text two")
    _make_article(tmp_db, "https://example.com/c.xml", guid="g3", title="Title Three", content_text="text three")
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "clusters" in data
    assert "total" in data
    assert data["total"] == len(data["clusters"])
    for cluster in data["clusters"]:
        assert "topic" in cluster
        assert "members" in cluster
        assert "sources" in cluster
        assert "unread" in cluster
        assert "cluster_score" in cluster


def test_n_1_limits_clusters(client, tmp_db):
    _make_article(tmp_db, "https://example.com/a.xml", guid="g1", title="Title One", content_text="text one")
    _make_article(tmp_db, "https://example.com/b.xml", guid="g2", title="Title Two", content_text="text two")
    _make_article(tmp_db, "https://example.com/c.xml", guid="g3", title="Title Three", content_text="text three")
    resp = client.get("/api/clusters?n=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == len(data["clusters"])
    assert len(data["clusters"]) <= 1


def test_invalid_n_returns_400(client, tmp_db):
    _make_article(tmp_db, "https://example.com/a.xml", guid="g1", title="Title One", content_text="text one")
    _make_article(tmp_db, "https://example.com/b.xml", guid="g2", title="Title Two", content_text="text two")
    _make_article(tmp_db, "https://example.com/c.xml", guid="g3", title="Title Three", content_text="text three")
    resp_invalid = client.get("/api/clusters?n=abc")
    assert resp_invalid.status_code == 400
    assert "n 参数非法" in resp_invalid.get_json()["error"]


def test_n_zero_returns_400(client, tmp_db):
    _make_article(tmp_db, "https://example.com/a.xml", guid="g1", title="Title One", content_text="text one")
    _make_article(tmp_db, "https://example.com/b.xml", guid="g2", title="Title Two", content_text="text two")
    _make_article(tmp_db, "https://example.com/c.xml", guid="g3", title="Title Three", content_text="text three")
    resp = client.get("/api/clusters?n=0")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_negative_n_returns_400(client, tmp_db):
    _make_article(tmp_db, "https://example.com/a.xml", guid="g1", title="Title One", content_text="text one")
    _make_article(tmp_db, "https://example.com/b.xml", guid="g2", title="Title Two", content_text="text two")
    _make_article(tmp_db, "https://example.com/c.xml", guid="g3", title="Title Three", content_text="text three")
    resp = client.get("/api/clusters?n=-5")
    assert resp.status_code == 400
    assert "n 参数非法" in resp.get_json()["error"]


def test_response_content_type_json(client, tmp_db):
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")


def test_same_title_different_feeds(client, tmp_db):
    long_text = " ".join(["word"] * 100)
    _make_article(tmp_db, "https://example.com/feed1.xml", guid="g1", title="Same Title", content_text=long_text)
    _make_article(tmp_db, "https://example.com/feed2.xml", guid="g2", title="Same Title", content_text=long_text)
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == len(data["clusters"])