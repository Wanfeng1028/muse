"""feedflow.fetcher — RSS 抓取与正文提取。"""
from __future__ import annotations

import html
import re
import time
from datetime import UTC, datetime

import feedparser
import trafilatura

from . import store


def parse_feed_info(feed_url: str) -> dict:
    """解析源的元信息，失败抛 ValueError。"""
    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    feed = parsed.get("feed") or {}
    title = (feed.get("title") or "").strip()
    if not title:
        # 无标题视为解析失败
        raise ValueError("无法解析源标题")
    return {
        "title": title,
        "site_url": (feed.get("link") or "").strip(),
        "description": (feed.get("description") or "").strip(),
    }


def _html_to_text(h: str) -> str:
    """去掉 HTML 标签并还原实体，压缩空白。"""
    if not h:
        return ""
    text = re.sub(r"<[^>]+>", " ", h)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _iso(dt_struct) -> str | None:
    """把 feedparser 的 time.struct_time 转成 UTC ISO 字符串。"""
    if not dt_struct:
        return None
    try:
        ts = time.mktime(dt_struct)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except Exception:  # noqa: BLE001
        return None


def extract_text(link: str, summary_html: str, user_agent: str) -> tuple[str, str]:
    """返回 (content_html, content_text)。"""
    content_html = summary_html or ""
    content_text = ""
    if link:
        try:
            raw = trafilatura.fetch_url(link, no_ssl=False)
            if raw:
                text = trafilatura.extract(raw, favor_recall=True)
                if text:
                    content_text = text.strip()
        except Exception:  # noqa: BLE001
            content_text = ""
    if not content_text:
        content_text = _html_to_text(summary_html)
    return content_html, content_text


def fetch_feed(db_path: str, feed: dict, user_agent: str) -> dict:
    """抓取单个源，返回 {added, status, error}。"""
    feed_id = feed["id"]
    feed_url = feed["feed_url"]
    etag = feed.get("etag") or None
    modified = feed.get("modified") or None

    added = 0
    status = "ok"
    error = ""
    new_etag = feed.get("etag") or ""
    new_modified = feed.get("modified") or ""

    try:
        parsed = feedparser.parse(
            feed_url,
            etag=etag,
            modified=modified,
            agent=user_agent,
        )
        new_etag = parsed.get("etag") or new_etag
        new_modified = parsed.get("modified") or new_modified

        bozo = parsed.get("bozo")
        entries = parsed.get("entries") or []

        if bozo and not entries:
            bozo_exc = parsed.get("bozo_exception")
            status = "error"
            error = str(bozo_exc)[:300] if bozo_exc else "解析失败"
        else:
            for entry in entries:
                try:
                    guid = entry.get("id") or entry.get("link") or ""
                    if not guid:
                        continue
                    if store.article_exists(db_path, feed_id, guid):
                        continue
                    title = entry.get("title") or ""
                    author = entry.get("author") or ""
                    link = entry.get("link") or ""
                    summary = entry.get("summary") or ""
                    published_at = _iso(entry.get("published_parsed"))

                    content_html = summary
                    contents = entry.get("content") or []
                    if contents:
                        try:
                            content_html = contents[0].get("value") or summary
                        except Exception:  # noqa: BLE001
                            content_html = summary

                    content_html, content_text = extract_text(
                        link, summary, user_agent
                    )

                    store.insert_article(
                        db_path,
                        feed_id=feed_id,
                        guid=guid,
                        title=title,
                        author=author,
                        link=link,
                        summary=summary,
                        content_html=content_html,
                        content_text=content_text,
                        published_at=published_at,
                    )
                    added += 1
                except Exception as exc:  # noqa: BLE001
                    # 单条失败跳过，不影响整源
                    print(f"跳过条目失败: {exc}")
                    continue
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error = str(exc)[:300]

    # 更新抓取结果
    try:
        store.set_fetch_result(db_path, feed_id, status, error, new_etag, new_modified)
    except Exception as exc:  # noqa: BLE001
        print(f"更新抓取结果失败: {exc}")

    return {"added": added, "status": status, "error": error}
