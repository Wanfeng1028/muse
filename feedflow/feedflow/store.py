"""数据访问层：所有函数首参为 db_path，返回 dict 或 dict 列表。"""
import html
import sqlite3
from datetime import UTC, datetime, timedelta

from . import dedup
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


def get_folder(db_path, folder_id):
    """取单个分组，无则返回 None，形状与 list_folders 行一致。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT f.id AS id, f.name AS name, f.position AS position,
                   (SELECT COUNT(*) FROM articles a
                      JOIN feeds fe ON fe.id = a.feed_id
                     WHERE fe.folder_id = f.id AND a.is_read = 0) AS unread
              FROM folders f
             WHERE f.id = ?
            """,
            (folder_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()

def update_folder_position(db_path, folder_id, position):
    """把指定分组的 position 直接设为给定整数。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE folders SET position = ? WHERE id = ?",
                (position, folder_id),
            )
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


def set_fetch_result(db_path, feed_id, status, error, etag, modified,
                     error_kind="", failures=None, dead_after=None):
    """抓取后更新源状态。failures 为 None 时不更新 consecutive_failures。

    dead_after 有效时：连续失败达到阈值则置 is_dead=1 并记录 dead_at；
    成功（status == "ok"）则清零 is_dead/dead_at 复活。
    """
    with write_lock:
        conn = get_conn(db_path)
        try:
            sets = [
                "last_fetched_at = ?",
                "last_status = ?",
                "last_error = ?",
                "last_error_kind = ?",
                "etag = ?",
                "modified = ?",
            ]
            params = [_now_iso(), status, error or "", error_kind or "",
                      etag or "", modified or ""]
            if failures is not None:
                sets.append("consecutive_failures = ?")
                params.append(failures)
            if status == "ok":
                sets.append("is_dead = ?")
                params.append(0)
                sets.append("dead_at = ?")
                params.append("")
            elif (
                failures is not None
                and isinstance(dead_after, int)
                and not isinstance(dead_after, bool)
                and dead_after >= 1
                and failures >= dead_after
            ):
                sets.append("is_dead = ?")
                params.append(1)
                sets.append("dead_at = ?")
                params.append(_now_iso())
            params.append(feed_id)
            conn.execute(
                f"UPDATE feeds SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
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
    """插入文章，返回 id。插入前计算 SimHash 并尝试归入去重簇。"""
    text = dedup.get_text_for({"title": title, "content_text": content_text})
    simhash_hex = dedup.simhash(text)
    cluster_id = dedup.find_or_create_cluster(db_path, simhash_hex, text)
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO articles(feed_id, guid, title, author, link, summary,
                                     content_html, content_text, published_at, fetched_at,
                                     simhash, cluster_id)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feed_id, guid, title, author, link, summary,
                 content_html, content_text, published_at, _now_iso(),
                 simhash_hex, cluster_id),
            )
            new_id = cur.lastrowid
            # 未命中已有簇时，把自己作为该簇的代表（cluster_id 指向自身）。
            if cluster_id is None:
                conn.execute(
                    "UPDATE articles SET cluster_id = ? WHERE id = ?",
                    (new_id, new_id),
                )
            conn.commit()
            return new_id
        finally:
            conn.close()
def _scope_clause(scope):
    if scope == "unread":
        return "a.is_read = 0"
    if scope == "starred":
        return "a.is_starred = 1"
    return "1 = 1"


def list_articles(db_path, scope="unread", feed_id=None, folder_id=None,
                  tag_id=None, limit=50, offset=0):
    """列出文章，返回 (total, rows)。rows 含 feed_title 与簇大小，按 published_at 倒序 NULL 排后。"""
    conn = get_conn(db_path)
    try:
        where = [_scope_clause(scope)]
        params = []
        if feed_id is not None:
            where.append("a.feed_id = ?")
            params.append(feed_id)
        if tag_id is not None:
            where.append("EXISTS (SELECT 1 FROM article_tags at WHERE at.article_id = a.id AND at.tag_id = ?)")
            params.append(tag_id)
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
            "a.is_read, a.is_starred, a.simhash, a.cluster_id, "
            "(SELECT COUNT(*) FROM articles c WHERE c.cluster_id = a.cluster_id) AS cluster_size, "
            "f.title AS feed_title "
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
            if is_read:
                conn.execute(
                    "UPDATE articles SET is_read = ?, last_read_at = ? WHERE id = ?",
                    (1, _now_iso(), article_id),
                )
            else:
                conn.execute(
                    "UPDATE articles SET is_read = ? WHERE id = ?",
                    (0, article_id),
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


def set_scroll_pos(db_path, article_id, pos):
    """记录文章阅读滚动位置（像素）。pos 非法（负数/非数字）时钳制为 0。"""
    try:
        value = float(pos)
    except (TypeError, ValueError):
        value = 0.0
    if value < 0:
        value = 0.0
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE articles SET scroll_pos = ? WHERE id = ?",
                (value, article_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_scroll_pos(db_path, article_id):
    """返回文章阅读滚动位置，不存在返回 0.0。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT scroll_pos FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if row is None:
            return 0.0
        return float(row["scroll_pos"])
    finally:
        conn.close()


def mark_all_read(db_path, feed_id=None, folder_id=None, tag_id=None, scope="unread"):
    """批量标记已读。scope: unread|starred|all。"""
    where = [_scope_clause(scope)]
    params = []
    if feed_id is not None:
        where.append("feed_id = ?")
        params.append(feed_id)
    if folder_id is not None:
        where.append("feed_id IN (SELECT id FROM feeds WHERE folder_id = ?)")
        params.append(folder_id)
    if tag_id is not None:
        where.append(
            "EXISTS (SELECT 1 FROM article_tags WHERE article_tags.article_id = articles.id AND tag_id = ?)"
        )
        params.append(tag_id)
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


def cluster_exists(db_path, cluster_id):
    """判断指定簇是否存在。"""
    conn = get_conn(db_path)
    try:
        cursor = conn.execute(
            "SELECT 1 FROM articles WHERE cluster_id = ? OR id = ? LIMIT 1",
            (cluster_id, cluster_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def mark_cluster_read(db_path, cluster_id, scope="unread"):
    """按簇标记已读。与 mark_all_read 一致，不写 last_read_at；solo 文章（cluster_id 为 NULL）按 id 命中。"""
    where = [_scope_clause(scope)]
    where.append("(cluster_id = ? OR id = ?)")
    params = [cluster_id, cluster_id]
    where_sql = " AND ".join(where).replace("a.", "")  # UPDATE 不支持表别名，去掉 a. 前缀
    with write_lock:
        conn = get_conn(db_path)
        try:
            cursor = conn.execute(
                f"UPDATE articles SET is_read = 1 WHERE {where_sql}", params
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


def _escape_fts5_query(q):
    """把用户输入转成安全的 FTS5 MATCH 查询串。

    双引号已被剥除。这里：
    - 把单引号 '、星号 *、左括号 (、右括号 )、冒号 :、脱字符 ^ 当作普通字符，
      整体用双引号包成短语，避免被 FTS5 当成语法。
    - 保留字 AND/OR/NOT 在 FTS5 中是运算符，把整段输入按空白切成 token，
      对每个 token 单独加双引号包成短语，运算符就退化为普通词。
    - 若处理后没有任何非空白 token，返回空串，由调用方回退 LIKE。
    """
    tokens = q.split()
    parts = []
    for tok in tokens:
        cleaned = tok.replace("'", "").replace("*", "").replace("(", "").replace(")", "").replace(":", "").replace("^", "")
        if not cleaned:
            continue
        parts.append('"' + cleaned + '"')
    return " ".join(parts)


def search_articles(db_path, q, limit=50):
    """FTS5 全文检索，返回 dict 列表（含 feed_title）。

    trigram 分词器无法处理短于 3 个字符的查询（形不成 trigram），
    这类短查询退化为 LIKE 匹配，保证单字/双字也能搜到结果。

    用户输入里的单引号、星号、括号、冒号、脱字符以及 AND/OR/NOT 等
    FTS5 特殊字符/保留字，会先被转义或剥除；转义后为空则退化为 LIKE；
    MATCH 抛 OperationalError 时也退化为 LIKE，不把异常抛给上层。
    """
    if q is None:
        return []
    q = q.strip()
    if not q:
        return []
    q = q.replace('"', "")
    if not q:
        return []
    columns = (
        "a.id, a.feed_id, a.guid, a.title, a.author, a.link, a.summary,"
        " a.content_html, a.content_text, a.published_at, a.fetched_at,"
        " a.is_read, a.is_starred, f.title AS feed_title"
    )
    conn = get_conn(db_path)
    try:
        escaped = _escape_fts5_query(q)
        if len(q) < 3 or not escaped:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = conn.execute(
                f"""SELECT {columns}
                      FROM articles a
                      JOIN feeds f ON f.id = a.feed_id
                     WHERE a.title LIKE ? ESCAPE '\\'
                        OR a.content_text LIKE ? ESCAPE '\\'
                        OR a.author LIKE ? ESCAPE '\\'
                     ORDER BY a.published_at DESC
                     LIMIT ?""",
                (like, like, like, limit),
            ).fetchall()
        else:
            try:
                rows = conn.execute(
                    f"""SELECT {columns}
                          FROM articles_fts
                          JOIN articles a ON a.id = articles_fts.rowid
                          JOIN feeds f ON f.id = a.feed_id
                         WHERE articles_fts MATCH ?
                         ORDER BY rank
                         LIMIT ?""",
                    (escaped, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                rows = conn.execute(
                    f"""SELECT {columns}
                          FROM articles a
                          JOIN feeds f ON f.id = a.feed_id
                         WHERE a.title LIKE ? ESCAPE '\\'
                            OR a.content_text LIKE ? ESCAPE '\\'
                            OR a.author LIKE ? ESCAPE '\\'
                         ORDER BY a.published_at DESC
                         LIMIT ?""",
                    (like, like, like, limit),
                ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def highlight_snippet(text, keyword, max_len=120):
    """在文本里高亮关键词，返回带 <mark> 的片段。"""
    if not text:
        return ""
    if not keyword:
        return html.escape(text)

    lower_text = text.lower()
    lower_kw = keyword.lower()
    idx = lower_text.find(lower_kw)

    if idx == -1:
        escaped = html.escape(text)
        if len(escaped) <= max_len:
            return escaped
        return escaped[:max_len]

    kw_len = len(keyword)
    half = max(0, (max_len - kw_len) // 2)
    start = max(0, idx - half)
    end = min(len(text), idx + kw_len + half)

    if end - start > max_len:
        end = start + max_len

    snippet = text[start:end]

    escaped_snippet = html.escape(snippet)

    lower_snippet = snippet.lower()
    pos = lower_snippet.find(lower_kw)

    if pos == -1:
        return escaped_snippet

    before = html.escape(snippet[:pos])
    matched = html.escape(snippet[pos:pos + kw_len])
    after = html.escape(snippet[pos + kw_len:])

    return before + "<mark>" + matched + "</mark>" + after


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
            "SELECT * FROM feeds WHERE enabled = 1 AND is_dead = 0 "
            "ORDER BY position ASC, id ASC"
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


def reactivate_feed(db_path, feed_id):
    """手动复活死源：清零 is_dead/dead_at/consecutive_failures。

    存在返回 True，不存在返回 False。
    """
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute(
                "UPDATE feeds SET is_dead = 0, dead_at = '', consecutive_failures = 0 "
                "WHERE id = ?",
                (feed_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def get_cluster_members(db_path, cluster_id, exclude_id=None):
    """返回同簇其他文章（id/title/feed_title/published_at），按 published_at 排序。"""
    conn = get_conn(db_path)
    try:
        sql = (
            "SELECT a.id AS id, a.title AS title, f.title AS feed_title, "
            "a.published_at AS published_at "
            "FROM articles a JOIN feeds f ON f.id = a.feed_id "
            "WHERE a.cluster_id = ? "
        )
        params = [cluster_id]
        if exclude_id is not None:
            sql += "AND a.id != ? "
            params.append(exclude_id)
        sql += "ORDER BY a.published_at IS NULL, a.published_at ASC, a.id ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job_state(db_path, key):
    """读取 job_state 中的值，不存在则返回 None。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM job_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_job_state(db_path, key, value):
    """写入或更新 job_state 中的值。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "INSERT INTO job_state(key, value, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------- tags ----------------

def create_tag(db_path, name):
    normalized = " ".join(name.split()).lower()
    if not normalized:
        raise ValueError("tag name cannot be empty")
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO tags(name, created_at) VALUES (?, ?)",
                (normalized, _now_iso()),
            )
            conn.commit()
            row = conn.execute("SELECT id, name FROM tags WHERE name = ?", (normalized,)).fetchone()
            return {"id": row["id"], "name": row["name"]}
        finally:
            conn.close()


def list_tags(db_path):
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT t.id, t.name, COUNT(a.article_id) AS article_count "
            "FROM tags t LEFT JOIN article_tags a ON a.tag_id = t.id "
            "GROUP BY t.id, t.name ORDER BY t.name ASC"
        ).fetchall()
        return [{"id": r["id"], "name": r["name"], "article_count": r["article_count"]} for r in rows]
    finally:
        conn.close()


def list_article_tags(db_path, article_id):
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT t.id, t.name FROM tags t "
            "JOIN article_tags a ON a.tag_id = t.id "
            "WHERE a.article_id = ? ORDER BY t.name ASC",
            (article_id,),
        ).fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]
    finally:
        conn.close()


def add_article_tag(db_path, article_id, tag_id):
    with write_lock:
        conn = get_conn(db_path)
        try:
            ok = conn.execute("SELECT (SELECT 1 FROM articles WHERE id = ?) AND (SELECT 1 FROM tags WHERE id = ?)", (article_id, tag_id)).fetchone()[0]
            if not ok or conn.execute("SELECT 1 FROM article_tags WHERE article_id = ? AND tag_id = ?", (article_id, tag_id)).fetchone():
                return False
            conn.execute("INSERT INTO article_tags (article_id, tag_id) VALUES (?, ?)", (article_id, tag_id))
            conn.commit()
            return True
        finally:
            conn.close()


def remove_article_tag(db_path, article_id, tag_id):
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute("DELETE FROM article_tags WHERE article_id = ? AND tag_id = ?", (article_id, tag_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# ---------------- article notes ----------------

def get_note(db_path, article_id):
    """读取文章笔记：文章不存在返回 None，无笔记返回空内容 dict。"""
    conn = get_conn(db_path)
    try:
        row = conn.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        note = conn.execute(
            "SELECT body, updated_at FROM article_notes WHERE article_id = ?", (article_id,)
        ).fetchone()
    finally:
        conn.close()
    if note is None:
        return {"article_id": article_id, "body": "", "updated_at": None}
    return {"article_id": article_id, "body": note[0], "updated_at": note[1]}


def save_note(db_path, article_id, body):
    """保存文章笔记：内容为空抛 ValueError，文章不存在抛 LookupError。"""
    body = (body or "").strip()
    if not body:
        raise ValueError("笔记内容为空")
    with write_lock:
        conn = get_conn(db_path)
        try:
            exists = conn.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone()
            if exists is None:
                raise LookupError("文章不存在")
            conn.execute(
                "INSERT INTO article_notes(article_id, body, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(article_id) DO UPDATE SET body=excluded.body, updated_at=excluded.updated_at",
                (article_id, body, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()
    return get_note(db_path, article_id)


def delete_note(db_path, article_id):
    """删除指定文章的阅读笔记，文章不存在返回 False，否则当且仅当确实删除一行时返回 True。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            cur = conn.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,))
            if cur.fetchone() is None:
                return False
            cur = conn.execute(
                "DELETE FROM article_notes WHERE article_id = ?", (article_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def list_notes(db_path, limit=50):
    """返回按更新时间倒序的最近非空阅读笔记列表，附带文章标题与订阅源标题。"""
    limit = max(1, min(int(limit), 200))
    conn = get_conn(db_path)
    try:
        cur = conn.execute(
            """
            SELECT n.article_id, n.body, n.updated_at,
                   a.title AS title, f.title AS feed_title
            FROM article_notes n
            JOIN articles a ON a.id = n.article_id
            JOIN feeds f ON f.id = a.feed_id
            WHERE n.body <> ''
            ORDER BY n.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "article_id": row[0],
                "body": row[1],
                "updated_at": row[2],
                "title": row[3],
                "feed_title": row[4],
            }
            for row in cur.fetchall()
        ]
    finally:
        conn.close()
