"""示例数据种子：当 feeds 表为空时插入两条禁用的示例源。"""

from datetime import UTC, datetime

from . import db


def _utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


def ensure_seed(db_path) -> None:
    """若 feeds 表为空，则插入两条 enabled=0 的示例源。"""
    db.init_db(db_path)
    conn = db.get_conn(db_path)
    try:
        with db.write_lock:
            cur = conn.execute("SELECT COUNT(*) AS n FROM feeds")
            row = cur.fetchone()
            count = row["n"] if row is not None else 0
            if count and count > 0:
                return

            now = _utcnow_iso()
            seeds = [
                {
                    "title": "示例博客",
                    "site_url": "https://example.com",
                    "feed_url": "https://example.com/feed.xml",
                    "description": "",
                },
                {
                    "title": "示例播客",
                    "site_url": "https://example.com",
                    "feed_url": "https://example.com/podcast.xml",
                    "description": "",
                },
            ]
            for item in seeds:
                conn.execute(
                    """
                    INSERT INTO feeds (
                        folder_id, title, site_url, feed_url, description,
                        interval_min, enabled, last_fetched_at, last_status,
                        last_error, etag, modified, position, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        None,
                        item["title"],
                        item["site_url"],
                        item["feed_url"],
                        item["description"],
                        0,
                        0,
                        None,
                        None,
                        "",
                        "",
                        "",
                        0,
                        now,
                    ),
                )
            conn.commit()
    finally:
        conn.close()
