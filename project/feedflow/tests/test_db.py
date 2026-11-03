import sqlite3
from datetime import UTC, datetime, timedelta

import pytest


def _iso(dt):
    return dt.isoformat()


def _now():
    return datetime.now(UTC)


@pytest.fixture
def tmp_db(tmp_path):
    from feedflow import db as dbmod
    db_path = str(tmp_path / "test.db")
    dbmod.init_db(db_path)
    return db_path


def _all_tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def test_tables_and_fts_exist(tmp_db):
    names = _all_tables(tmp_db)
    for t in ("folders", "feeds", "articles", "articles_fts"):
        assert t in names, f"missing table {t}"


def test_folder_crud_and_delete_sets_null(tmp_db):
    from feedflow import store
    fid = store.create_folder(tmp_db, "News")
    assert isinstance(fid, int)
    folders = store.list_folders(tmp_db)
    assert len(folders) == 1
    assert folders[0]["name"] == "News"

    store.rename_folder(tmp_db, fid, "World")
    folders = store.list_folders(tmp_db)
    assert folders[0]["name"] == "World"

    feed_id = store.create_feed(tmp_db, "https://example.com/a.xml", folder_id=fid)
    assert feed_id > 0
    f = store.get_feed(tmp_db, feed_id)
    assert f["folder_id"] == fid

    store.delete_folder(tmp_db, fid)
    f = store.get_feed(tmp_db, feed_id)
    assert f["folder_id"] is None
    assert store.list_folders(tmp_db) == []


