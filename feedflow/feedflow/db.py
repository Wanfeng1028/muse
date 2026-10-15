"""数据库访问层：连接、初始化、通用读写封装。"""

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

# 所有写操作共用的模块级锁，串行化写事务
write_lock = threading.Lock()


def get_conn(db_path) -> sqlite3.Connection:
    """创建新连接，启用 Row 工厂并允许跨线程使用。"""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path) -> None:
    """初始化数据库：建父目录、设置 PRAGMA、建表、建 FTS 与索引。"""
    path = Path(str(db_path))
    parent = path.parent
    if str(parent) and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    conn = get_conn(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                title TEXT NOT NULL DEFAULT '',
                site_url TEXT NOT NULL DEFAULT '',
                feed_url TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                interval_min INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_fetched_at TEXT,
                last_status TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                etag TEXT NOT NULL DEFAULT '',
                modified TEXT NOT NULL DEFAULT '',
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
                guid TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                link TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                content_html TEXT NOT NULL DEFAULT '',
                content_text TEXT NOT NULL DEFAULT '',
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_starred INTEGER NOT NULL DEFAULT 0,
                UNIQUE(feed_id, guid)
            )
            """
        )

        # 全文索引虚表（trigram 分词，内容镜像 articles 表）
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title,
                content_text,
                author,
                content='articles',
                content_rowid='id',
                tokenize='trigram'
            )
            """
        )

        # 三个触发器保持 FTS 与 articles 同步
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, content_text, author)
                VALUES (new.id, new.title, new.content_text, new.author);
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, content_text, author)
                VALUES ('delete', old.id, old.title, old.content_text, old.author);
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, content_text, author)
                VALUES ('delete', old.id, old.title, old.content_text, old.author);
                INSERT INTO articles_fts(rowid, title, content_text, author)
                VALUES (new.id, new.title, new.content_text, new.author);
            END
            """
        )

        # 常用索引
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_feed ON articles(feed_id, published_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_read ON articles(feed_id, is_read)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_starred ON articles(is_starred)"
        )

        conn.commit()

        # 执行版本化迁移（幂等）
        run_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def utcnow() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(UTC).isoformat()


def execute_write(db_path, sql, params=()) -> int:
    """加锁执行写操作，返回 lastrowid。"""
    with write_lock:
        conn = get_conn(db_path)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def query_all(db_path, sql, params=()) -> list:
    """查询多行，返回 dict 列表。"""
    conn = get_conn(db_path)
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_one(db_path, sql, params=()):
    """查询单行，返回 dict 或 None。"""
    conn = get_conn(db_path)
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 版本化迁移（PRAGMA user_version）
# ---------------------------------------------------------------------------


MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "新增 simhash/cluster_id/last_error_kind/consecutive_failures 及 job_state 表",
        [
            # articles 新增列
            "ALTER TABLE articles ADD COLUMN simhash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE articles ADD COLUMN cluster_id INTEGER",
            # feeds 新增列
            "ALTER TABLE feeds ADD COLUMN last_error_kind TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE feeds ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0",
            # job_state 表
            (
                "CREATE TABLE IF NOT EXISTS job_state (\n"
                "    key TEXT PRIMARY KEY,\n"
                "    value TEXT NOT NULL DEFAULT '',\n"
                "    updated_at TEXT NOT NULL DEFAULT ''\n"
                ")"
            ),
            # 索引
            "CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id)",
        ],
    ),
    (
        2,
        "新增关键词/来源权重/通用设置表（v1.2 重要性排序）",
        [
            (
                "CREATE TABLE IF NOT EXISTS keywords (\n"
                "    id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "    keyword TEXT NOT NULL UNIQUE,\n"
                "    weight REAL NOT NULL DEFAULT 1.0,\n"
                "    created_at TEXT NOT NULL\n"
                ")"
            ),
            (
                "CREATE TABLE IF NOT EXISTS feed_weights (\n"
                "    feed_id INTEGER PRIMARY KEY REFERENCES feeds(id) ON DELETE CASCADE,\n"
                "    weight REAL NOT NULL DEFAULT 1.0,\n"
                "    learned REAL NOT NULL DEFAULT 1.0,\n"
                "    updated_at TEXT NOT NULL\n"
                ")"
            ),
            (
                "CREATE TABLE IF NOT EXISTS settings (\n"
                "    key TEXT PRIMARY KEY,\n"
                "    value TEXT NOT NULL DEFAULT '',\n"
                "    updated_at TEXT NOT NULL\n"
                ")"
            ),
            "CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword)",
        ],
    ),
    (
        3,
        "articles 新增 last_read_at（标记已读的时间，Fever API 的 unread_recently_read 用）",
        [
            "ALTER TABLE articles ADD COLUMN last_read_at TEXT",
        ],
    ),
]





def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """检查指定表是否存在指定列。"""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.DatabaseError:
        return False
    for row in rows:
        # row 可能是 sqlite3.Row 或 tuple，兼容取值
        try:
            name = row["name"]
        except (TypeError, IndexError):
            name = row[1]
        if name == column:
            return True
    return False


def _parse_add_column(sql: str) -> tuple[str, str] | None:
    """从 ``ALTER TABLE x ADD COLUMN y ...`` 语句解析出 (table, column)。

    解析失败返回 None（此时按普通语句执行）。
    """
    tokens = sql.strip().split()
    if len(tokens) < 6:
        return None
    if tokens[0].upper() != "ALTER" or tokens[1].upper() != "TABLE":
        return None
    if tokens[3].upper() != "ADD" or tokens[4].upper() != "COLUMN":
        return None
    table = tokens[2].strip('`"[]')
    column = tokens[5].strip('`"[],')
    if not table or not column:
        return None
    return table, column


def _apply_statements(conn: sqlite3.Connection, statements: list[str]) -> None:
    """执行一组迁移语句。

    对 ``ALTER TABLE ... ADD COLUMN`` 语句先检查列是否已存在，已存在则跳过；
    其余语句直接执行（建议使用 ``IF NOT EXISTS`` 保证幂等）。
    """
    for sql in statements:
        parsed = _parse_add_column(sql)
        if parsed is not None:
            table, column = parsed
            if _column_exists(conn, table, column):
                # 老库已包含该列，跳过以避免 duplicate column 错误。
                continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            # 对加列语句，若仍因"列已存在"报错，也视作已应用。
            if parsed is not None and "duplicate column" in str(exc).lower():
                continue
            raise


def _get_user_version(conn: sqlite3.Connection) -> int:
    """读取 PRAGMA user_version。"""
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError, IndexError):
        return 0


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    """设置 PRAGMA user_version（SQLite 不支持参数绑定，需拼接整数）。"""
    conn.execute(f"PRAGMA user_version = {int(version)}")


def run_migrations(conn: sqlite3.Connection) -> int:
    """依次执行缺失的迁移版本，返回执行后的 user_version。"""
    current = _get_user_version(conn)
    target = current
    for version, _description, statements in sorted(MIGRATIONS, key=lambda m: m[0]):
        if version <= current:
            continue
        _apply_statements(conn, statements)
        target = version
        _set_user_version(conn, target)
    return target
