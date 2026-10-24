
from datetime import UTC, datetime

from feedflow import store
from feedflow.ranking import add_keyword, get_keywords, score_article


def test_title_body_hit_counts_once(tmp_db):
    add_keyword(tmp_db, "ai")
    feed_id = store.create_feed(tmp_db, "https://example.com/kw_once_a.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="kw-once-a-1",
        title="AI 前沿报告",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="这里讨论 ai 技术细节",
        published_at=None,
    )
    keywords = get_keywords(tmp_db)
    article = {
        "title": "AI 前沿报告",
        "content_text": "这里讨论 ai 技术细节",
        "summary": "",
        "published_at": None,
        "fetched_at": None,
        "is_read": 0,
    }
    info = score_article(
        article,
        now=datetime.now(UTC),
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )
    assert info["parts"]["keyword"] == 0.5
    matched_reasons = [r for r in info["reasons"] if "命中关键词" in r]
    assert len(matched_reasons) == 1


def test_body_only_hit(tmp_db):
    add_keyword(tmp_db, "ai")
    feed_id = store.create_feed(tmp_db, "https://example.com/kw_once_b.xml")
    store.insert_article(
        tmp_db,
        feed_id=feed_id,
        guid="kw-once-b-1",
        title="今日天气",
        author="",
        link="",
        summary="",
        content_html="",
        content_text="ai 技术细节",
        published_at=None,
    )
    keywords = get_keywords(tmp_db)
    article = {
        "title": "今日天气",
        "content_text": "ai 技术细节",
        "summary": "",
        "published_at": None,
        "fetched_at": None,
        "is_read": 0,
    }
    info = score_article(
        article,
        now=datetime.now(UTC),
        cluster_size=1,
        feed_weight=1.0,
        learned=1.0,
        keywords=keywords,
    )
    assert info["parts"]["keyword"] == 0.25
