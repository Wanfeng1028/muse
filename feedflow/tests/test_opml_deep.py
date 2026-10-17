import xml.etree.ElementTree as ET

import pytest

from feedflow import db as db_mod
from feedflow import opml
from feedflow import store


def _make_feed(feed_url, title="", site_url=""):
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<opml version="2.0"><head><title>t</title></head><body>'
        '<outline text="{title}" title="{title}" type="rss" '
        'xmlUrl="{url}" htmlUrl="{site}"/>'
        "</body></opml>"
    ).format(title=title, url=feed_url, site=site_url)
    return xml


def _parse(xml_text):
    return ET.fromstring(xml_text)


def test_import_skips_malformed_xml(tmp_db):
    before_feeds = store.list_feeds(tmp_db)
    before_folders = store.list_folders(tmp_db)

    result = opml.import_opml(tmp_db, "<opml><body><outline")

    assert result == {"imported": 0, "skipped": 0}
    assert store.list_feeds(tmp_db) == before_feeds
    assert store.list_folders(tmp_db) == before_folders


def test_import_handles_empty_body(tmp_db):
    xml = '<?xml version="1.0"?><opml version="2.0"><body></body></opml>'

    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 0
    assert result["skipped"] == 0
    assert store.list_feeds(tmp_db) == []


def test_import_handles_missing_body(tmp_db):
    xml = '<?xml version="1.0"?><opml version="2.0"><head/></opml>'

    result = opml.import_opml(tmp_db, xml)

    assert result == {"imported": 0, "skipped": 0}
    assert store.list_feeds(tmp_db) == []


def test_import_creates_feed_and_folder_from_nested_outlines(tmp_db):
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<opml version="2.0"><body>'
        '<outline text="科技" title="科技">'
        '<outline text="某站" title="某站" type="rss" '
        'xmlUrl="https://example.com/tech.xml" htmlUrl="https://example.com"/>'
        "</outline>"
        "</body></opml>"
    )

    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 1
    assert result["skipped"] == 0
    folders = store.list_folders(tmp_db)
    assert len(folders) == 1
    assert folders[0]["name"] == "科技"
    feeds = store.list_feeds(tmp_db)
    assert len(feeds) == 1
    assert feeds[0]["feed_url"] == "https://example.com/tech.xml"
    assert feeds[0]["title"] == "某站"
    assert feeds[0]["folder_id"] == folders[0]["id"]


def test_import_nested_folder_uses_text_fallback_title(tmp_db):
    xml = (
        '<?xml version="1.0"?>'
        '<opml version="2.0"><body>'
        '<outline title="新闻">'
        '<outline type="rss" xmlUrl="https://a.example/rss"/>'
        "</outline>"
        "</body></opml>"
    )

    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 1
    folders = store.list_folders(tmp_db)
    assert [f["name"] for f in folders] == ["新闻"]
    feeds = store.list_feeds(tmp_db)
    assert feeds[0]["folder_id"] == folders[0]["id"]


def test_import_duplicate_feed_url_counted_as_skipped(tmp_db):
    xml = _make_feed("https://dup.example/rss", title="重复")

    first = opml.import_opml(tmp_db, xml)
    second = opml.import_opml(tmp_db, xml)

    assert first == {"imported": 1, "skipped": 0}
    assert second == {"imported": 0, "skipped": 1}
    assert len(store.list_feeds(tmp_db)) == 1


def test_import_repeated_import_is_idempotent_for_folders(tmp_db):
    xml = (
        '<?xml version="1.0"?>'
        '<opml version="2.0"><body>'
        '<outline text="组A">'
        '<outline type="rss" xmlUrl="https://idem.example/a"/>'
        '<outline type="rss" xmlUrl="https://idem.example/b"/>'
        "</outline>"
        "</body></opml>"
    )

    opml.import_opml(tmp_db, xml)
    opml.import_opml(tmp_db, xml)

    folders = store.list_folders(tmp_db)
    assert len(folders) == 1
    assert folders[0]["name"] == "组A"
    urls = sorted(f["feed_url"] for f in store.list_feeds(tmp_db))
    assert urls == ["https://idem.example/a", "https://idem.example/b"]


