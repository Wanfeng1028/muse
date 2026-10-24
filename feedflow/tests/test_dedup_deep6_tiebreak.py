
from feedflow import store
from feedflow.dedup import find_or_create_cluster, get_text_for, simhash


def test_tie_picks_largest_id(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/tie.xml")
    title = "相同事件标题"
    content = "完全相同的正文内容。"
    text = get_text_for({"title": title, "content_text": content})
    sh = simhash(text)

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary, "
            "content_html, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
            (feed_id, "guid-a", title, "", "", "", "", content, sh, 101),
        )
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary, "
            "content_html, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
            (feed_id, "guid-b", title, "", "", "", "", content, sh, 202),
        )
        conn.commit()
    finally:
        conn.close()

    result = find_or_create_cluster(tmp_db, sh, text)
    assert result == 202


def test_dissimilar_does_not_steal(tmp_db):
    feed_id = store.create_feed(tmp_db, "https://example.com/dissim.xml")
    title = "相同事件标题"
    content = "完全相同的正文内容。"
    text = get_text_for({"title": title, "content_text": content})
    sh = simhash(text)

    other_title = "完全不相关"
    other_content = "另一件毫不相干的事情，与前文没有任何交集。"
    other_text = get_text_for({"title": other_title, "content_text": other_content})
    other_sh = simhash(other_text)

    import sqlite3
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary, "
            "content_html, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
            (feed_id, "guid-a", title, "", "", "", "", content, sh, 101),
        )
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary, "
            "content_html, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
            (feed_id, "guid-b", title, "", "", "", "", content, sh, 202),
        )
        conn.execute(
            "INSERT INTO articles (feed_id, guid, title, author, link, summary, "
            "content_html, content_text, published_at, fetched_at, simhash, cluster_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
            (feed_id, "guid-c", other_title, "", "", "", "", other_content, other_sh, 303),
        )
        conn.commit()
    finally:
        conn.close()

    result = find_or_create_cluster(tmp_db, sh, text)
    assert result == 202
