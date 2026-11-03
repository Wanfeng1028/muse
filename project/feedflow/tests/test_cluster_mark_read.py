from feedflow import db, store


def test_store_mark_cluster_read_batch(tmp_db):
    """真簇未读批量标已读：同一簇 7 的 3 篇（2 未读 + 1 预先已读）
    加另一簇 8 的 1 篇未读；mark_cluster_read 返回 2；
    簇 7 三篇全已读，簇 8 仍未读。"""
    fid = store.create_feed(tmp_db, "https://example.com/batch.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="batch-a1",
                              title="批量标题一", author="", link="",
                              summary="", content_html="",
                              content_text="批量内容一", published_at=None)
    a2 = store.insert_article(tmp_db, feed_id=fid, guid="batch-a2",
                              title="批量标题二", author="", link="",
                              summary="", content_html="",
                              content_text="批量内容二", published_at=None)
    a3 = store.insert_article(tmp_db, feed_id=fid, guid="batch-a3",
                              title="批量标题三", author="", link="",
                              summary="", content_html="",
                              content_text="批量内容三", published_at=None)
    a4 = store.insert_article(tmp_db, feed_id=fid, guid="batch-a4",
                              title="批量标题四", author="", link="",
                              summary="", content_html="",
                              content_text="批量内容四", published_at=None)
    # 强制指定簇归属
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a2))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a3))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (8, a4))
    # 预先标记 a3 为已读
    store.set_read(tmp_db, a3, 1)
    # 调用 mark_cluster_read，仅更新簇 7 中未读的 2 篇
    updated = store.mark_cluster_read(tmp_db, 7, scope="unread")
    assert updated == 2
    # 簇 7 三篇全部已读
    for aid in (a1, a2, a3):
        row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (aid,)))
        assert row["is_read"] == 1
    # 簇 8 仍然未读
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a4,)))
    assert row["is_read"] == 0


def test_store_mark_cluster_read_solo(tmp_db):
    """solo 单篇：两篇 cluster_id 均为 NULL；
    按其中一篇 id 调用返回 1；该篇已读，另一篇仍未读。"""
    fid = store.create_feed(tmp_db, "https://example.com/solo.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="solo-a1",
                              title="独立标题一", author="", link="",
                              summary="", content_html="",
                              content_text="独立内容一", published_at=None)
    a2 = store.insert_article(tmp_db, feed_id=fid, guid="solo-a2",
                              title="独立标题二", author="", link="",
                              summary="", content_html="",
                              content_text="独立内容二", published_at=None)
    # 强制置为 solo（cluster_id 为 NULL）
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (None, a1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (None, a2))
    updated = store.mark_cluster_read(tmp_db, a1, scope="unread")
    assert updated == 1
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a1,)))
    assert row["is_read"] == 1
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a2,)))
    assert row["is_read"] == 0


def test_store_mark_cluster_read_starred_scope(tmp_db):
    """starred 范围：同一簇 3 篇全未读，其中 1 篇标星；
    scope="starred" 返回 1；仅星标篇已读。"""
    fid = store.create_feed(tmp_db, "https://example.com/starred.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="star-a1",
                              title="星标标题一", author="", link="",
                              summary="", content_html="",
                              content_text="星标内容一", published_at=None)
    a2 = store.insert_article(tmp_db, feed_id=fid, guid="star-a2",
                              title="星标标题二", author="", link="",
                              summary="", content_html="",
                              content_text="星标内容二", published_at=None)
    a3 = store.insert_article(tmp_db, feed_id=fid, guid="star-a3",
                              title="星标标题三", author="", link="",
                              summary="", content_html="",
                              content_text="星标内容三", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a2))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a3))
    # 仅 a2 标星
    store.set_starred(tmp_db, a2, 1)
    updated = store.mark_cluster_read(tmp_db, 7, scope="starred")
    assert updated == 1
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a1,)))
    assert row["is_read"] == 0
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a2,)))
    assert row["is_read"] == 1
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a3,)))
    assert row["is_read"] == 0


