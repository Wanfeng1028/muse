import os
import sys
from pathlib import Path

import pytest

# 保证可以 import feedflow（项目根目录）
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from feedflow import db as db_mod
from feedflow import opml, store


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "feedflow.db"
    db_mod.init_db(str(db_path))
    return str(db_path)


def test_export_contains_opml_and_xmlurl(tmp_db):
    fid = store.create_folder(tmp_db, "科技")
    store.create_feed(tmp_db, "https://example.com/a.xml", folder_id=fid)
    store.create_feed(tmp_db, "https://example.com/b.xml")

    xml_text = opml.export_opml(tmp_db)
    assert '<opml version="2.0">' in xml_text
    assert "xmlUrl" in xml_text
    assert "https://example.com/a.xml" in xml_text
    assert "https://example.com/b.xml" in xml_text


def test_import_opml_counts(tmp_db):
    fid = store.create_folder(tmp_db, "科技")
    store.create_feed(tmp_db, "https://example.com/a.xml", folder_id=fid)
    store.create_feed(tmp_db, "https://example.com/b.xml")
    store.create_feed(tmp_db, "https://example.com/c.xml", folder_id=fid)

    xml_text = opml.export_opml(tmp_db)

    # 新空库
    other = tmp_db + ".new"
    if os.path.exists(other):
        os.remove(other)
    db_mod.init_db(other)

    result = opml.import_opml(other, xml_text)
    assert result["imported"] == 3

    result2 = opml.import_opml(other, xml_text)
    assert result2["skipped"] == 3
    assert result2["imported"] == 0

def test_export_preserves_folder_structure(tmp_db):
    import xml.etree.ElementTree as ET

    fid_a = store.create_folder(tmp_db, "分组A")
    fid_b = store.create_folder(tmp_db, "分组B")
    store.create_feed(tmp_db, "https://example.com/a.xml", folder_id=fid_a)
    store.create_feed(tmp_db, "https://example.com/b.xml", folder_id=fid_b)
    store.create_feed(tmp_db, "https://example.com/c.xml")

    xml_text = opml.export_opml(tmp_db)
    root = ET.fromstring(xml_text)
    body = root.find("body")

    folder_outlines = [
        o for o in body.findall("outline") if o.get("xmlUrl") is None
    ]
    folder_texts = {o.get("text") for o in folder_outlines}
    assert "分组A" in folder_texts
    assert "分组B" in folder_texts

    for outline in folder_outlines:
        child_urls = {c.get("xmlUrl") for c in outline.findall("outline")}
        if outline.get("text") == "分组A":
            assert "https://example.com/a.xml" in child_urls
        if outline.get("text") == "分组B":
            assert "https://example.com/b.xml" in child_urls

    ungrouped = body.findall("./outline[@xmlUrl]")
    ungrouped_urls = {o.get("xmlUrl") for o in ungrouped}
    assert "https://example.com/c.xml" in ungrouped_urls

def test_export_escapes_special_chars(tmp_db):
    import xml.etree.ElementTree as ET

    folder_name = '分组 & < > " 中文'
    feed_title = '标题 & < > " 中文'
    fid = store.create_folder(tmp_db, folder_name)
    store.create_feed(tmp_db, "https://example.com/special.xml", folder_id=fid)

    # 覆写 title 为含特殊字符的值，验证往返无损
    import sqlite3

    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "UPDATE feeds SET title = ? WHERE feed_url = ?",
        (feed_title, "https://example.com/special.xml"),
    )
    conn.commit()
    conn.close()

    xml_text = opml.export_opml(tmp_db)
    root = ET.fromstring(xml_text)
    body = root.find("body")

    folder_outlines = [
        o for o in body.findall("outline") if o.get("xmlUrl") is None
    ]
    assert any(o.get("text") == folder_name for o in folder_outlines)

    target = None
    for outline in folder_outlines:
        for child in outline.findall("outline"):
            if child.get("xmlUrl") == "https://example.com/special.xml":
                target = child
    assert target is not None
    assert target.get("text") == feed_title
    assert target.get("title") == feed_title

def test_export_none_safe(tmp_db, monkeypatch):
    # feeds.title/site_url 有 NOT NULL 约束，脏数据走不到 DB；直接在 dict 层构造 None，
    # 验证 export_opml 对 None 标题/网址不抛异常（防御性）。
    import xml.etree.ElementTree as ET

    dirty = {
        "id": 999,
        "title": None,
        "site_url": None,
        "feed_url": "https://example.com/dirty.xml",
        "folder_id": None,
    }
    monkeypatch.setattr(opml.store, "list_folders", lambda db_path: [])
    monkeypatch.setattr(opml.store, "list_feeds", lambda db_path: [dirty])

    xml_text = opml.export_opml(tmp_db)
    root = ET.fromstring(xml_text)
    body = root.find("body")
    urls = {o.get("xmlUrl") for o in body.findall("./outline[@xmlUrl]")}
    assert "https://example.com/dirty.xml" in urls

def test_export_has_date_created(tmp_db):
    import xml.etree.ElementTree as ET
    from datetime import datetime

    store.create_feed(tmp_db, "https://example.com/a.xml")
    xml_text = opml.export_opml(tmp_db)
    root = ET.fromstring(xml_text)
    head = root.find("head")
    date_el = head.find("dateCreated")
    assert date_el is not None
    assert date_el.text
    datetime.fromisoformat(date_el.text)

def test_export_opml_version(tmp_db):
    import xml.etree.ElementTree as ET

    store.create_feed(tmp_db, "https://example.com/a.xml")
    xml_text = opml.export_opml(tmp_db)
    root = ET.fromstring(xml_text)
    assert root.tag == "opml"
    assert root.get("version") == "2.0"

def test_export_import_roundtrip_keeps_folders(tmp_db):
    fid_a = store.create_folder(tmp_db, "分组A")
    fid_b = store.create_folder(tmp_db, "分组B")
    store.create_feed(tmp_db, "https://example.com/a.xml", folder_id=fid_a)
    store.create_feed(tmp_db, "https://example.com/b.xml", folder_id=fid_b)
    store.create_feed(tmp_db, "https://example.com/c.xml")

    xml_text = opml.export_opml(tmp_db)

    other = tmp_db + ".roundtrip"
    if os.path.exists(other):
        os.remove(other)
    db_mod.init_db(other)

    result = opml.import_opml(other, xml_text)
    assert result["imported"] == 3

    new_folders = store.list_folders(other)
    new_feeds = store.list_feeds(other)
    assert {f["name"] for f in new_folders} == {"分组A", "分组B"}
    assert len(new_feeds) == 3

