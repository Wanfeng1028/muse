"""GET /api/clusters 的 cluster_score 评分语义 API 测试。

覆盖 HTTP 层穿透到评分语义：响应形状、分数与纯函数一致性、
降序排列、多成员/未读/时效加成、n 参数语义、分数有界性。
（端点基础形状见 test_api_clusters.py；get_digest_clusters 函数级见
test_digest_clusters.py；纯函数见 test_cluster_scoring.py，本文件不重复。）
"""

import math
from datetime import UTC, datetime

import pytest

from feedflow import db, store
from feedflow.cluster_scoring import cluster_importance_score


def _clear_all(tmp_db):
    import sqlite3

    con = sqlite3.connect(tmp_db)
    con.execute("DELETE FROM articles")
    con.execute("DELETE FROM feeds")
    con.commit()
    con.close()


def test_empty_db(client, tmp_db):
    _clear_all(tmp_db)
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clusters"] == []
    assert data["total"] == 0


def test_shape(client, tmp_db):
    _clear_all(tmp_db)
    feed_id = store.create_feed(tmp_db, "http://example.com/feed")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="g1",
        title="t",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="正文",
        published_at=None,
    )
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    cluster = data["clusters"][0]
    expected_keys = {
        "cluster_id",
        "topic",
        "members",
        "sources",
        "unread",
        "representative",
        "cluster_score",
        "cluster_reasons",
        "latest_at",
    }
    assert expected_keys.issubset(cluster.keys())
    assert isinstance(cluster["cluster_score"], float)


def test_score_equals_formula(client, tmp_db):
    _clear_all(tmp_db)
    feed1 = store.create_feed(tmp_db, "http://example.com/feed1")
    feed2 = store.create_feed(tmp_db, "http://example.com/feed2")
    aid1 = store.insert_article(
        tmp_db,
        feed_id=feed1,
        guid="g1",
        title="苹果发布会",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="苹果今日发布新品",
        published_at="2020-01-01T00:00:00",
    )
    aid2 = store.insert_article(
        tmp_db,
        feed_id=feed2,
        guid="g2",
        title="苹果发布会",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="苹果今日发布新品",
        published_at="2020-01-01T00:00:00",
    )
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, aid1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (7, aid2))
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    cluster = next(c for c in data["clusters"] if c["cluster_id"] == 7)
    rep = cluster["representative"]
    expected = cluster_importance_score(
        float(rep["score_info"]["score"]),
        cluster["members"],
        cluster["sources"],
        cluster["unread"],
        cluster["latest_at"],
    )
    assert cluster["cluster_score"] == pytest.approx(expected, abs=1e-6)


def test_descending(client, tmp_db):
    _clear_all(tmp_db)
    dates = ["2020-01-01T00:00:00", "2024-01-01T00:00:00", "2026-10-21T10:00:00"]
    for i, dt in enumerate(dates):
        feed_id = store.create_feed(tmp_db, f"http://example.com/feed{i}")
        store.insert_article(
            tmp_db,
            feed_id=feed_id,
            guid=f"g{i}",
            title="新闻标题",
            author="",
            link="",
            summary="",
            content_html="",
            content_text="新闻正文内容",
            published_at=dt,
        )
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    scores = [c["cluster_score"] for c in data["clusters"]]
    assert scores == sorted(scores, reverse=True)


def test_multi_member_first(client, tmp_db):
    _clear_all(tmp_db)
    feed1 = store.create_feed(tmp_db, "http://example.com/feed1")
    feed2 = store.create_feed(tmp_db, "http://example.com/feed2")
    aid1 = store.insert_article(
        tmp_db,
        feed_id=feed1,
        guid="g1",
        title="相同标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="相同正文相同正文",
        published_at="2020-01-01T00:00:00",
    )
    aid2 = store.insert_article(
        tmp_db,
        feed_id=feed1,
        guid="g2",
        title="相同标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="相同正文相同正文",
        published_at="2020-01-01T00:00:00",
    )
    store.insert_article(
        tmp_db,
        feed_id=feed2,
        guid="g3",
        title="相同标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="相同正文相同正文",
        published_at="2020-01-01T00:00:00",
    )
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (11, aid1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (11, aid2))
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["clusters"][0]["cluster_id"] == 11


