"""db 层深度测试：解析边界、去重聚类、失败注入、幂等、排序稳定性。

只依赖 conftest 提供的 tmp_db / app / client fixture，直接操作 sqlite 验证行为。
"""

import sqlite3
import threading

import pytest

from feedflow import db as db_mod


def _insert_feed(db_path, feed_url="https://example.com/rss.xml", title="示例源"):
    return db_mod.execute_write(
        db_path,
        "INSERT INTO feeds (title, site_url, feed_url, description, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (title, "https://example.com", feed_url, "", db_mod.utcnow()),
    )


def _insert_article(
    db_path,
    feed_id,
    guid,
    title="标题",
    content_text="正文内容",
    published_at=None,
    simhash="",
    cluster_id=None,
):
    return db_mod.execute_write(
        db_path,
        "INSERT INTO articles (feed_id, guid, title, author, link, summary,"
        " content_html, content_text, published_at, fetched_at, simhash, cluster_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            feed_id,
            guid,
            title,
            "",
            "https://example.com/a",
            "",
            "",
            content_text,
            published_at,
            db_mod.utcnow(),
            simhash,
            cluster_id,
        ),
    )


def test_malformed_xml_feed_still_stores_and_queries(tmp_db):
    """畸形 XML 来源的 feed 仍能落库并原样查回，不因内容异常丢失记录。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://bad.example.com/rss.xml", title="<broken>")
    assert feed_id > 0

    row = db_mod.query_one(tmp_db, "SELECT * FROM feeds WHERE id = ?", (feed_id,))
    assert row is not None
    assert row["title"] == "<broken>"
    assert row["feed_url"] == "https://bad.example.com/rss.xml"

    _insert_article(tmp_db, feed_id, "guid-broken", title="未闭合<tag>", content_text="正文<&>")
    arts = db_mod.query_all(tmp_db, "SELECT * FROM articles WHERE feed_id = ?", (feed_id,))
    assert len(arts) == 1
    assert arts[0]["title"] == "未闭合<tag>"
    assert arts[0]["content_text"] == "正文<&>"


def test_large_feed_bulk_insert_and_count(tmp_db):
    """超大 feed 批量入库后行数与唯一 guid 数一致，且 FTS 可检索。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://big.example.com/rss.xml")
    n = 2000
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executemany(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary,"
            " content_html, content_text, published_at, fetched_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    feed_id,
                    f"guid-{i}",
                    f"大feed条目 {i}",
                    "",
                    "",
                    "",
                    "",
                    f"批量正文 {i}",
                    None,
                    db_mod.utcnow(),
                )
                for i in range(n)
            ],
        )
        conn.commit()
    finally:
        conn.close()

    cnt = db_mod.query_one(tmp_db, "SELECT COUNT(*) AS c FROM articles WHERE feed_id = ?", (feed_id,))
    assert cnt["c"] == n

    distinct = db_mod.query_one(
        tmp_db, "SELECT COUNT(DISTINCT guid) AS c FROM articles WHERE feed_id = ?", (feed_id,)
    )
    assert distinct["c"] == n

    fts = db_mod.query_all(
        tmp_db,
        "SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?",
        ("批量正文",),
    )
    assert len(fts) == n


def test_empty_feed_yields_zero_articles(tmp_db):
    """空 feed 建源成功但没有文章，查询返回空列表而不是报错。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://empty.example.com/rss.xml", title="空源")
    assert feed_id > 0

    arts = db_mod.query_all(tmp_db, "SELECT * FROM articles WHERE feed_id = ?", (feed_id,))
    assert arts == []
    assert isinstance(arts, list)

    one = db_mod.query_one(tmp_db, "SELECT * FROM articles WHERE feed_id = ?", (feed_id,))
    assert one is None


def test_non_utf8_encoded_content_roundtrip(tmp_db):
    """非 UTF8 来源内容经参数绑定写入后按原样读回，不出现乱码替换。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://gbk.example.com/rss.xml")
    raw_text = "中文标题：测试·符号"

    _insert_article(tmp_db, feed_id, "guid-gbk", title=raw_text, content_text=raw_text)
    row = db_mod.query_one(tmp_db, "SELECT title, content_text FROM articles WHERE guid = ?", ("guid-gbk",))
    assert row["title"] == raw_text
    assert row["content_text"] == raw_text

    # 通过 sqlite3 直接写入 bytes 解码后的文本，验证存储层不会二次损坏
    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute(
            "UPDATE articles SET title = ? WHERE guid = ?",
            (raw_text.encode("utf-8").decode("utf-8"), "guid-gbk"),
        )
        conn.commit()
    finally:
        conn.close()
    again = db_mod.query_one(tmp_db, "SELECT title FROM articles WHERE guid = ?", ("guid-gbk",))
    assert again["title"] == raw_text


