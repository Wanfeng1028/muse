"""全文 RSS 输出：把文章正文渲染成 RSS 2.0 XML。

纯函数模块，不依赖 flask.request，便于测试。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

from . import fetcher, store


def _format_pubdate(row: dict) -> str | None:
    """把 published_at / fetched_at 转成 RFC822；都失败返回 None。"""
    for key in ("published_at", "fetched_at"):
        raw = row.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=None)
        try:
            return format_datetime(dt, usegmt=dt.tzinfo is not None)
        except (TypeError, ValueError):
            continue
    return None


_ILLEGAL_XML_RE = None


def _strip_illegal_xml(text: str) -> str:
    """剔除 XML 1.0 非法的控制字符。"""
    global _ILLEGAL_XML_RE
    if _ILLEGAL_XML_RE is None:
        import re
        _ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    return _ILLEGAL_XML_RE.sub("", text)


def _cdata_safe(text: str) -> str:
    """把 ]]> 拆开，避免破坏 CDATA 段；剔除 XML 1.0 非法控制字符。"""
    text = _strip_illegal_xml(text)
    return text.replace("]]>", "]]]]><![CDATA[>")


def _full_text(row: dict) -> str:
    """优先 content_text，回落 summary 去标签文本。"""
    content = row.get("content_text")
    if content and content.strip():
        return content
    summary = row.get("summary") or ""
    return fetcher._html_to_text(summary)


def build_rss(db_path, feed_id=None, folder_id=None, limit=50) -> tuple[str, str]:
    """构建全文 RSS，返回 (xml_text, etag)。"""
    capped = min(limit, 50)
    _total, rows = store.list_articles(
        db_path,
        scope="all",
        feed_id=feed_id,
        folder_id=folder_id,
        limit=capped,
        offset=0,
    )

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<rss version="2.0">')
    parts.append("<channel>")
    parts.append("<title>FeedFlow 全文 RSS</title>")
    parts.append("<link>/</link>")
    parts.append("<description>FeedFlow 自托管阅读器全文输出</description>")

    for row in rows:
        title = escape(_strip_illegal_xml(row.get("title") or ""))
        link = row.get("link") or ""
        guid_raw = row.get("guid") or link
        guid = escape(guid_raw)
        body = _cdata_safe(_full_text(row))

        parts.append("<item>")
        parts.append("<title>" + title + "</title>")
        parts.append("<link>" + escape(link) + "</link>")
        parts.append("<guid>" + guid + "</guid>")
        pubdate = _format_pubdate(row)
        if pubdate is not None:
            parts.append("<pubDate>" + pubdate + "</pubDate>")
        parts.append("<description><![CDATA[" + body + "]]></description>")
        parts.append("</item>")

    parts.append("</channel>")
    parts.append("</rss>")

    xml_text = "".join(parts)
    digest = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
    etag = '"' + digest + '"'
    return xml_text, etag
