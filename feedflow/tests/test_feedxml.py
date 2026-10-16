import xml.etree.ElementTree as ET

from feedflow import store


def _seed_article(db, feed_id, i, content_text="正文内容…", summary="<p>摘要</p>"):
    return store.insert_article(
        db,
        feed_id,
        guid=f"g-{feed_id}-{i}",
        title=f"T-{i}",
        author="作者",
        link=f"http://example.com/{feed_id}/{i}",
        summary=summary,
        content_html=content_text,
        content_text=content_text,
        published_at=f"2026-10-16T00:{i % 60:02d}:00+00:00",
    )


def test_feedxml_is_valid_rss(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed", folder_id=None)
    _seed_article(tmp_db, fid, 1)
    _seed_article(tmp_db, fid, 2)

    r = client.get("/feed.xml")
    assert r.status_code == 200
    assert "rss+xml" in r.headers.get("Content-Type", "")

    root = ET.fromstring(r.data)
    assert root.tag == "rss"
    channel = root.find("channel")
    assert channel is not None
    assert channel.find("title") is not None
    items = channel.findall("item")
    # 注：create_app 会 seeding 24 篇演示文章，只断言我们插入的 2 篇在列
    assert len(items) >= 2
    body = r.data.decode("utf-8")
    assert "T-1" in body
    assert "T-2" in body


def test_feedxml_contains_full_text(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed")
    _seed_article(
        tmp_db,
        fid,
        1,
        content_text="trafilatura提取的完整正文第一段第二段",
        summary="<p>摘要</p>",
    )

    r = client.get("/feed.xml")
    assert r.status_code == 200
    assert "trafilatura提取的完整正文第一段第二段" in r.data.decode("utf-8")


def test_feedxml_falls_back_to_summary(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed")
    _seed_article(
        tmp_db,
        fid,
        1,
        content_text="",
        summary="<p>摘要<b>文本</b></p>",
    )

    r = client.get("/feed.xml")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "摘要 文本" in body
    assert "<p>" not in body


def test_feedxml_filter_by_feed(client, tmp_db):
    fa = store.create_feed(tmp_db, "http://a/feed")
    fb = store.create_feed(tmp_db, "http://b/feed")
    store.insert_article(
        tmp_db,
        fa,
        guid="a-1",
        title="A-1",
        author="",
        link="http://a/1",
        summary="<p>s</p>",
        content_html="",
        content_text="",
        published_at="2026-10-16T00:00:00+00:00",
    )
    store.insert_article(
        tmp_db,
        fa,
        guid="a-2",
        title="A-2",
        author="",
        link="http://a/2",
        summary="<p>s</p>",
        content_html="",
        content_text="",
        published_at="2026-10-16T00:01:00+00:00",
    )
    store.insert_article(
        tmp_db,
        fb,
        guid="b-1",
        title="B-1",
        author="",
        link="http://b/1",
        summary="<p>s</p>",
        content_html="",
        content_text="",
        published_at="2026-10-16T00:02:00+00:00",
    )

    r = client.get(f"/feed.xml?feed_id={fa}")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "A-1" in body
    assert "B-1" not in body


def test_feedxml_filter_by_folder(client, tmp_db):
    gid = store.create_folder(tmp_db, "G")
    fs = store.create_feed(tmp_db, "http://s/feed", folder_id=gid)
    ft = store.create_feed(tmp_db, "http://t/feed")
    store.insert_article(
        tmp_db,
        fs,
        guid="s-1",
        title="S-1",
        author="",
        link="http://s/1",
        summary="<p>s</p>",
        content_html="",
        content_text="",
        published_at="2026-10-16T00:00:00+00:00",
    )
    store.insert_article(
        tmp_db,
        ft,
        guid="t-1",
        title="T-1",
        author="",
        link="http://t/1",
        summary="<p>s</p>",
        content_html="",
        content_text="",
        published_at="2026-10-16T00:01:00+00:00",
    )

    r = client.get(f"/feed.xml?folder={gid}")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "S-1" in body
    assert "T-1" not in body


def test_feedxml_limit_50(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed")
    for i in range(55):
        _seed_article(tmp_db, fid, i)

    r = client.get("/feed.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.data)
    channel = root.find("channel")
    items = channel.findall("item")
    assert len(items) == 50


def test_feedxml_etag_304(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed")
    _seed_article(tmp_db, fid, 1)

    r1 = client.get("/feed.xml")
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag

    r2 = client.get("/feed.xml", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers.get("ETag") == etag


def test_feedxml_cdata_escape(client, tmp_db):
    fid = store.create_feed(tmp_db, "http://a/feed")
    _seed_article(tmp_db, fid, 1, content_text="a]]>b")

    r = client.get("/feed.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.data)
    channel = root.find("channel")
    items = channel.findall("item")
    assert items
    # 按标题找到我们插入的那篇（种子数据也在库里，不假设排第一）
    ours = None
    for it in items:
        title_el = it.find("title")
        if title_el is not None and title_el.text == "T-1":
            ours = it
            break
    assert ours is not None
    desc = ours.find("description")
    assert desc is not None
    text = desc.text or ""
    assert "a" in text
    assert "b" in text