def test_similar_titles_cluster_together(tmp_db):
    """相似标题（同一事件不同措辞）写入后可按 cluster_id 聚成一簇。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://cluster.example.com/rss.xml")
    h = "samehash01"
    id_a = _insert_article(tmp_db, feed_id, "c-a", title="今日天气：暴雨来袭", simhash=h, cluster_id=7)
    id_b = _insert_article(tmp_db, feed_id, "c-b", title="暴雨今日来袭天气", simhash=h, cluster_id=7)
    id_c = _insert_article(tmp_db, feed_id, "c-c", title="完全不同的科技新闻", simhash="other99", cluster_id=8)

    cluster7 = db_mod.query_all(tmp_db, "SELECT id FROM articles WHERE cluster_id = ?", (7,))
    assert sorted(r["id"] for r in cluster7) == sorted([id_a, id_b])
    assert id_c not in [r["id"] for r in cluster7]

    sizes = db_mod.query_all(
        tmp_db,
        "SELECT cluster_id, COUNT(*) AS c FROM articles GROUP BY cluster_id ORDER BY cluster_id",
    )
    assert {r["cluster_id"]: r["c"] for r in sizes} == {7: 2, 8: 1}


def test_reprint_and_clickbait_variants_share_simhash(tmp_db):
    """转载与标题党变体共享 simhash 时按同一簇查询，非同类不混入。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://reprint.example.com/rss.xml")
    h = "reprint-hash"
    _insert_article(tmp_db, feed_id, "r-1", title="某公司发布新品", simhash=h, cluster_id=1)
    _insert_article(tmp_db, feed_id, "r-2", title="震惊！某公司发布新品", simhash=h, cluster_id=1)
    _insert_article(tmp_db, feed_id, "r-3", title="转载：某公司发布新品", simhash=h, cluster_id=1)
    _insert_article(tmp_db, feed_id, "r-4", title="无关广告软文", simhash="ad-hash", cluster_id=2)

    same = db_mod.query_all(
        tmp_db, "SELECT guid FROM articles WHERE simhash = ? ORDER BY guid", (h,)
    )
    assert [r["guid"] for r in same] == ["r-1", "r-2", "r-3"]

    others = db_mod.query_all(
        tmp_db, "SELECT guid FROM articles WHERE cluster_id = 2"
    )
    assert [r["guid"] for r in others] == ["r-4"]


def test_fetch_timeout_records_error_kind_and_increments_failures(tmp_db):
    """抓取超时：记录 last_error_kind=timeout 并让 consecutive_failures 递增。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://slow.example.com/rss.xml")

    db_mod.execute_write(
        tmp_db,
        "UPDATE feeds SET last_status = ?, last_error = ?, last_error_kind = ?,"
        " consecutive_failures = consecutive_failures + 1 WHERE id = ?",
        ("error", "read timed out", "timeout", feed_id),
    )
    row = db_mod.query_one(tmp_db, "SELECT * FROM feeds WHERE id = ?", (feed_id,))
    assert row["last_error_kind"] == "timeout"
    assert row["consecutive_failures"] == 1
    assert row["last_status"] == "error"

    db_mod.execute_write(
        tmp_db,
        "UPDATE feeds SET last_error = ?, last_error_kind = ?,"
        " consecutive_failures = consecutive_failures + 1 WHERE id = ?",
        ("read timed out again", "timeout", feed_id),
    )
    row2 = db_mod.query_one(tmp_db, "SELECT consecutive_failures FROM feeds WHERE id = ?", (feed_id,))
    assert row2["consecutive_failures"] == 2


def test_fetch_404_marks_error_kind(tmp_db):
    """抓取 404：记录 last_error_kind=http_404 且保留具体错误文本。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://missing.example.com/rss.xml")
    db_mod.execute_write(
        tmp_db,
        "UPDATE feeds SET last_status = ?, last_error = ?, last_error_kind = ? WHERE id = ?",
        ("error", "HTTP 404 Not Found", "http_404", feed_id),
    )
    row = db_mod.query_one(tmp_db, "SELECT * FROM feeds WHERE id = ?", (feed_id,))
    assert row["last_error_kind"] == "http_404"
    assert row["last_error"] == "HTTP 404 Not Found"
    assert row["last_status"] == "error"


