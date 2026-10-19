import time
from datetime import UTC, datetime, timedelta

import pytest

from feedflow import opml, scheduler, store
from feedflow.db import execute_write, get_conn


def _iso_minutes_ago(minutes: float) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _iso_seconds_ago(seconds: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _insert_feed(db_path, title, feed_url, *, interval_min=0, last_fetched_at=None,
                 enabled=1, position=0, folder_id=None):
    created = datetime.now(UTC).isoformat()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, ?, ?)",
            (title, feed_url, position, created),
        )
        feed_id = cur.lastrowid
        conn.execute(
            "UPDATE feeds SET interval_min = ?, last_fetched_at = ?, enabled = ?, folder_id = ? WHERE id = ?",
            (interval_min, last_fetched_at, enabled, folder_id, feed_id),
        )
        conn.commit()
    return feed_id


def _count_feeds(db_path):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM feeds").fetchone()
    return row["n"]


def _list_feeds(db_path):
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM feeds").fetchall()
    return [dict(r) for r in rows]


def _list_folders(db_path):
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM folders").fetchall()
    return [dict(r) for r in rows]


def _get_feed_by_url(db_path, feed_url):
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM feeds WHERE feed_url = ?", (feed_url,)).fetchone()
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# OPML
# ---------------------------------------------------------------------------

def test_outline_with_xmlurl_and_children_children_dropped(tmp_db):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>t</title></head>
  <body>
    <outline text="Parent" type="rss" xmlUrl="http://parent.example/feed">
      <outline text="Child" type="rss" xmlUrl="http://child.example/feed"/>
    </outline>
  </body>
</opml>
"""
    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 1
    assert _count_feeds(tmp_db) == 1

    parent = _get_feed_by_url(tmp_db, "http://parent.example/feed")
    assert parent is not None

    child = _get_feed_by_url(tmp_db, "http://child.example/feed")
    assert child is None


def test_empty_xmlurl_treated_as_folder(tmp_db):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>t</title></head>
  <body>
    <outline text="G" xmlUrl="">
      <outline text="Child Feed" type="rss" xmlUrl="http://child.example/feed"/>
    </outline>
  </body>
</opml>
"""
    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 1

    folders = _list_folders(tmp_db)
    assert len(folders) == 1
    assert folders[0]["name"] == "G"

    child = _get_feed_by_url(tmp_db, "http://child.example/feed")
    assert child is not None
    assert child["folder_id"] == folders[0]["id"]


def test_source_outline_without_title_falls_back_to_feed_url(tmp_db):
    bad_url = "not a url at all !!!"
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>t</title></head>
  <body>
    <outline type="rss" xmlUrl="not a url at all !!!"/>
  </body>
</opml>
"""
    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 1
    assert result["skipped"] == 0

    feed = _get_feed_by_url(tmp_db, bad_url)
    assert feed is not None
    assert feed["title"] == bad_url


def test_export_folder_name_with_xml_special_chars(tmp_db):
    folder_id = store.create_folder(tmp_db, "A&B<C>")
    _insert_feed(tmp_db, "Feed1", "http://example.com/feed", folder_id=folder_id)

    out = opml.export_opml(tmp_db)

    assert "A&amp;B&lt;C&gt;" in out
    root = __import__("xml.etree.ElementTree", fromlist=["fromstring"]).fromstring(out)
    assert root.tag == "opml"
    texts = [o.get("text") for o in root.iter("outline")]
    assert "A&B<C>" in texts


def test_folder_names_are_case_sensitive(tmp_db):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>t</title></head>
  <body>
    <outline text="Tech">
      <outline text="F1" type="rss" xmlUrl="http://a.example/feed"/>
    </outline>
    <outline text="tech">
      <outline text="F2" type="rss" xmlUrl="http://b.example/feed"/>
    </outline>
  </body>
</opml>
"""
    result = opml.import_opml(tmp_db, xml)
    assert result["imported"] == 2

    folders = _list_folders(tmp_db)
    names = sorted(f["name"] for f in folders)
    assert names == ["Tech", "tech"]
    assert len(folders) == 2