def test_unread_boost(client, tmp_db):
    _clear_all(tmp_db)
    # 每篇文章独立 feed：已读文章所在源的 learned 加成不会污染未读代表文章
    aids = []
    for i in range(4):
        fid = store.create_feed(tmp_db, f"http://u{i}")
        aid = store.insert_article(
            tmp_db,
            feed_id=fid,
            guid=f"gu{i}",
            title="同题",
            author="",
            link="",
            summary="",
            content_html="",
            content_text="同文同文",
            published_at="2020-01-01T00:00:00",
        )
        aids.append(aid)
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (21, aids[0]))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (21, aids[1]))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (22, aids[2]))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (22, aids[3]))
    store.set_read(tmp_db, aids[3], 1)

    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()

    clusters = {c["cluster_id"]: c for c in data["clusters"]}
    assert 21 in clusters
    assert 22 in clusters
    assert clusters[21]["unread"] == 2
    assert clusters[22]["unread"] == 1
    assert clusters[21]["cluster_score"] > clusters[22]["cluster_score"]


def test_recency(client, tmp_db):
    _clear_all(tmp_db)
    feed1 = store.create_feed(tmp_db, "http://f1")
    feed2 = store.create_feed(tmp_db, "http://f2")

    store.insert_article(
        tmp_db,
        feed_id=feed1,
        guid="g1",
        title="时效标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="时效正文时效正文",
        published_at="2020-01-01T00:00:00",
    )
    store.insert_article(
        tmp_db,
        feed_id=feed2,
        guid="g2",
        title="时效标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="时效正文时效正文",
        published_at=datetime.now(UTC).isoformat(),
    )

    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()

    assert len(data["clusters"]) == 2
    assert data["clusters"][0]["latest_at"] > data["clusters"][1]["latest_at"]
    assert data["clusters"][0]["cluster_score"] > data["clusters"][1]["cluster_score"]


def test_n_limits(client, tmp_db):
    _clear_all(tmp_db)
    for i in range(3):
        feed = store.create_feed(tmp_db, f"http://f{i}")
        store.insert_article(
            tmp_db,
            feed_id=feed,
            guid=f"g{i}",
            title=f"t{i}",
            author="",
            link="",
            summary="",
            content_html="",
            content_text=f"c{i}",
            published_at=None,
        )

    resp = client.get("/api/clusters?n=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["clusters"]) <= 1
    assert data["total"] <= 1


def test_invalid_n(client, tmp_db):
    _clear_all(tmp_db)
    for i in range(2):
        feed = store.create_feed(tmp_db, f"http://f{i}")
        store.insert_article(
            tmp_db,
            feed_id=feed,
            guid=f"g{i}",
            title=f"t{i}",
            author="",
            link="",
            summary="",
            content_html="",
            content_text=f"c{i}",
            published_at=None,
        )

    resp = client.get("/api/clusters?n=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 0

    resp = client.get("/api/clusters?n=abc")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == len(data["clusters"])


def test_score_bounded_and_reason(client, tmp_db):
    _clear_all(tmp_db)

    feed1 = store.create_feed(tmp_db, "http://f1")
    feed2 = store.create_feed(tmp_db, "http://f2")

    aid1 = store.insert_article(
        tmp_db,
        feed_id=feed1,
        guid="g1",
        title="边界标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="边界正文",
        published_at="2020-01-01T00:00:00",
    )
    aid2 = store.insert_article(
        tmp_db,
        feed_id=feed2,
        guid="g2",
        title="边界标题",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="边界正文",
        published_at="2020-01-01T00:00:00",
    )

    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (31, aid1))
    db.execute_write(tmp_db, "UPDATE articles SET cluster_id=? WHERE id=?", (31, aid2))

    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.get_json()

    for cluster in data["clusters"]:
        assert 0 <= cluster["cluster_score"]
        assert math.isfinite(cluster["cluster_score"])

    cluster31 = next(c for c in data["clusters"] if c["cluster_id"] == 31)
    assert any("同事件" in r for r in cluster31["cluster_reasons"])