def test_store_cluster_exists(tmp_db):
    """cluster_exists：真簇 id 存在为 True；
    solo 文章 id 为 True；不存在的 99999 为 False。"""
    fid = store.create_feed(tmp_db, "https://example.com/exists.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="exist-a1",
                              title="存在标题一", author="", link="",
                              summary="", content_html="",
                              content_text="存在内容一", published_at=None)
    a2 = store.insert_article(tmp_db, feed_id=fid, guid="exist-a2",
                              title="存在标题二", author="", link="",
                              summary="", content_html="",
                              content_text="存在内容二", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (None, a2))
    # 真簇 7 存在
    assert store.cluster_exists(tmp_db, 7) is True
    # solo 文章 a2 以其 id 作为簇标识存在
    assert store.cluster_exists(tmp_db, a2) is True
    # 不存在的簇
    assert store.cluster_exists(tmp_db, 99999) is False


def test_api_mark_cluster_read_batch(client, tmp_db):
    """端点批量标已读：簇 7 两篇未读；
    POST 返回 200 且 updated 为 2；
    再 POST 一次返回 200 且 updated 为 0（幂等）。"""
    fid = store.create_feed(tmp_db, "https://example.com/api-batch.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="api-b1",
                              title="接口批量一", author="", link="",
                              summary="", content_html="",
                              content_text="接口批量内容一", published_at=None)
    a2 = store.insert_article(tmp_db, feed_id=fid, guid="api-b2",
                              title="接口批量二", author="", link="",
                              summary="", content_html="",
                              content_text="接口批量内容二", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a2))
    # 首次请求
    resp = client.post("/api/clusters/7/read", json={"scope": "unread"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cluster_id"] == 7
    assert data["updated"] == 2
    # 幂等：再次请求，已全部已读
    resp2 = client.post("/api/clusters/7/read", json={"scope": "unread"})
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["updated"] == 0


def test_api_mark_cluster_read_not_found(client, tmp_db):
    """不存在的簇 POST 返回 404。"""
    resp = client.post("/api/clusters/99999/read", json={"scope": "unread"})
    assert resp.status_code == 404


def test_api_mark_cluster_read_invalid_scope(client, tmp_db):
    """非法 scope（如 "bogus"）POST 返回 400。"""
    # 先建一个真实簇，确保不是 404
    fid = store.create_feed(tmp_db, "https://example.com/api-invalid.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="api-inv1",
                              title="非法范围标题", author="", link="",
                              summary="", content_html="",
                              content_text="非法范围内容", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a1))
    resp = client.post("/api/clusters/7/read", json={"scope": "bogus"})
    assert resp.status_code == 400


def test_api_mark_cluster_read_solo(client, tmp_db):
    """solo 文章经端点标已读：cluster_id 为 NULL 的单篇，
    按其 id POST 返回 200 且 updated 为 1。"""
    fid = store.create_feed(tmp_db, "https://example.com/api-solo.xml")
    a1 = store.insert_article(tmp_db, feed_id=fid, guid="api-solo1",
                              title="接口独立标题", author="", link="",
                              summary="", content_html="",
                              content_text="接口独立内容", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (None, a1))
    resp = client.post(f"/api/clusters/{a1}/read", json={"scope": "unread"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cluster_id"] == a1
    assert data["updated"] == 1


def test_api_mark_cluster_read_no_cross_cluster(client, tmp_db):
    """端点不越簇：簇 7 与簇 8 各 1 篇未读；
    POST 簇 7 后簇 8 仍未读。"""
    fid = store.create_feed(tmp_db, "https://example.com/api-nocross.xml")
    a7 = store.insert_article(tmp_db, feed_id=fid, guid="api-nc7",
                              title="不越簇七", author="", link="",
                              summary="", content_html="",
                              content_text="不越簇内容七", published_at=None)
    a8 = store.insert_article(tmp_db, feed_id=fid, guid="api-nc8",
                              title="不越簇八", author="", link="",
                              summary="", content_html="",
                              content_text="不越簇内容八", published_at=None)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, a7))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (8, a8))
    resp = client.post("/api/clusters/7/read", json={"scope": "unread"})
    assert resp.status_code == 200
    # 簇 8 的文章仍为未读
    row = dict(db.query_one(tmp_db, "SELECT * FROM articles WHERE id=?", (a8,)))
    assert row["is_read"] == 0
