# tests/test_rss_deep3.py — /feed.xml HTTP 层纵深（过滤/ETag/转义/分页封顶）
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"

import xml.etree.ElementTree as ET

from feedflow import (
    create_app,
    store,
)
from feedflow import db as db_module


def _clean_seed(db_path):
    """清掉 create_app 自动写入的演示数据，保证计数类断言确定。"""
    for table in ("articles", "feeds", "folders"):
        db_module.execute_write(db_path, f"DELETE FROM {table}")


def _make_app(tmp_path):
    db_path = str(tmp_path / "feedflow.db")
    os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
    app = create_app({
        "db_path": db_path,
        "host": "127.0.0.1",
        "port": 8303,
        "fetch_interval": 30,
        "user_agent": "FeedFlow-test",
    })
    _clean_seed(db_path)
    return app, db_path


def _add_feed(db_path, url, title="Feed"):
    fid = store.create_feed(db_path, url)
    store.update_feed(db_path, fid, title=title)
    return fid


def _add_article(db_path, feed_id, title, content_text=None, summary=None, url=None):
    aid = store.insert_article(
        db_path,
        feed_id,
        guid=f"guid-{title}",
        title=title,
        author="",
        link=url or f"http://example.com/{title}",
        summary=summary or "",
        content_html="",
        content_text=content_text or "",
        published_at="2024-01-01T00:00:00+00:00",
    )
    return aid


def _client(app):
    return app.test_client()


# 测：GET /feed.xml 无文章时返回合法空 RSS，channel 结构完整
def test_feedxml_empty_channel_structure(tmp_path):
    app, _db_path = _make_app(tmp_path)
    client = _client(app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    root = ET.fromstring(body)
    assert root.tag == "rss"
    assert root.attrib.get("version") == "2.0"
    channel = root.find("channel")
    assert channel is not None
    assert channel.find("title") is not None
    assert channel.find("link") is not None
    assert channel.find("description") is not None
    items = channel.findall("item")
    assert items == []


# 测：?feed_id= 过滤只含该源文章，别源文章不出现
def test_feedxml_filter_by_feed_id(tmp_path):
    app, db_path = _make_app(tmp_path)
    f1 = _add_feed(db_path, "http://a.example/feed", "FeedA")
    f2 = _add_feed(db_path, "http://b.example/feed", "FeedB")
    _add_article(db_path, f1, "alpha-one", content_text="alpha content")
    _add_article(db_path, f1, "alpha-two", content_text="alpha two")
    _add_article(db_path, f2, "beta-one", content_text="beta content")

    client = _client(app)
    resp = client.get(f"/feed.xml?feed_id={f1}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    root = ET.fromstring(body)
    titles = [it.findtext("title") for it in root.findall("./channel/item")]
    assert "alpha-one" in titles
    assert "alpha-two" in titles
    assert "beta-one" not in titles
    assert len(titles) == 2


# 测：?folder= 按分组过滤
def test_feedxml_filter_by_folder(tmp_path):
    app, db_path = _make_app(tmp_path)
    folder_id = store.create_folder(db_path, "Tech")
    f_in = _add_feed(db_path, "http://in.example/feed", "InFeed")
    f_out = _add_feed(db_path, "http://out.example/feed", "OutFeed")
    store.update_feed(db_path, f_in, folder_id=folder_id)

    _add_article(db_path, f_in, "in-article", content_text="in content")
    _add_article(db_path, f_out, "out-article", content_text="out content")

    client = _client(app)
    resp = client.get(f"/feed.xml?folder={folder_id}")
    assert resp.status_code == 200
    root = ET.fromstring(resp.get_data(as_text=True))
    titles = [it.findtext("title") for it in root.findall("./channel/item")]
    assert "in-article" in titles
    assert "out-article" not in titles
    assert len(titles) == 1


# 测：50 篇封顶，61 篇文章只输出 50 个 item
def test_feedxml_limit_50_items(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _add_feed(db_path, "http://cap.example/feed", "CapFeed")
    for i in range(61):
        _add_article(db_path, fid, f"art-{i:03d}", content_text=f"content {i}")

    client = _client(app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    root = ET.fromstring(resp.get_data(as_text=True))
    items = root.findall("./channel/item")
    assert len(items) == 50


# 测：ETag/If-None-Match 第二次请求返回 304 且 body 为空
def test_feedxml_etag_304(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _add_feed(db_path, "http://etag.example/feed", "EtagFeed")
    _add_article(db_path, fid, "etag-article", content_text="etag content")

    client = _client(app)
    first = client.get("/feed.xml")
    assert first.status_code == 200
    etag = first.headers.get("ETag")
    assert etag

    second = client.get("/feed.xml", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.get_data(as_text=True) == ""


# 测：正文优先 content_text，无正文回落摘要去标签文本（摘要含 HTML 标签时输出无标签）
def test_feedxml_content_text_preferred_and_summary_stripped(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _add_feed(db_path, "http://content.example/feed", "ContentFeed")
    _add_article(
        db_path,
        fid,
        "with-content",
        content_text="RAW CONTENT BODY",
        summary="<p>should not appear</p>",
    )
    _add_article(
        db_path,
        fid,
        "summary-only",
        content_text=None,
        summary="<p>Hello <b>World</b></p>",
    )

    client = _client(app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    root = ET.fromstring(body)
    items = {it.findtext("title"): it for it in root.findall("./channel/item")}

    assert "RAW CONTENT BODY" in body
    with_content_desc = items["with-content"].findtext("description") or ""
    assert "RAW CONTENT BODY" in with_content_desc
    assert "should not appear" not in with_content_desc

    summary_only_desc = items["summary-only"].findtext("description") or ""
    assert "Hello" in summary_only_desc
    assert "World" in summary_only_desc
    assert "<p>" not in summary_only_desc
    assert "<b>" not in summary_only_desc
    assert "&lt;" not in summary_only_desc


# 测：特殊字符（& < >）被正确转义，feed 可被 XML 解析器解析
def test_feedxml_special_chars_escaped(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _add_feed(db_path, "http://escape.example/feed", "A & B <Feed>")
    _add_article(
        db_path,
        fid,
        "Tom & Jerry <Show>",
        content_text="5 < 6 && 7 > 3",
    )

    client = _client(app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 必须能被 XML 解析器解析（未转义会抛 ParseError）
    root = ET.fromstring(body)
    item = root.find("./channel/item")
    assert item is not None
    assert item.findtext("title") == "Tom & Jerry <Show>"
    assert "5 < 6 && 7 > 3" in (item.findtext("description") or "")
    # 原始 & < > 不应以裸字符形式出现于标签之间
    assert "&amp;" in body or "&#" in body


# 测：limit 参数非法值（-1/abc）不 500
def test_feedxml_invalid_limit_no_500(tmp_path):
    app, db_path = _make_app(tmp_path)
    fid = _add_feed(db_path, "http://lim.example/feed", "LimFeed")
    _add_article(db_path, fid, "lim-article", content_text="lim content")

    client = _client(app)
    for bad in ["-1", "abc", "0", "", "999999999999999999999"]:
        resp = client.get(f"/feed.xml?limit={bad}")
        assert resp.status_code == 200, f"limit={bad} 返回了 {resp.status_code}"
        body = resp.get_data(as_text=True)
        root = ET.fromstring(body)
        assert root.tag == "rss"
        assert root.find("channel") is not None