def test_import_same_folder_name_under_multiple_parents(tmp_db):
    xml = (
        '<?xml version="1.0"?>'
        '<opml version="2.0"><body>'
        '<outline text="根">'
        '<outline text="子">'
        '<outline type="rss" xmlUrl="https://n1.example/rss"/>'
        "</outline>"
        "</outline>"
        '<outline text="子">'
        '<outline type="rss" xmlUrl="https://n2.example/rss"/>'
        "</outline>"
        "</body></opml>"
    )

    result = opml.import_opml(tmp_db, xml)

    assert result["imported"] == 2
    names = sorted(f["name"] for f in store.list_folders(tmp_db))
    assert names == ["子", "根"]
    folder_by_name = {f["name"]: f["id"] for f in store.list_folders(tmp_db)}
    feed_by_url = {f["feed_url"]: f for f in store.list_feeds(tmp_db)}
    assert feed_by_url["https://n1.example/rss"]["folder_id"] == folder_by_name["子"]
    assert feed_by_url["https://n2.example/rss"]["folder_id"] == folder_by_name["子"]


def test_import_missing_xmlurl_outline_is_treated_as_folder(tmp_db):
    xml = (
        '<?xml version="1.0"?>'
        '<opml version="2.0"><body>'
        '<outline text="只有标题没有源"/>'
        "</body></opml>"
    )

    result = opml.import_opml(tmp_db, xml)

    assert result == {"imported": 0, "skipped": 0}
    folders = store.list_folders(tmp_db)
    assert [f["name"] for f in folders] == ["只有标题没有源"]
    assert store.list_feeds(tmp_db) == []


def test_import_feed_title_falls_back_to_outline_title_attr(tmp_db):
    xml = (
        '<?xml version="1.0"?>'
        '<opml version="2.0"><body>'
        '<outline title="备用标题" type="rss" xmlUrl="https://fallback.example/rss"/>'
        "</body></opml>"
    )

    opml.import_opml(tmp_db, xml)

    feeds = store.list_feeds(tmp_db)
    assert len(feeds) == 1
    assert feeds[0]["title"] == "备用标题"
    assert feeds[0]["feed_url"] == "https://fallback.example/rss"


def test_export_roundtrip_preserves_folder_and_feed(tmp_db):
    fid = store.create_folder(tmp_db, "科技")
    feed_id = store.create_feed(tmp_db, "https://round.example/rss", fid, 0)
    store.update_feed(tmp_db, feed_id, title="Round站点")

    xml_text = opml.export_opml(tmp_db)

    assert "Round站点" in xml_text
    assert "https://round.example/rss" in xml_text
    assert "科技" in xml_text
    result = opml.import_opml(tmp_db, xml_text)
    assert result["imported"] == 0
    assert result["skipped"] == 1
    assert len(store.list_feeds(tmp_db)) == 1


def test_export_ungrouped_feed_attached_to_body(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://free.example/rss", None, 0)
    store.update_feed(tmp_db, feed_id, title="未分组站点")

    xml_text = opml.export_opml(tmp_db)
    root = _parse(xml_text)

    body = root.find("body")
    assert body is not None
    direct = [o for o in body.findall("outline") if o.get("xmlUrl")]
    assert len(direct) == 1
    assert direct[0].get("xmlUrl") == "https://free.example/rss"
    assert direct[0].get("text") == "未分组站点"


def test_export_structure_has_head_and_version(tmp_db):
    store.create_folder(tmp_db, "空组")

    xml_text = opml.export_opml(tmp_db)
    root = _parse(xml_text)

    assert root.tag == "opml"
    assert root.get("version") == "2.0"
    head = root.find("head")
    assert head is not None
    assert head.find("title").text == "FeedFlow 订阅导出"
    assert head.find("dateCreated").text


def test_export_multiple_feeds_in_one_folder_keep_order(tmp_db):
    fid = store.create_folder(tmp_db, "批量")
    first = store.create_feed(tmp_db, "https://m1.example/rss", fid, 0)
    store.update_feed(tmp_db, first, title="M1")
    second = store.create_feed(tmp_db, "https://m2.example/rss", fid, 0)
    store.update_feed(tmp_db, second, title="M2")

    xml_text = opml.export_opml(tmp_db)
    root = _parse(xml_text)

    folder_outline = root.find("body").find("outline")
    assert folder_outline.get("text") == "批量"
    urls = [o.get("xmlUrl") for o in folder_outline.findall("outline")]
    assert urls == ["https://m1.example/rss", "https://m2.example/rss"]