"""覆盖 GET /api/articles/<article_id>/score 端点（v1.8 新增）：
响应结构、404、评分公式一致性、已读/未读因子、
cluster_size 计数、关键词命中、published_at 缺失容错、
单例文章 heat 为零。"""

import math
import sqlite3
from datetime import UTC, datetime

import pytest

from feedflow import ranking, store


def _clear_all(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute("DELETE FROM articles")
    con.execute("DELETE FROM feeds")
    con.commit()
    con.close()


def test_score_shape(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://shape.example.com/rss")
    aid = store.insert_article(
        tmp_db,
        fid,
        "g-shape",
        "ShapeTitle",
        "auth",
        "https://shape.example.com/1",
        "sum",
        "<p>hi</p>",
        "hi",
        None,
    )
    rv = client.get(f"/api/articles/{aid}/score")
    assert rv.status_code == 200
    data = rv.get_json()
    assert set(data.keys()) == {
        "article_id",
        "title",
        "score",
        "parts",
        "reasons",
        "cluster_size",
        "age_hours",
    }
    assert set(data["parts"].keys()) == {
        "recency",
        "heat",
        "source",
        "keyword",
        "unread",
    }
    for v in data["parts"].values():
        assert isinstance(v, float)
        assert 0 <= v <= 1
    assert isinstance(data["score"], float)
    assert 0 <= data["score"] <= 1
    assert isinstance(data["reasons"], list)
    assert data["article_id"] == aid
    assert data["title"] == "ShapeTitle"
    assert data["cluster_size"] == 1


def test_score_404(client, tmp_db):
    _clear_all(tmp_db)
    rv = client.get("/api/articles/999999/score")
    assert rv.status_code == 404
    assert rv.get_json()["error"] == "文章不存在"


def test_score_matches_formula(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://formula.example.com/rss")
    now_iso = datetime.now(UTC).isoformat()
    aid = store.insert_article(
        tmp_db,
        fid,
        "g-formula",
        "FormulaTitle",
        "auth",
        "https://formula.example.com/1",
        "sum",
        "<p>x</p>",
        "x",
        now_iso,
    )
    rv = client.get(f"/api/articles/{aid}/score")
    assert rv.status_code == 200
    data = rv.get_json()

    article = store.get_article(tmp_db, aid)
    expected = ranking.score_article(
        article,
        now=datetime.now(UTC),
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=ranking.get_keywords(tmp_db),
    )
    assert data["score"] == pytest.approx(expected["score"], rel=1e-3)
    for k in ("recency", "heat", "source", "keyword", "unread"):
        assert data["parts"][k] == pytest.approx(expected["parts"][k], rel=1e-3)


def test_score_read_unread_factor(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://read.example.com/rss")
    aid = store.insert_article(
        tmp_db,
        fid,
        "g-read",
        "ReadTitle",
        "auth",
        "https://read.example.com/1",
        "sum",
        "<p>y</p>",
        "y",
        None,
    )
    rv1 = client.get(f"/api/articles/{aid}/score")
    assert rv1.status_code == 200
    data1 = rv1.get_json()
    assert data1["parts"]["unread"] == 1.0

    store.set_read(tmp_db, aid, 1)
    rv2 = client.get(f"/api/articles/{aid}/score")
    assert rv2.status_code == 200
    data2 = rv2.get_json()
    assert data2["parts"]["unread"] == 0.0
    assert data2["score"] < data1["score"]


def test_score_cluster_size(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://cluster.example.com/rss")
    a1 = store.insert_article(
        tmp_db,
        fid,
        "g-c1",
        "C1",
        "auth",
        "https://cluster.example.com/1",
        "sum",
        "<p>a</p>",
        "a",
        None,
    )
    a2 = store.insert_article(
        tmp_db,
        fid,
        "g-c2",
        "C2",
        "auth",
        "https://cluster.example.com/2",
        "sum",
        "<p>b</p>",
        "b",
        None,
    )
    con = sqlite3.connect(tmp_db)
    con.execute(
        "UPDATE articles SET cluster_id = 777 WHERE id IN (?, ?)",
        (a1, a2),
    )
    con.commit()
    con.close()

    rv1 = client.get(f"/api/articles/{a1}/score")
    rv2 = client.get(f"/api/articles/{a2}/score")
    assert rv1.get_json()["cluster_size"] == 2
    assert rv2.get_json()["cluster_size"] == 2


def test_score_keyword_match(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://kw.example.com/rss")
    ranking.add_keyword(tmp_db, "量子")

    aid_hit = store.insert_article(
        tmp_db,
        fid,
        "g-kw1",
        "量子计算突破",
        "auth",
        "https://kw.example.com/1",
        "sum",
        "<p>k</p>",
        "k",
        None,
    )
    rv = client.get(f"/api/articles/{aid_hit}/score")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["parts"]["keyword"] > 0.0
    assert any("关键词" in r for r in data["reasons"])

    aid_miss = store.insert_article(
        tmp_db,
        fid,
        "g-kw2",
        "普通新闻",
        "auth",
        "https://kw.example.com/2",
        "sum",
        "<p>m</p>",
        "m",
        None,
    )
    rv2 = client.get(f"/api/articles/{aid_miss}/score")
    assert rv2.get_json()["parts"]["keyword"] == 0.0


def test_score_no_published_at_no_crash(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://null.example.com/rss")
    aid = store.insert_article(
        tmp_db,
        fid,
        "g-null",
        "NoDate",
        "auth",
        "https://null.example.com/1",
        "sum",
        "<p>n</p>",
        "n",
        None,
    )
    rv = client.get(f"/api/articles/{aid}/score")
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data["age_hours"], (int, float))
    assert math.isfinite(data["age_hours"])
    assert data["age_hours"] >= 0


def test_score_singleton_heat_zero(client, tmp_db):
    _clear_all(tmp_db)
    fid = store.create_feed(tmp_db, "https://heat.example.com/rss")
    aid = store.insert_article(
        tmp_db,
        fid,
        "g-heat",
        "Alone",
        "auth",
        "https://heat.example.com/1",
        "sum",
        "<p>o</p>",
        "o",
        None,
    )
    rv = client.get(f"/api/articles/{aid}/score")
    assert rv.status_code == 200
    assert rv.get_json()["parts"]["heat"] == 0.0
