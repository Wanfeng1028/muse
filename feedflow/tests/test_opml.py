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

