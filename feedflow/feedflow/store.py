"""数据访问层：所有函数首参为 db_path，返回 dict 或 dict 列表。"""
from datetime import UTC, datetime, timedelta

from .db import get_conn, write_lock


def _now_iso():
    return datetime.now(UTC).isoformat()


# ---------------- folders ----------------

def create_folder(db_path, name):
    """新建分组，返回 id。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO folders(name, position, created_at) "
                "VALUES(?, (SELECT COALESCE(MAX(position), -1) + 1 FROM folders), ?)",
                (name, _now_iso()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def list_folders(db_path):
    """列出分组，附未读数（该组下所有源未读文章数）。"""
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT f.id AS id, f.name AS name, f.position AS position,
                   (SELECT COUNT(*) FROM articles a
                      JOIN feeds fe ON fe.id = a.feed_id
                     WHERE fe.folder_id = f.id AND a.is_read = 0) AS unread
              FROM folders f
             ORDER BY f.position ASC, f.id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def rename_folder(db_path, folder_id, name):
    """重命名分组。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
            conn.commit()
        finally:
            conn.close()


def delete_folder(db_path, folder_id):
    """删除分组，组内源 folder_id 置 NULL。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute("UPDATE feeds SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
            conn.commit()
        finally:
            conn.close()


def move_folder(db_path, folder_id, direction):
    """上/下移动分组，调整 position。direction: 'up'|'down'。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute("SELECT id, position FROM folders WHERE id = ?", (folder_id,)).fetchone()
            if cur is None:
                return False
            cur_pos = cur["position"]
            if direction == "up":
                nb = conn.execute(
                    "SELECT id, position FROM folders WHERE position < ? ORDER BY position DESC LIMIT 1",
                    (cur_pos,),
                ).fetchone()
            else:
                nb = conn.execute(
                    "SELECT id, position FROM folders WHERE position > ? ORDER BY position ASC LIMIT 1",
                    (cur_pos,),
                ).fetchone()
            if nb is None:
                return False
            conn.execute("UPDATE folders SET position = ? WHERE id = ?", (nb["position"], cur["id"]))
            conn.execute("UPDATE folders SET position = ? WHERE id = ?", (cur_pos, nb["id"]))
            conn.commit()
            return True
        finally:
            conn.close()


# ---------------- feeds ----------------

