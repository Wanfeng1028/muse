"""搜索功能深度测试。

覆盖 web.py:113 GET /search 背后的 store.search_articles 与 trigram FTS5 行为。
所有断言基于 store.py 中 search_articles 的真实实现：
- 查询短于 3 个字符走 LIKE
- 查询不短于 3 个字符走 FTS5 MATCH ... ORDER BY rank
- 查询中的双引号会被剥除
"""
import time

import pytest

from feedflow import store


def _make_db(tmp_path):
    from feedflow import db as _db
    p = str(tmp_path / "search_deep.db")
    _db.init_db(p)
    return p


def _seed(db_path, feeds, articles):
    for f in feeds:
        fid = store.create_feed(db_path, f["url"])
        store.update_feed(db_path, fid, title=f["title"])
    feed_rows = store.list_feeds(db_path)
    feed_id_by_url = {row["feed_url"]: row["id"] for row in feed_rows}
    for art in articles:
        store.insert_article(
            db_path,
            feed_id_by_url[art["feed_url"]],
            art["guid"],
            art["title"],
            art.get("author", ""),
            art.get("link", "http://example.com/" + art["guid"]),
            art.get("summary", ""),
            art.get("content_html", "<p>" + art.get("content_text", "") + "</p>"),
            art.get("content_text", ""),
            art.get("published_at", "2024-01-01T00:00:00"),
        )


@pytest.fixture
def zh_db(tmp_path):
    db_path = _make_db(tmp_path)
    _seed(
        db_path,
        [{"url": "http://example.com/zh", "title": "中文源"}],
        [
            {
                "feed_url": "http://example.com/zh",
                "guid": "zh-1",
                "title": "人工智能前沿",
                "content_text": "本文讨论人工智能的发展。",
                "published_at": "2024-01-03T00:00:00",
            },
            {
                "feed_url": "http://example.com/zh",
                "guid": "zh-2",
                "title": "智能制造观察",
                "content_text": "智能制造与产业升级。",
                "published_at": "2024-01-02T00:00:00",
            },
            {
                "feed_url": "http://example.com/zh",
                "guid": "zh-3",
                "title": "天气预报",
                "content_text": "今日多云转晴。",
                "published_at": "2024-01-01T00:00:00",
            },
        ],
    )
    return db_path


@pytest.fixture
def en_db(tmp_path):
    db_path = _make_db(tmp_path)
    _seed(
        db_path,
        [{"url": "http://example.com/en", "title": "English Source"}],
        [
            {
                "feed_url": "http://example.com/en",
                "guid": "en-1",
                "title": "Python Tutorial",
                "content_text": "Learn Python programming step by step.",
                "published_at": "2024-02-03T00:00:00",
            },
            {
                "feed_url": "http://example.com/en",
                "guid": "en-2",
                "title": "PYTHON advanced",
                "content_text": "Advanced PYTHON topics.",
                "published_at": "2024-02-02T00:00:00",
            },
            {
                "feed_url": "http://example.com/en",
                "guid": "en-3",
                "title": "Ruby notes",
                "content_text": "Ruby is a scripting language.",
                "published_at": "2024-02-01T00:00:00",
            },
        ],
    )
    return db_path


def test_chinese_two_char_matches(zh_db):
    """两字中文查询走 LIKE，能命中标题含该两字的文章。"""
    results = store.search_articles(zh_db, "人工")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert "人工智能前沿" in titles


def test_chinese_single_char_matches(zh_db):
    """单字中文查询走 LIKE，能命中标题或正文含该字的文章。"""
    results = store.search_articles(zh_db, "智")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert "人工智能前沿" in titles
    assert "智能制造观察" in titles


def test_chinese_three_char_uses_fts(zh_db):
    """三字及以上中文查询走 FTS5 MATCH，命中含该词的文章。"""
    results = store.search_articles(zh_db, "人工智能")
    assert len(results) >= 1
    titles = [r["title"] for r in results]
    assert "人工智能前沿" in titles


def test_chinese_no_match_returns_empty(zh_db):
    """完全不相关的中文词返回空列表，不报错。"""
    results = store.search_articles(zh_db, "量子纠缠计算")
    assert results == []


def test_english_case_insensitive(en_db):
    """英文查询大小写不敏感。"""
    lower = store.search_articles(en_db, "python")
    upper = store.search_articles(en_db, "PYTHON")
    assert len(lower) >= 1
    assert len(upper) >= 1
    lower_guids = sorted(r["guid"] for r in lower)
    upper_guids = sorted(r["guid"] for r in upper)
    assert lower_guids == upper_guids


def test_english_prefix_match(en_db):
    """英文前缀匹配：'prog' 能命中含 'programming' 的正文。"""
    results = store.search_articles(en_db, "prog")
    assert len(results) >= 1
    guids = [r["guid"] for r in results]
    assert "en-1" in guids


