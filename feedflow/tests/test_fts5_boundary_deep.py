import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from feedflow.db import get_conn
from feedflow.store import (
    _escape_fts5_query,
    insert_article,
    search_articles,
)


def _insert_feed(
    db_path, name="示例源", feed_url="https://example.com/rss", site_url="https://example.com"
):
    conn = get_conn(db_path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(feeds)").fetchall()]
        fill = {}
        for c in cols:
            if c == "id":
                continue
            if c == "name":
                fill[c] = name
            elif c == "feed_url":
                fill[c] = feed_url
            elif c == "site_url":
                fill[c] = site_url
            else:
                fill[c] = ""
        col_names = list(fill.keys())
        placeholders = ",".join("?" for _ in col_names)
        sql = f"INSERT INTO feeds ({','.join(col_names)}) VALUES ({placeholders})"
        cur = conn.execute(sql, [fill[c] for c in col_names])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _base_time():
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _insert(
    db_path,
    feed_id,
    guid,
    title,
    content_text="",
    author="",
    summary="",
    published_at=None,
    content_html="",
):
    if published_at is None:
        published_at = _iso(_base_time())
    insert_article(
        db_path,
        feed_id,
        guid,
        title,
        author,
        "https://example.com/a/" + guid,
        summary,
        content_html,
        content_text,
        published_at,
    )


# ---------------- A. 特殊字符不 500 ----------------


def test_a1_fullwidth_double_quote(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "苹果发布会回顾", content_text="“苹果发布会”现场报道")
    res = search_articles(tmp_db, "“苹果发布会”")
    assert isinstance(res, list)


def test_a2_fullwidth_single_quote(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "iPhone 使用体验", content_text="‘iPhone’ 长期使用报告")
    res = search_articles(tmp_db, "‘iPhone’")
    assert isinstance(res, list)


def test_a3_book_title_marks(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "《三体》解读", content_text="对《三体》的深度解读")
    res = search_articles(tmp_db, "《三体》解读")
    assert isinstance(res, list)


def test_a4_emoji(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "新品发布现场", content_text="🎉新品发布🎉 精彩回顾")
    res = search_articles(tmp_db, "🎉新品发布🎉")
    assert isinstance(res, list)


def test_a5_mixed_specials(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "苹果发布会价格直播", content_text="苹果发布会 价格 直播 置顶")
    res = search_articles(tmp_db, "苹果“发布会”：'价格' (直播) ^置顶^")
    assert isinstance(res, list)


# ---------------- B. 保留字与运算符退化 ----------------


def test_b1_and_operator_escaped_shape():
    assert _escape_fts5_query("apple AND orange") == '"apple" "AND" "orange"'


def test_b1b_and_operator_no_raise(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "apple 与 orange 的故事", content_text="apple AND orange 都提到了")
    res = search_articles(tmp_db, "apple AND orange")
    assert isinstance(res, list)


def test_b2_mixed_case_operators_shape():
    assert _escape_fts5_query("Apple Or ORANGE aNd") == '"Apple" "Or" "ORANGE" "aNd"'


def test_b2b_mixed_case_no_raise(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "Apple ORANGE 混排", content_text="Apple Or ORANGE aNd")
    res = search_articles(tmp_db, "Apple Or ORANGE aNd")
    assert isinstance(res, list)


def test_b3_near_alone_no_raise(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "NEAR 距离检索说明", content_text="NEAR 是 FTS5 的一个运算符")
    res = search_articles(tmp_db, "NEAR")
    assert isinstance(res, list)


def test_b4_column_prefix_colon_stripped():
    # 诚实记录：列限定语法不被支持，冒号被剥除后整体变成短语 "title苹果"。
    assert _escape_fts5_query("title:苹果") == '"title苹果"'


def test_b4b_column_prefix_no_raise(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "苹果公司财报", content_text="苹果公司季度财报发布")
    res = search_articles(tmp_db, "title:苹果")
    assert isinstance(res, list)


def test_b5_hyphen_in_phrase(tmp_db):
    assert _escape_fts5_query("iPhone-17") == '"iPhone-17"'
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "iPhone-17 开箱评测", content_text="iPhone-17 详细评测内容")
    res = search_articles(tmp_db, "iPhone-17")
    assert isinstance(res, list)
    titles = [r["title"] for r in res]
    assert "iPhone-17 开箱评测" in titles


