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
