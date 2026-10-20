from datetime import UTC, datetime, timedelta
from feedflow import ranking
import math
import pytest

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)

def test_score_全新文章各分项精确值():
    article = {"title": "t", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"] == {"recency": 1.0, "heat": 0.0, "source": 0.4, "keyword": 0.0, "unread": 1.0}
    assert result["score"] == 0.48
    assert result["reasons"] == ["刚刚发布"]

def test_score_关键词标题命中双倍():
    article = {"title": "AI 芯片新突破", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    keywords = [{"keyword": "AI", "weight": 1.0}]
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=keywords)
    assert result["parts"]["keyword"] == 0.5
    assert "命中关键词「AI」" in result["reasons"]

def test_score_关键词命中上限封顶():
    article = {"title": "a b c d 全有", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    keywords = [{"keyword": "a"}, {"keyword": "b"}, {"keyword": "c"}, {"keyword": "d"}]
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=keywords)
    assert result["parts"]["keyword"] == 1.0

def test_score_关键词只命中正文():
    article = {"title": "无关标题", "content_text": "这里提到 python", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    keywords = [{"keyword": "python", "weight": 1.0}]
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=keywords)
    assert result["parts"]["keyword"] == 0.25

def test_score_已读文章unread为0():
    article = {"title": "t", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 1}
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"]["unread"] == 0.0

def test_score_簇热度边界():
    article = {"title": "t", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    result = ranking.score_article(article, now=NOW, cluster_size=8, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"]["heat"] == 1.0
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"]["heat"] == 0.0
    result = ranking.score_article(article, now=NOW, cluster_size=0, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"]["heat"] == 0.0
    assert result["cluster_size"] == 1

def test_score_来源权重饱和与极低():
    article = {"title": "t", "published_at": "2026-10-21T12:00:00+00:00", "is_read": 0}
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=5.0, learned=2.0, keywords=[])
    assert result["parts"]["source"] == 1.0
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=0.1, learned=0.5, keywords=[])
    assert result["parts"]["source"] == pytest.approx(0.02)

def test_format_age_边界():
    assert ranking._format_age(0.0) == "刚刚"
    assert ranking._format_age(0.5) == "30 分钟前"
    assert ranking._format_age(47.9) == "47 小时前"
    assert ranking._format_age(48.0) == "2 天前"
    assert ranking._format_age(72.0) == "3 天前"

def test_age_hours_未来时间为0():
    future = NOW + timedelta(hours=5)
    article = {"published_at": future.isoformat()}
    assert ranking._age_hours(article["published_at"], None, NOW) == 0.0
    article = {"published_at": "not-a-date"}
    assert ranking._age_hours(article["published_at"], None, NOW) == 0.0





def test_score_半衰期衰减():
    article = {"title": "t", "published_at": "2026-10-19T12:00:00+00:00", "is_read": 0}
    result = ranking.score_article(article, now=NOW, cluster_size=1, feed_weight=1.0, learned=1.0, keywords=[])
    assert result["parts"]["recency"] == pytest.approx(0.5)
    assert result["reasons"][0] == "2 天前发布"