def test_import_opml_returns_exactly_two_keys(tmp_db):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0"><head></head><body></body></opml>
"""
    result = opml.import_opml(tmp_db, xml)
    assert set(result.keys()) == {"imported", "skipped"}


# ---------------------------------------------------------------------------
# scheduler
# ---------------------------------------------------------------------------

def test_run_tick_fetch_exception_does_not_propagate_and_state_written(tmp_db, monkeypatch):
    _insert_feed(tmp_db, "F1", "http://one.example/feed", last_fetched_at=None, enabled=1)
    _insert_feed(tmp_db, "F2", "http://two.example/feed", last_fetched_at=None, enabled=1)

    calls = {"n": 0}

    def fake_fetch_feed(db_path, feed, user_agent, timeout=None, retries=None,
                        extract_timeout=None, dead_after=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {"status": "ok", "added": 0, "error": ""}

    monkeypatch.setattr("feedflow.scheduler.fetcher.fetch_feed", fake_fetch_feed)

    scheduler._run_tick(tmp_db, 30, "UA", 5, 0, 5)

    assert calls["n"] == 2

    last_tick = scheduler._job_state_get(tmp_db, "last_tick_at")
    last_success = scheduler._job_state_get(tmp_db, "last_success_at")
    assert last_tick
    assert last_success


def test_due_feeds_interval_zero_falls_back_to_default(tmp_db):
    _insert_feed(
        tmp_db, "A", "http://a.example/feed",
        interval_min=0, last_fetched_at=_iso_minutes_ago(40), enabled=1,
    )
    _insert_feed(
        tmp_db, "B", "http://b.example/feed",
        interval_min=0, last_fetched_at=_iso_minutes_ago(10), enabled=1,
    )

    due = store.due_feeds(tmp_db, scheduler._utcnow_iso(), 30)
    urls = {f["feed_url"] for f in due}

    assert "http://a.example/feed" in urls
    assert "http://b.example/feed" not in urls


def test_due_feeds_invalid_last_fetched_at_included(tmp_db):
    _insert_feed(
        tmp_db, "Bad", "http://bad.example/feed",
        interval_min=30, last_fetched_at="garbage", enabled=1,
    )

    due = store.due_feeds(tmp_db, scheduler._utcnow_iso(), 30)
    urls = {f["feed_url"] for f in due}
    assert "http://bad.example/feed" in urls


def test_due_feeds_invalid_now_iso_does_not_raise(tmp_db):
    _insert_feed(
        tmp_db, "X", "http://x.example/feed",
        interval_min=30, last_fetched_at=_iso_minutes_ago(120), enabled=1,
    )

    due = store.due_feeds(tmp_db, "not-a-time", 30)
    assert isinstance(due, list)


def test_start_scheduler_catchup_when_stale(tmp_db, app, monkeypatch):
    scheduler._job_state_set(tmp_db, "last_tick_at", _iso_seconds_ago(200))

    calls = {"n": 0}

    def fake_run_tick(*args, **kwargs):
        calls["n"] += 1

    monkeypatch.setattr(scheduler, "_run_tick", fake_run_tick)

    started = None
    try:
        started = scheduler.start_scheduler(app)
        assert calls["n"] >= 1
    finally:
        scheduler.shutdown_scheduler()

    assert started is not None


def test_start_scheduler_no_catchup_when_recent(tmp_db, app, monkeypatch):
    scheduler._job_state_set(tmp_db, "last_tick_at", _iso_seconds_ago(10))

    calls = {"n": 0}

    def fake_run_tick(*args, **kwargs):
        calls["n"] += 1

    monkeypatch.setattr(scheduler, "_run_tick", fake_run_tick)

    try:
        scheduler.start_scheduler(app)
        assert calls["n"] == 0
    finally:
        scheduler.shutdown_scheduler()


def test_shutdown_scheduler_without_scheduler_does_not_raise():
    scheduler.shutdown_scheduler()
    scheduler.shutdown_scheduler()