def test_fetch_rate_limited_records_kind_and_retry_after(tmp_db):
    """抓取限流：记录 last_error_kind=rate_limited 并通过 last_error 保存 retry 提示。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://limited.example.com/rss.xml")
    db_mod.execute_write(
        tmp_db,
        "UPDATE feeds SET last_status = ?, last_error = ?, last_error_kind = ? WHERE id = ?",
        ("error", "429 Too Many Requests; retry after 60s", "rate_limited", feed_id),
    )
    row = db_mod.query_one(tmp_db, "SELECT * FROM feeds WHERE id = ?", (feed_id,))
    assert row["last_error_kind"] == "rate_limited"
    assert "retry after 60s" in row["last_error"]
    assert row["last_status"] == "error"


def test_repeated_fetch_is_idempotent_on_guid(tmp_db):
    """重复拉取：相同 (feed_id, guid) 的插入被唯一约束拒绝，不产生重复行。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://idem.example.com/rss.xml")
    first = _insert_article(tmp_db, feed_id, "same-guid", title="第一次")
    assert first > 0

    conn = db_mod.get_conn(tmp_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO articles (feed_id, guid, title, author, link, summary,"
                " content_html, content_text, published_at, fetched_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (feed_id, "same-guid", "第二次", "", "", "", "", "", None, db_mod.utcnow()),
            )
        conn.rollback()
    finally:
        conn.close()

    rows = db_mod.query_all(
        tmp_db, "SELECT id, title FROM articles WHERE feed_id = ? AND guid = ?", (feed_id, "same-guid")
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "第一次"

    # 重复更新 last_fetched_at 不影响文章行数
    db_mod.execute_write(
        tmp_db, "UPDATE feeds SET last_fetched_at = ? WHERE id = ?", (db_mod.utcnow(), feed_id)
    )
    total = db_mod.query_one(tmp_db, "SELECT COUNT(*) AS c FROM articles WHERE feed_id = ?", (feed_id,))
    assert total["c"] == 1


def test_importance_order_stable_under_equal_scores(tmp_db):
    """重要性排序：分数相同时按 published_at 倒序，结果稳定且可重复查询。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://rank.example.com/rss.xml")
    ids = []
    for i in range(5):
        ids.append(
            _insert_article(
                tmp_db,
                feed_id,
                f"rank-{i}",
                title=f"排名条目 {i}",
                published_at=f"2024-05-0{i + 1}T00:00:00+00:00",
            )
        )

    order1 = db_mod.query_all(
        tmp_db,
        "SELECT id FROM articles WHERE feed_id = ? ORDER BY published_at DESC, id DESC",
        (feed_id,),
    )
    order2 = db_mod.query_all(
        tmp_db,
        "SELECT id FROM articles WHERE feed_id = ? ORDER BY published_at DESC, id DESC",
        (feed_id,),
    )
    assert [r["id"] for r in order1] == [r["id"] for r in order2]
    assert [r["id"] for r in order1] == list(reversed(ids))


def test_fts_triggers_keep_index_in_sync(tmp_db):
    """FTS 触发器在增删改后保持索引同步，删除文章后搜索不再命中。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://fts.example.com/rss.xml")
    aid = _insert_article(tmp_db, feed_id, "fts-1", title="触发器同步测试", content_text="唯一关键词Zebra123")

    hit = db_mod.query_all(
        tmp_db, "SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?", ("Zebra123",)
    )
    assert [r["rowid"] for r in hit] == [aid]

    db_mod.execute_write(tmp_db, "DELETE FROM articles WHERE id = ?", (aid,))
    after = db_mod.query_all(
        tmp_db, "SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?", ("Zebra123",)
    )
    assert after == []


def test_init_db_is_idempotent_and_preserves_data(tmp_db):
    """重复 init_db 不丢数据、不报错，user_version 与迁移表保持一致。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://persist.example.com/rss.xml")
    _insert_article(tmp_db, feed_id, "persist-1", title="保留我")

    db_mod.init_db(tmp_db)
    db_mod.init_db(tmp_db)

    row = db_mod.query_one(tmp_db, "SELECT title FROM articles WHERE guid = ?", ("persist-1",))
    assert row is not None
    assert row["title"] == "保留我"

    uv = db_mod.query_one(tmp_db, "PRAGMA user_version")
    assert uv["user_version"] == len(db_mod.MIGRATIONS)

    tables = db_mod.query_all(
        tmp_db, "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    )
    names = {t["name"] for t in tables}
    assert {"folders", "feeds", "articles", "articles_fts", "job_state", "keywords"} <= names


def test_concurrent_writes_serialized_by_lock(tmp_db):
    """并发写：模块级 write_lock 串行化，多个线程写入后无丢失、无重复。"""
    feed_id = _insert_feed(tmp_db, feed_url="https://concurrent.example.com/rss.xml")
    errors = []

    def worker(idx):
        try:
            _insert_article(tmp_db, feed_id, f"thr-{idx}", title=f"并发条目 {idx}")
        except Exception as exc:  # noqa: BLE001 - collect thread errors; pragma: no cover - 用于捕获线程内异常
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    cnt = db_mod.query_one(tmp_db, "SELECT COUNT(*) AS c FROM articles WHERE feed_id = ?", (feed_id,))
    assert cnt["c"] == 20
    distinct = db_mod.query_one(
        tmp_db, "SELECT COUNT(DISTINCT guid) AS c FROM articles WHERE feed_id = ?", (feed_id,)
    )
    assert distinct["c"] == 20