def test_english_no_match_returns_empty(en_db):
    """英文不相关词返回空列表。"""
    results = store.search_articles(en_db, "javascriptframework")
    assert results == []


def test_double_quote_stripped(en_db):
    """查询中的双引号被剥除，不抛异常。"""
    results = store.search_articles(en_db, '"python"')
    assert len(results) >= 1
    guids = [r["guid"] for r in results]
    assert "en-1" in guids


def test_only_quotes_returns_empty(en_db):
    """查询全是双引号，剥除后为空，返回空列表不抛异常。"""
    results = store.search_articles(en_db, '""""')
    assert results == []


def test_fts_reserved_or(zh_db):
    """FTS5 保留字 OR 作为查询不抛异常。"""
    results = store.search_articles(zh_db, "OR")
    assert isinstance(results, list)


def test_fts_reserved_and(zh_db):
    """FTS5 保留字 AND 作为查询不抛异常。"""
    results = store.search_articles(zh_db, "AND")
    assert isinstance(results, list)


def test_fts_reserved_not(zh_db):
    """FTS5 保留字 NOT 作为查询不抛异常。"""
    results = store.search_articles(zh_db, "NOT")
    assert isinstance(results, list)


def test_sql_injection_attempt(zh_db):
    """SQL 注入字符串不抛异常，返回列表。"""
    results = store.search_articles(zh_db, "'; DROP TABLE articles; --")
    assert isinstance(results, list)


def test_empty_query_returns_empty(zh_db):
    """空字符串查询返回空列表。"""
    assert store.search_articles(zh_db, "") == []


def test_whitespace_query_returns_empty(zh_db):
    """纯空白查询 strip 后为空，返回空列表。"""
    assert store.search_articles(zh_db, "   \t\n  ") == []


def test_none_query_returns_empty(zh_db):
    """None 查询返回空列表。"""
    assert store.search_articles(zh_db, None) == []


def test_results_include_feed_title(zh_db):
    """每条结果包含 feed_title 字段，值来自 feeds 表。"""
    results = store.search_articles(zh_db, "人工")
    assert len(results) >= 1
    assert results[0]["feed_title"] == "中文源"


def test_results_include_expected_fields(zh_db):
    """结果字典包含 search_articles 声明的所有列。"""
    results = store.search_articles(zh_db, "人工")
    assert len(results) >= 1
    expected_keys = {
        "id",
        "feed_id",
        "guid",
        "title",
        "author",
        "link",
        "summary",
        "content_html",
        "content_text",
        "published_at",
        "fetched_at",
        "is_read",
        "is_starred",
        "feed_title",
    }
    assert expected_keys.issubset(set(results[0].keys()))


def test_limit_caps_results(zh_db):
    """limit 参数限制返回条数。"""
    results = store.search_articles(zh_db, "智", limit=1)
    assert len(results) == 1
    assert results[0]["title"] in {"人工智能前沿", "智能制造观察"}


def test_short_query_ordered_by_published_desc(zh_db):
    """短查询（LIKE 分支）按 published_at 倒序返回。"""
    results = store.search_articles(zh_db, "智")
    assert len(results) >= 2
    dates = [r["published_at"] for r in results]
    assert dates == sorted(dates, reverse=True)


def test_fts_query_returns_matching_article(zh_db):
    """FTS 分支：查询结果非空且包含命中文章，不假设 rank 具体顺序。"""
    results = store.search_articles(zh_db, "智能制造")
    assert len(results) >= 1
    guids = [r["guid"] for r in results]
    assert "zh-2" in guids


def test_fts_query_no_false_positive(zh_db):
    """FTS 分支：不相关文章不应出现在结果里。"""
    results = store.search_articles(zh_db, "人工智能")
    guids = [r["guid"] for r in results]
    assert "zh-2" not in guids
    assert "zh-3" not in guids


def test_perf_1000_articles_under_2s(tmp_path):
    """1000 篇文章库搜索响应 < 2s（性能回归）。"""
    db_path = _make_db(tmp_path)
    store.create_feed(db_path, "http://example.com/perf")
    feed_rows = store.list_feeds(db_path)
    feed_id = feed_rows[0]["id"]
    for i in range(1000):
        store.insert_article(
            db_path,
            feed_id,
            f"perf-{i}",
            f"Performance article number {i}",
            "author",
            f"http://example.com/perf/{i}",
            "summary",
            "<p>content about benchmarking</p>",
            "content about benchmarking performance",
            "2024-03-01T00:00:00",
        )
    start = time.perf_counter()
    results = store.search_articles(db_path, "benchmarking")
    elapsed = time.perf_counter() - start
    assert len(results) >= 1
    assert elapsed < 2.0