# ---------------- C. 全特殊字符查询 ----------------


def test_c1_only_stars(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "普通文章标题", content_text="普通正文内容")
    assert _escape_fts5_query("***") == ""
    res = search_articles(tmp_db, "***")
    assert isinstance(res, list)


def test_c2_only_single_quotes(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "普通文章标题", content_text="普通正文内容")
    assert _escape_fts5_query("'''") == ""
    res = search_articles(tmp_db, "'''")
    assert isinstance(res, list)


def test_c3_only_parens(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "普通文章标题", content_text="普通正文内容")
    assert _escape_fts5_query("(((") == ""
    res = search_articles(tmp_db, "(((")
    assert isinstance(res, list)


def test_c4_single_double_quote(tmp_db):
    res = search_articles(tmp_db, '"')
    assert res == []


# ---------------- D. trigram / 长度边界 ----------------


def test_d1_two_char_like_path(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "AI 芯片新突破", content_text="AI 芯片领域取得新突破")
    res = search_articles(tmp_db, "AI")
    assert isinstance(res, list)
    titles = [r["title"] for r in res]
    assert "AI 芯片新突破" in titles


def test_d2_three_char_cjk_fts(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "前沿科技观察", content_text="人工智能正在改变世界")
    res = search_articles(tmp_db, "人工智")
    assert isinstance(res, list)
    assert len(res) >= 1
    assert any("人工智能" in (r["content_text"] or "") for r in res)


def test_d3_very_long_query(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "苹果相关文章", content_text="苹果 相关 内容")
    res = search_articles(tmp_db, "苹果" * 700)
    assert isinstance(res, list)


def test_d4_mixed_cjk_ascii(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "苹果 iPhone 17 发布", content_text="苹果 iPhone 17 正式发布")
    res = search_articles(tmp_db, "苹果 iPhone 17 发布")
    assert isinstance(res, list)


# ---------------- E. 回退路径 ----------------


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, first_raises=True):
        self._first_raises = first_raises
        self._calls = 0

    def execute(self, sql, params=()):
        self._calls += 1
        if self._first_raises and self._calls == 1:
            raise sqlite3.OperationalError("mock match failure")
        return _FakeCursor([])

    def close(self):
        pass


def test_e1_match_operational_error_fallback(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "量子计算前沿", content_text="量子计算相关研究进展")
    fake = _FakeConn(first_raises=True)
    with patch("feedflow.store.get_conn", return_value=fake):
        res = search_articles(tmp_db, "量子计算")
    assert isinstance(res, list)
    # mock 的 LIKE 分支返回空列表，因此这里应为空
    assert res == []


def test_e2_like_path_ordering_desc(tmp_db):
    fid = _insert_feed(tmp_db)
    old_time = _iso(_base_time() - timedelta(days=10))
    new_time = _iso(_base_time())
    _insert(
        tmp_db, fid, "g_old", "量子计算旧文", content_text="量子计算早期探索", published_at=old_time
    )
    _insert(
        tmp_db, fid, "g_new", "量子计算新文", content_text="量子计算最新进展", published_at=new_time
    )
    res = search_articles(tmp_db, "量子")
    assert isinstance(res, list)
    assert len(res) == 2
    assert res[0]["guid"] == "g_new"
    assert res[1]["guid"] == "g_old"


# ---------------- F. limit / 未命中 / 大小写 ----------------


def test_f1_limit_respected(tmp_db):
    fid = _insert_feed(tmp_db)
    for i in range(5):
        _insert(
            tmp_db,
            fid,
            f"g{i}",
            f"新能源行业观察第{i}期",
            content_text="新能源 行业 观察",
            published_at=_iso(_base_time() + timedelta(minutes=i)),
        )
    res = search_articles(tmp_db, "新能源", limit=2)
    assert isinstance(res, list)
    assert len(res) == 2


def test_f2_no_match_returns_empty(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "某篇文章标题", content_text="某段正文内容")
    res = search_articles(tmp_db, "不存在的词XYZ123")
    assert res == []


def test_f3_case_insensitive(tmp_db):
    fid = _insert_feed(tmp_db)
    _insert(tmp_db, fid, "g1", "Python 性能优化", content_text="Python 性能优化技巧分享")
    res = search_articles(tmp_db, "python")
    assert isinstance(res, list)
    assert len(res) >= 1
    assert any("Python" in (r["title"] or "") for r in res)
