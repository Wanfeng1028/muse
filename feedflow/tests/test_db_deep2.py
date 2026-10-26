# tests/test_db_deep2.py
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import threading

from feedflow import db as db_mod
from feedflow import store


@pytest.fixture()
def db_path(tmp_path):
    p = tmp_path / "deep2.db"
    db_mod.init_db(p)
    return p


def _make_feed(db_path, url="https://example.com/feed.xml"):
    return store.create_feed(db_path, url)


def _insert_article(db_path, feed_id, guid, title="t", text="hello world content"):
    return store.insert_article(
        db_path, feed_id, guid, title, "author", "http://x/", "sum",
        "<p>html</p>", text, None,
    )


# 测迁移幂等：重复 init_db 不报错，user_version 不变，数据不丢
def test_migration_idempotent_repeat_init(db_path):
    conn = db_mod.get_conn(db_path)
    try:
        v1 = db_mod._get_user_version(conn)
    finally:
        conn.close()
    assert v1 == len(db_mod.MIGRATIONS)

    fid = _make_feed(db_path)
    aid = _insert_article(db_path, fid, "guid-1", title="keep me")

    # 再次 init_db，应幂等
    db_mod.init_db(db_path)

    conn = db_mod.get_conn(db_path)
    try:
        v2 = db_mod._get_user_version(conn)
    finally:
        conn.close()
    assert v2 == len(db_mod.MIGRATIONS)

    # 数据仍在
    art = store.get_article(db_path, aid)
    assert art is not None
    assert art["title"] == "keep me"
    assert art["feed_id"] == fid
    _, rows = store.list_articles(db_path, scope="all")
    assert len(rows) == 1


# 测迁移幂等：手动把 user_version 回退后重跑不重复加列导致报错
def test_migration_rerun_after_version_reset(db_path):
    conn = db_mod.get_conn(db_path)
    try:
        db_mod._set_user_version(conn, 0)
        conn.commit()
    finally:
        conn.close()

    # 列已存在，但 user_version=0，重跑应跳过已存在列而非抛 duplicate column
    db_mod.init_db(db_path)

    conn = db_mod.get_conn(db_path)
    try:
        v = db_mod._get_user_version(conn)
        cols = [dict(r)["name"] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    finally:
        conn.close()
    assert v == len(db_mod.MIGRATIONS)
    assert "simhash" in cols
    assert "cluster_id" in cols
    assert "last_read_at" in cols
    assert "scroll_pos" in cols


# 测超长标题（5000 字）入库不抛异常且可读回
def test_insert_long_title_5000(db_path):
    fid = _make_feed(db_path)
    long_title = "长" * 5000
    aid = _insert_article(db_path, fid, "long-guid", title=long_title, text="body")
    art = store.get_article(db_path, aid)
    assert art is not None
    assert art["title"] == long_title
    assert len(art["title"]) == 5000


# 测 guid 为空字符串时：唯一键 (feed_id, guid) 允许第一条，第二条冲突
def test_insert_empty_guid_duplicate_behavior(db_path):
    fid = _make_feed(db_path)
    a1 = _insert_article(db_path, fid, "", title="first empty guid")
    assert a1 > 0
    # 同 feed 同空 guid 再次插入应触发 UNIQUE 冲突（sqlite3.IntegrityError）
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        _insert_article(db_path, fid, "", title="second empty guid")
    # 但不同 feed 的空 guid 可以共存
    fid2 = _make_feed(db_path, url="https://example.com/feed2.xml")
    a2 = _insert_article(db_path, fid2, "", title="other feed empty guid")
    assert a2 > 0


# 测 guid=None 时：NOT NULL 约束导致 IntegrityError
def test_insert_none_guid_raises(db_path):
    fid = _make_feed(db_path)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        _insert_article(db_path, fid, None, title="none guid")


# 测非法 published_at 入库不崩，读回保持原字符串
def test_insert_invalid_published_at(db_path):
    fid = _make_feed(db_path)
    aid = store.insert_article(
        db_path, fid, "bad-date-guid", "bad date", "a", "http://x/", "s",
        "<p>h</p>", "text", "not-a-date",
    )
    art = store.get_article(db_path, aid)
    assert art is not None
    assert art["published_at"] == "not-a-date"


# 测同一 feed 并发插入 20 篇文章无丢失
def test_concurrent_insert_20_articles(db_path):
    fid = _make_feed(db_path)
    errors = []

    def worker(i):
        try:
            _insert_article(db_path, fid, f"concurrent-{i}", title=f"t{i}", text=f"body {i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    total, rows = store.list_articles(db_path, scope="all", limit=100)
    assert total == 20
    assert len(rows) == 20
    guids = sorted(r["guid"] for r in rows)
    assert guids == sorted(f"concurrent-{i}" for i in range(20))


# 测 set_read/set_starred 对不存在 article id 不抛异常
def test_set_read_starred_nonexistent_id(db_path):
    # 不存在的 id：UPDATE 影响 0 行，不应抛异常
    store.set_read(db_path, 999999, True)
    store.set_read(db_path, 999999, False)
    store.set_starred(db_path, 999999, True)
    store.set_starred(db_path, 999999, False)
    # 数据库仍可用
    assert store.stats(db_path)["articles"] == 0


# 测删除 feed 级联清理其文章（外键 ON DELETE CASCADE + PRAGMA foreign_keys=ON）
def test_delete_feed_cascades_articles(db_path):
    fid = _make_feed(db_path)
    _insert_article(db_path, fid, "c-1")
    _insert_article(db_path, fid, "c-2")
    assert store.stats(db_path)["articles"] == 2

    # execute_write 会显式打开 foreign_keys
    ok = store.delete_feed(db_path, fid)
    assert ok is True

    total, rows = store.list_articles(db_path, scope="all")
    assert total == 0
    assert rows == []
    assert store.get_feed(db_path, fid) is None


# 测 search 对 FTS5 特殊字符（引号/星号/括号/冒号/脱字符）不 500
def test_search_special_chars_no_error(db_path):
    fid = _make_feed(db_path)
    _insert_article(db_path, fid, "s-1", title="hello world", text="some searchable body text")
    _insert_article(db_path, fid, "s-2", title="python notes", text="flask sqlite deep dive")

    for q in ['"quoted"', "star*", "(paren)", "colon:value", "^caret",
              "AND OR NOT", 'mix "a" AND (b)*', "'", "**", "((("]:
        res = store.search_articles(db_path, q, limit=50)
        assert isinstance(res, list)

    # 正常查询仍能命中
    hits = store.search_articles(db_path, "searchable", limit=50)
    assert any(h["guid"] == "s-1" for h in hits)


# 测 search 单字/双字走 LIKE 回退（trigram 无法处理 <3 字符）
def test_search_short_query_fallback_like(db_path):
    fid = _make_feed(db_path)
    _insert_article(db_path, fid, "sh-1", title="abcd", text="zzz")
    res1 = store.search_articles(db_path, "a", limit=50)
    assert any(r["guid"] == "sh-1" for r in res1)
    res2 = store.search_articles(db_path, "ab", limit=50)
    assert any(r["guid"] == "sh-2" for r in res2) or any(r["guid"] == "sh-1" for r in res2)