def test_feed_unique_and_cascade(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed.xml")
    assert fid > 0

    with pytest.raises(sqlite3.IntegrityError):
        conn = sqlite3.connect(tmp_db)
        try:
            conn.execute(
                "INSERT INTO feeds (title, site_url, feed_url, description, created_at) "
                "VALUES ('x','','https://example.com/feed.xml','','2020-01-01T00:00:00+00:00')"
            )
            conn.commit()
        finally:
            conn.close()

    aid = store.insert_article(
        tmp_db, fid, "g1", "Title", "Author", "https://example.com/1",
        "sum", "<p>html</p>", "text body", _iso(_now())
    )
    assert aid > 0
    assert store.get_article(tmp_db, aid) is not None

    store.delete_feed(tmp_db, fid)
    assert store.get_feed(tmp_db, fid) is None
    assert store.get_article(tmp_db, aid) is None


def test_feed_update(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed2.xml")
    store.update_feed(tmp_db, fid, title="NewTitle", enabled=0, interval_min=15)
    f = store.get_feed(tmp_db, fid)
    assert f["title"] == "NewTitle"
    assert f["enabled"] == 0
    assert f["interval_min"] == 15


def test_fts_insert_and_search(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed3.xml")
    store.insert_article(
        tmp_db, fid, "g1", "Hello World", "Alice",
        "https://example.com/1", "summary", "<p>c</p>",
        "unique keyword zephyrix appears here", _iso(_now())
    )
    results = store.search_articles(tmp_db, "zephyrix")
    assert len(results) == 1
    assert results[0]["title"] == "Hello World"

    conn = sqlite3.connect(tmp_db)
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0]
    finally:
        conn.close()
    assert cnt >= 1


def test_fts_update_sync(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed4.xml")
    aid = store.insert_article(
        tmp_db, fid, "g1", "OldTitle", "A",
        "https://example.com/1", "s", "<p>x</p>",
        "alpha omega", _iso(_now())
    )
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("UPDATE articles SET title='NewTitle' WHERE id=?", (aid,))
        conn.commit()
    finally:
        conn.close()
    results = store.search_articles(tmp_db, "NewTitle")
    assert len(results) == 1
    assert results[0]["title"] == "NewTitle"
    old = store.search_articles(tmp_db, "OldTitle")
    assert old == []


def test_fts_delete_sync(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed5.xml")
    aid = store.insert_article(
        tmp_db, fid, "g1", "ToDelete", "A",
        "https://example.com/1", "s", "<p>x</p>",
        "deletekeyword", _iso(_now())
    )
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("DELETE FROM articles WHERE id=?", (aid,))
        conn.commit()
        cnt = conn.execute("SELECT COUNT(*) FROM articles_fts WHERE rowid=?", (aid,)).fetchone()[0]
    finally:
        conn.close()
    assert cnt == 0


def test_list_articles_scope_and_pagination(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed6.xml")
    base = _now()
    for i in range(5):
        aid = store.insert_article(
            tmp_db, fid, f"g{i}", f"Title{i}", "A",
            f"https://example.com/{i}", "s", "<p>x</p>",
            f"body{i}", _iso(base - timedelta(hours=i))
        )
        if i < 2:
            store.set_read(tmp_db, aid, 1)
    total, _arts = store.list_articles(tmp_db, scope="unread", limit=10, offset=0)
    assert total == 3
    assert len(_arts) == 3
    assert all(a["is_read"] == 0 for a in _arts)

    total, _arts = store.list_articles(tmp_db, scope="all", limit=2, offset=0)
    assert total == 5
    assert len(_arts) == 2

    total, _arts = store.list_articles(tmp_db, scope="all", limit=2, offset=2)
    assert total == 5
    assert len(_arts) == 2


def test_mark_all_read(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed7.xml")
    for i in range(3):
        store.insert_article(
            tmp_db, fid, f"g{i}", f"T{i}", "A",
            f"https://example.com/{i}", "s", "<p>x</p>", "b", _iso(_now())
        )
    store.mark_all_read(tmp_db, feed_id=fid, scope="unread")
    total, _arts = store.list_articles(tmp_db, scope="unread", feed_id=fid)
    assert total == 0


def test_stats(tmp_db):
    from feedflow import store
    fid = store.create_feed(tmp_db, "https://example.com/feed8.xml")
    a1 = store.insert_article(
        tmp_db, fid, "g1", "T1", "A",
        "https://example.com/1", "s", "<p>x</p>", "b", _iso(_now())
    )
    store.insert_article(
        tmp_db, fid, "g2", "T2", "A",
        "https://example.com/2", "s", "<p>x</p>", "b", _iso(_now())
    )
    store.set_read(tmp_db, a1, 1)
    store.set_starred(tmp_db, a1, 1)
    s = store.stats(tmp_db)
    assert s["feeds"] == 1
    assert s["articles"] == 2
    assert s["unread"] == 1
    assert s["starred"] == 1
    assert s["today_added"] == 2
    assert len(s["per_feed"]) == 1
    assert s["per_feed"][0]["unread"] == 1


def test_due_feeds(tmp_db):
    from feedflow import store
    f1 = store.create_feed(tmp_db, "https://example.com/due1.xml")
    f2 = store.create_feed(tmp_db, "https://example.com/due2.xml")
    store.update_feed(tmp_db, f2, enabled=0)

    now = _now()
    due = store.due_feeds(tmp_db, _iso(now), 30)
    ids = {d["id"] for d in due}
    assert f1 in ids
    assert f2 not in ids

    store.set_fetch_result(tmp_db, f1, "ok", "", "", "")
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "UPDATE feeds SET last_fetched_at=? WHERE id=?",
            (_iso(now - timedelta(minutes=5)), f1),
        )
        conn.commit()
    finally:
        conn.close()
    due = store.due_feeds(tmp_db, _iso(now), 30)
    ids = {d["id"] for d in due}
    assert f1 not in ids

    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "UPDATE feeds SET last_fetched_at=? WHERE id=?",
            (_iso(now - timedelta(minutes=45)), f1),
        )
        conn.commit()
    finally:
        conn.close()
    due = store.due_feeds(tmp_db, _iso(now), 30)
    ids = {d["id"] for d in due}
    assert f1 in ids
