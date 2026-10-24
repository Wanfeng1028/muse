# deep2: RSS deep coverage tests (determinism, escaping, CDATA, pubDate, filtering, limits)
from __future__ import annotations

import xml.etree.ElementTree as ET

from feedflow import db, rss, store


def _insert(db_path, feed_id, title="t", link="http://x/", guid=None,
            content_text="", summary="", published_at=None, fetched_at=None):
    if guid is None:
        guid = ""
    if summary is None:
        summary = ""
    aid = store.insert_article(
        db_path,
        feed_id=feed_id,
        guid=guid,
        title=title,
        author="",
        link=link,
        summary=summary,
        content_html="",
        content_text=content_text,
        published_at=published_at,
    )
    if fetched_at is not None:
        db.execute_write(
            db_path, "UPDATE articles SET fetched_at = ? WHERE id = ?", (fetched_at, aid)
        )
    return aid


_FEED_SEQ = [0]


def _make_feed(db_path, name="f", url=None):
    _FEED_SEQ[0] += 1
    if url is None:
        url = f"http://f/{_FEED_SEQ[0]:d}/"
    return db.execute_write(
        db_path,
        "INSERT INTO feeds (title, feed_url, position, created_at) VALUES (?, ?, 0, ?)",
        (name, url, db.utcnow()),
    )


def test_build_rss_deterministic_etag(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="hello", link="http://x/1", guid="g1",
            content_text="body", published_at="2024-01-02T03:04:05+00:00")
    xml1, etag1 = rss.build_rss(tmp_db)
    xml2, etag2 = rss.build_rss(tmp_db)
    assert xml1 == xml2
    assert etag1 == etag2
    assert etag1.startswith('"') and etag1.endswith('"')
    assert len(etag1) == 66


def test_title_script_is_escaped_and_xml_parses(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="<script>alert(1)</script>",
            link="http://x/", guid="g")
    xml_text, _ = rss.build_rss(tmp_db)
    assert "<title>&lt;script&gt;alert(1)&lt;/script&gt;</title>" in xml_text
    assert "<script>" not in xml_text
    root = ET.fromstring(xml_text)
    assert root.tag == "rss"
    titles = root.findall("./channel/item/title")
    assert len(titles) == 1
    assert titles[0].text == "<script>alert(1)</script>"


def test_guid_fallback_to_link_and_amp_escaping(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="a", link="http://ex/a", guid="")
    _insert(tmp_db, fid, title="b", link="http://ex/b?x=1&y=2", guid="A&B")
    xml_text, _ = rss.build_rss(tmp_db)
    assert "<guid>http://ex/a</guid>" in xml_text
    assert "<guid>A&amp;B</guid>" in xml_text
    assert "<guid>A&B</guid>" not in xml_text
    root = ET.fromstring(xml_text)
    guids = [g.text for g in root.findall("./channel/item/guid")]
    assert sorted(guids) == ["A&B", "http://ex/a"]


def test_cdata_split_on_cdata_end_marker(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="t", link="http://x/", guid="g",
            content_text="before]]>after")
    xml_text, _ = rss.build_rss(tmp_db)
    assert "]]]]><![CDATA[>" in xml_text
    root = ET.fromstring(xml_text)
    desc = root.find("./channel/item/description")
    assert desc is not None
    assert desc.text == "before]]>after"


def test_pubdate_invalid_omitted_and_fetched_fallback(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="bad", link="http://x/bad", guid="gb",
            published_at="not-a-date", fetched_at="2024-05-06T07:08:09+00:00")
    _insert(tmp_db, fid, title="fb", link="http://x/fb", guid="gf",
            published_at=None, fetched_at="2024-05-06T07:08:09+00:00")
    xml_text, _ = rss.build_rss(tmp_db)
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    assert len(items) == 2
    bad_item = next(i for i in items if i.findtext("title") == "bad")
    bad_pub = bad_item.findtext("pubDate")
    assert bad_pub is not None
    assert "06 May 2024" in bad_pub
    assert "07:08:09" in bad_pub
    fb_item = next(i for i in items if i.findtext("title") == "fb")
    pub = fb_item.findtext("pubDate")
    assert pub is not None
    assert "06 May 2024" in pub
    assert "07:08:09" in pub

    fid2 = _make_feed(tmp_db)
    aid = _insert(tmp_db, fid2, title="allbad", link="http://x/allbad", guid="gall",
                  published_at="not-a-date")
    db.execute_write(
        tmp_db, "UPDATE articles SET fetched_at = ? WHERE id = ?", ("bad", aid)
    )
    xml_text2, _ = rss.build_rss(tmp_db, feed_id=fid2)
    root2 = ET.fromstring(xml_text2)
    items2 = root2.findall("./channel/item")
    assert len(items2) == 1
    assert items2[0].find("pubDate") is None


def test_feed_id_filtering(tmp_db):
    f1 = _make_feed(tmp_db, name="one", url="http://one/")
    f2 = _make_feed(tmp_db, name="two", url="http://two/")
    _insert(tmp_db, f1, title="from-f1", link="http://one/a", guid="a")
    _insert(tmp_db, f2, title="from-f2", link="http://two/b", guid="b")
    xml1, _ = rss.build_rss(tmp_db, feed_id=f1)
    root1 = ET.fromstring(xml1)
    titles1 = [t.text for t in root1.findall("./channel/item/title")]
    assert titles1 == ["from-f1"]
    xml2, _ = rss.build_rss(tmp_db, feed_id=f2)
    root2 = ET.fromstring(xml2)
    titles2 = [t.text for t in root2.findall("./channel/item/title")]
    assert titles2 == ["from-f2"]


def test_empty_content_and_summary_yields_empty_cdata(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="empty", link="http://x/e", guid="ge",
            content_text="", summary="")
    xml_text, _ = rss.build_rss(tmp_db)
    assert "<description><![CDATA[]]></description>" in xml_text
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    assert len(items) == 1
    assert items[0].findtext("title") == "empty"


def test_limit_capped_at_50_with_60_articles(tmp_db):
    fid = _make_feed(tmp_db)
    for i in range(60):
        _insert(tmp_db, fid, title=f"a{i}", link=f"http://x/{i}", guid=f"g{i}")
    xml_text, _ = rss.build_rss(tmp_db, limit=100)
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    assert len(items) == 50


def test_link_with_quotes_and_angle_brackets_escaped(tmp_db):
    fid = _make_feed(tmp_db)
    _insert(tmp_db, fid, title="t", link='http://x/?q="a"<b>', guid="g")
    xml_text, _ = rss.build_rss(tmp_db)
    assert "&lt;" in xml_text
    assert "&gt;" in xml_text
    root = ET.fromstring(xml_text)
    link = root.findtext("./channel/item/link")
    assert link == 'http://x/?q="a"<b>'