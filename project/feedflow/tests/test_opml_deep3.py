from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from feedflow import db, opml, store


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "feedflow.db"
    db.init_db(db_path)
    return db_path


def _insert_feed(db_path, folder_id, title, feed_url, site_url=""):
    db.execute_write(
        db_path,
        "INSERT INTO feeds (folder_id, title, site_url, feed_url, description,"
        " interval_min, enabled, position, created_at)"
        " VALUES (?, ?, ?, ?, ?, 0, 1, 0, ?)",
        (folder_id, title, site_url, feed_url, "", db.utcnow()),
    )


def _feed_by_url(db_path, feed_url):
    rows = store.list_feeds(db_path)
    for row in rows:
        if row["feed_url"] == feed_url:
            return row
    return None


def test_export_empty_db_valid_xml(tmp_db):
    text = opml.export_opml(tmp_db)
    root = ET.fromstring(text)
    assert root.tag == "opml"
    assert root.get("version") == "2.0"
    head = root.find("head")
    assert head is not None
    title = head.find("title")
    assert title is not None
    assert title.text == "FeedFlow 订阅导出"
    body = root.find("body")
    assert body is not None
    assert body.findall("outline") == []


def test_export_feed_title_special_chars_escaped(tmp_db):
    _insert_feed(tmp_db, None, "A&B <C>", "http://example.com/feed", "http://example.com")
    text = opml.export_opml(tmp_db)
    assert "A&amp;B &lt;C&gt;" in text
    root = ET.fromstring(text)
    body = root.find("body")
    outlines = body.findall("outline")
    assert len(outlines) == 1
    assert outlines[0].get("text") == "A&B <C>"


def test_export_folder_without_feeds_present(tmp_db):
    store.create_folder(tmp_db, "空分组")
    text = opml.export_opml(tmp_db)
    root = ET.fromstring(text)
    body = root.find("body")
    outlines = body.findall("outline")
    assert len(outlines) == 1
    assert outlines[0].get("text") == "空分组"
    assert outlines[0].findall("outline") == []


def test_export_none_site_url_empty_htmlurl(tmp_db):
    _insert_feed(tmp_db, None, "源", "http://example.com/f", "")
    text = opml.export_opml(tmp_db)
    root = ET.fromstring(text)
    outline = root.find("body").find("outline")
    assert outline.get("htmlUrl") == ""


def test_export_date_created_present(tmp_db):
    text = opml.export_opml(tmp_db)
    root = ET.fromstring(text)
    date_el = root.find("head").find("dateCreated")
    assert date_el is not None
    assert date_el.text
    parsed = datetime.fromisoformat(date_el.text)
    assert parsed.tzinfo is not None


def test_import_malformed_xml_zeros(tmp_db):
    result = opml.import_opml(tmp_db, "<opml><broken")
    assert result == {"imported": 0, "skipped": 0}


def test_import_no_body_zeros(tmp_db):
    xml = '<opml version="2.0"><head><title>x</title></head></opml>'
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 0, "skipped": 0}


def test_import_nested_folders(tmp_db):
    xml = (
        '<opml version="2.0"><body>'
        '<outline text="外层">'
        '<outline text="内层">'
        '<outline text="源" type="rss" xmlUrl="http://example.com/nested"/>'
        "</outline>"
        "</outline>"
        "</body></opml>"
    )
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 1, "skipped": 0}
    folders = store.list_folders(tmp_db)
    inner = [f for f in folders if f["name"] == "内层"]
    assert len(inner) == 1
    feed = _feed_by_url(tmp_db, "http://example.com/nested")
    assert feed is not None
    assert feed["folder_id"] == inner[0]["id"]


def test_import_duplicate_url(tmp_db):
    xml = (
        '<opml version="2.0"><body>'
        '<outline text="A" type="rss" xmlUrl="http://example.com/dup"/>'
        '<outline text="B" type="rss" xmlUrl="http://example.com/dup"/>'
        "</body></opml>"
    )
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 1, "skipped": 1}


def test_import_same_folder_name_once(tmp_db):
    xml = (
        '<opml version="2.0"><body>'
        '<outline text="同组">'
        '<outline text="源1" type="rss" xmlUrl="http://example.com/one"/>'
        "</outline>"
        '<outline text="同组">'
        '<outline text="源2" type="rss" xmlUrl="http://example.com/two"/>'
        "</outline>"
        "</body></opml>"
    )
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 2, "skipped": 0}
    folders = store.list_folders(tmp_db)
    assert len(folders) == 1
    fid = folders[0]["id"]
    f1 = _feed_by_url(tmp_db, "http://example.com/one")
    f2 = _feed_by_url(tmp_db, "http://example.com/two")
    assert f1["folder_id"] == fid
    assert f2["folder_id"] == fid


def test_import_empty_folder_name_ungrouped(tmp_db):
    xml = (
        '<opml version="2.0"><body>'
        "<outline>"
        '<outline text="源" type="rss" xmlUrl="http://example.com/u"/>'
        "</outline>"
        "</body></opml>"
    )
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 1, "skipped": 0}
    feed = _feed_by_url(tmp_db, "http://example.com/u")
    assert feed is not None
    assert feed["folder_id"] is None


def test_import_outline_without_xmlurl_nor_text_skipped_gracefully(tmp_db):
    xml = '<opml version="2.0"><body><outline/></body></opml>'
    result = opml.import_opml(tmp_db, xml)
    assert result == {"imported": 0, "skipped": 0}


def test_roundtrip(tmp_db, tmp_path):
    fid = store.create_folder(tmp_db, "组")
    _insert_feed(tmp_db, fid, "源A", "http://example.com/a", "http://a.example.com")
    _insert_feed(tmp_db, fid, "源B", "http://example.com/b", "http://b.example.com")
    _insert_feed(tmp_db, None, "源C", "http://example.com/c", "http://c.example.com")

    exported = opml.export_opml(tmp_db)

    new_db = tmp_path / "new.db"
    db.init_db(new_db)
    result = opml.import_opml(new_db, exported)
    assert result == {"imported": 3, "skipped": 0}

    folders = store.list_folders(new_db)
    assert len(folders) == 1
    fid_new = folders[0]["id"]
    feeds = store.list_feeds(new_db)
    in_group = [f for f in feeds if f["folder_id"] == fid_new]
    assert len(in_group) == 2
    ungrouped = [f for f in feeds if f["folder_id"] is None]
    assert len(ungrouped) == 1


def test_import_second_run_all_skipped(tmp_db):
    xml = (
        '<opml version="2.0"><body>'
        '<outline text="源1" type="rss" xmlUrl="http://example.com/x1"/>'
        '<outline text="源2" type="rss" xmlUrl="http://example.com/x2"/>'
        "</body></opml>"
    )
    first = opml.import_opml(tmp_db, xml)
    assert first == {"imported": 2, "skipped": 0}
    second = opml.import_opml(tmp_db, xml)
    assert second == {"imported": 0, "skipped": 2}