def create_feed(db_path, feed_url, folder_id=None, interval_min=0):
    """新建源，先用 fetcher.parse_feed_info 填充元信息，失败则 title=feed_url。返回 id。"""
    from . import fetcher
    info = {}
    try:
        info = fetcher.parse_feed_info(feed_url) or {}
    except Exception:  # noqa: BLE001
        # 解析元信息可能因网络或格式异常抛出任意异常，这里故意宽捕获，失败则回退默认值。
        info = {}
    title = info.get("title") or feed_url
    site_url = info.get("site_url") or ""
    description = info.get("description") or ""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO feeds(folder_id, title, site_url, feed_url, description,
                                  interval_min, enabled, position, created_at)
                VALUES(?, ?, ?, ?, ?, ?, 1,
                       (SELECT COALESCE(MAX(position), -1) + 1 FROM feeds), ?)
                """,
                (folder_id, title, site_url, feed_url, description, interval_min, _now_iso()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_feed(db_path, feed_id):
    """取单个源，无则 None。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_feeds(db_path, folder_id=None):
    """列出源，附未读数。folder_id 为 None 列出全部。"""
    conn = get_conn(db_path)
    try:
        sql = (
            "SELECT f.*, "
            "(SELECT COUNT(*) FROM articles a WHERE a.feed_id = f.id AND a.is_read = 0) AS unread "
            "FROM feeds f "
        )
        params = ()
        if folder_id is not None:
            sql += "WHERE f.folder_id = ? "
            params = (folder_id,)
        sql += "ORDER BY f.position ASC, f.id ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_feed(db_path, feed_id, **fields):
    """更新源允许的字段。"""
    allowed = {"title", "folder_id", "interval_min", "enabled", "position"}
    sets = []
    params = []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            params.append(v)
    if not sets:
        return
    params.append(feed_id)
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(f"UPDATE feeds SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()


def delete_feed(db_path, feed_id):
    """删除源（级联删文章）。返回 True/False。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def set_fetch_result(db_path, feed_id, status, error, etag, modified):
    """抓取后更新源状态。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE feeds SET last_fetched_at = ?, last_status = ?, last_error = ?, "
                "etag = ?, modified = ? WHERE id = ?",
                (_now_iso(), status, error or "", etag or "", modified or "", feed_id),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------- articles ----------------

def article_exists(db_path, feed_id, guid):
    """判断文章是否已存在。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE feed_id = ? AND guid = ? LIMIT 1",
            (feed_id, guid),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_article(db_path, feed_id, guid, title, author, link, summary,
                   content_html, content_text, published_at):
    """插入文章，返回 id。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO articles(feed_id, guid, title, author, link, summary,
                                     content_html, content_text, published_at, fetched_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feed_id, guid, title, author, link, summary,
                 content_html, content_text, published_at, _now_iso()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def _scope_clause(scope):
    if scope == "unread":
        return "a.is_read = 0"
    if scope == "starred":
        return "a.is_starred = 1"
    return "1 = 1"


def list_articles(db_path, scope="unread", feed_id=None, folder_id=None,
                  limit=50, offset=0):
    """列出文章，返回 (total, rows)。rows 含 feed_title，按 published_at 倒序 NULL 排后。"""
    conn = get_conn(db_path)
    try:
        where = [_scope_clause(scope)]
        params = []
        if feed_id is not None:
            where.append("a.feed_id = ?")
            params.append(feed_id)
        if folder_id is not None:
            where.append("f.folder_id = ?")
            params.append(folder_id)
        where_sql = " AND ".join(where)
        base = (
            "FROM articles a JOIN feeds f ON f.id = a.feed_id "
            f"WHERE {where_sql}"
        )
        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        sql = (
            "SELECT a.id, a.feed_id, a.guid, a.title, a.author, a.link, a.summary, "
            "a.content_html, a.content_text, a.published_at, a.fetched_at, "
            "a.is_read, a.is_starred, f.title AS feed_title "
            f"{base} "
            "ORDER BY a.published_at IS NULL, a.published_at DESC, a.id DESC "
            "LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, params + [limit, offset]).fetchall()
        return total, [dict(r) for r in rows]
    finally:
        conn.close()


def get_article(db_path, article_id):
    """取单篇文章全字段 + feed_title，无则 None。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT a.*, f.title AS feed_title "
            "FROM articles a JOIN feeds f ON f.id = a.feed_id WHERE a.id = ?",
            (article_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_read(db_path, article_id, is_read):
    """设置已读状态。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE articles SET is_read = ? WHERE id = ?",
                (1 if is_read else 0, article_id),
            )
            conn.commit()
        finally:
            conn.close()


def set_starred(db_path, article_id, is_starred):
    """设置星标状态。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE articles SET is_starred = ? WHERE id = ?",
                (1 if is_starred else 0, article_id),
            )
            conn.commit()
        finally:
            conn.close()


def mark_all_read(db_path, feed_id=None, folder_id=None, scope="unread"):
    """批量标记已读。scope: unread|starred|all。"""
    where = [_scope_clause(scope)]
    params = []
    if feed_id is not None:
        where.append("feed_id = ?")
        params.append(feed_id)
    if folder_id is not None:
        where.append("feed_id IN (SELECT id FROM feeds WHERE folder_id = ?)")
        params.append(folder_id)
    where_sql = " AND ".join(where).replace("a.", "")  # UPDATE 不支持表别名，去掉 a. 前缀
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                f"UPDATE articles SET is_read = 1 WHERE {where_sql}", params
            )
            conn.commit()
        finally:
            conn.close()


def search_articles(db_path, q, limit=50):
    """FTS5 全文检索，返回 dict 列表（含 feed_title）。"""
    if q is None:
        return []
    q = q.strip()
    if not q:
        return []
    q = q.replace('"', "")
    if not q:
        return []
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.feed_id, a.guid, a.title, a.author, a.link, a.summary,
                   a.content_html, a.content_text, a.published_at, a.fetched_at,
                   a.is_read, a.is_starred, f.title AS feed_title
              FROM articles_fts
              JOIN articles a ON a.id = articles_fts.rowid
              JOIN feeds f ON f.id = a.feed_id
             WHERE articles_fts MATCH ?
             ORDER BY rank
             LIMIT ?
            """,
            (q, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats(db_path):
    """统计信息。"""
    conn = get_conn(db_path)
    try:
        feeds = conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
        articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        unread = conn.execute("SELECT COUNT(*) FROM articles WHERE is_read = 0").fetchone()[0]
        starred = conn.execute("SELECT COUNT(*) FROM articles WHERE is_starred = 1").fetchone()[0]
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_added = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE fetched_at >= ?",
            (today.isoformat(),),
        ).fetchone()[0]
        per_feed_rows = conn.execute(
            """
            SELECT f.id AS id, f.title AS title, f.last_status AS last_status,
                   (SELECT COUNT(*) FROM articles a WHERE a.feed_id = f.id AND a.is_read = 0) AS unread
              FROM feeds f
             ORDER BY f.position ASC, f.id ASC
            """
        ).fetchall()
        return {
            "feeds": feeds,
            "articles": articles,
            "unread": unread,
            "starred": starred,
            "today_added": today_added,
            "per_feed": [dict(r) for r in per_feed_rows],
        }
    finally:
        conn.close()


def due_feeds(db_path, now_iso, default_interval):
    """返回需要抓取的源（enabled=1 且到期）。在 Python 里比较 ISO8601 时间字符串。"""
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM feeds WHERE enabled = 1 ORDER BY position ASC, id ASC"
        ).fetchall()
    finally:
        conn.close()
    result = []
    try:
        now_dt = datetime.fromisoformat(now_iso)
    except Exception:  # noqa: BLE001
        # 传入时间字符串格式可能异常，这里故意宽捕获，解析失败则回退为当前时间。
        now_dt = datetime.now(UTC)
    for r in rows:
        feed = dict(r)
        interval = feed.get("interval_min") or 0
        if not interval:
            interval = default_interval
        last = feed.get("last_fetched_at")
        if not last:
            result.append(feed)
            continue
        try:
            last_dt = datetime.fromisoformat(last)
        except Exception:  # noqa: BLE001
            # 存储的抓取时间可能格式异常，这里故意宽捕获，解析失败则跳过该源。
            result.append(feed)
            continue
        if last_dt <= now_dt - timedelta(minutes=interval):
            result.append(feed)
    return result

