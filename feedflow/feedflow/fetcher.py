"""feedflow.fetcher — RSS 抓取与正文提取。"""
from __future__ import annotations

import html
import os
import random
import re
import socket
import time
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime

import feedparser
import trafilatura
from trafilatura.settings import DEFAULT_CONFIG

from . import store
from .logging import get_logger

logger = get_logger("feedflow.fetcher")

# 重试基础退避（秒）
RETRY_BASE_SECONDS = 2.0
# 429 时 Retry-After 最多等待的秒数
RETRY_AFTER_CAP = 60.0


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
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
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


_download_config_cache: dict = {}

def _download_config(timeout: float):
    """按超时秒数缓存 trafilatura 下载配置（设置 DOWNLOAD_TIMEOUT）。"""
    key = int(timeout)
    cfg = _download_config_cache.get(key)
    if cfg is None:
        cfg = deepcopy(DEFAULT_CONFIG)
        cfg["DEFAULT"]["DOWNLOAD_TIMEOUT"] = str(key)
        _download_config_cache[key] = cfg
    return cfg

def extract_text(link: str, summary_html: str, user_agent: str,
                 extract_timeout: float = 15) -> tuple[str, str]:
    """返回 (content_html, content_text)。extract_timeout 为单篇正文下载超时（秒）。"""
    content_html = summary_html or ""
    content_text = ""
    if link:
        try:
            raw = trafilatura.fetch_url(
                link, no_ssl=False, config=_download_config(extract_timeout)
            )
            if raw:
                text = trafilatura.extract(raw, favor_recall=True)
                if text:
                    content_text = text.strip()
        except Exception:  # noqa: BLE001
            content_text = ""
    if not content_text:
        content_text = _html_to_text(summary_html)
    return content_html, content_text



class FetchError(Exception):
    """网络抓取层的自定义异常，携带分类与可重试标记。"""

    def __init__(self, message: str, kind: str, retryable: bool, retry_after: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after


def classify_error(exc: BaseException) -> str:
    """把异常分类成 timeout / dns / http_4xx / http_5xx / parse_error / unknown。"""
    # 已经是 FetchError，直接用其 kind
    if isinstance(exc, FetchError):
        return exc.kind

    # 超时类
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "timeout"

    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 429:
            return "http_4xx"
        if 400 <= code < 500:
            return "http_4xx"
        if 500 <= code < 600:
            return "http_5xx"
        return "unknown"

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "timeout"
        reason_text = str(reason).lower()
        if "name or service not known" in reason_text or "nodename nor servname" in reason_text:
            return "dns"
        if "timed out" in reason_text:
            return "timeout"
        return "unknown"

    if isinstance(exc, (ValueError,)):
        # feedparser 的解析类问题常以字符串形式抛出
        return "parse_error"

    return "unknown"


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否应当重试。"""
    if isinstance(exc, FetchError):
        return exc.retryable
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, urllib.error.URLError)


def _retry_after_seconds(exc: BaseException) -> float | None:
    """从 HTTPError 中解析 Retry-After，返回秒数（封顶 60 秒）。"""
    if isinstance(exc, FetchError):
        if exc.retry_after is not None:
            return min(float(exc.retry_after), RETRY_AFTER_CAP)
        return None
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
        header = exc.headers.get("Retry-After") if exc.headers else None
        if not header:
            return None
        try:
            seconds = float(header)
        except (TypeError, ValueError):
            return None
        return min(seconds, RETRY_AFTER_CAP)
    return None


def _http_get(url: str, user_agent: str, timeout: float, etag: str | None,
              modified: str | None) -> tuple[bytes | None, str | None, str | None, bool]:
    """用 urllib 发起 GET 条件请求。

    返回 (body, new_etag, new_modified, not_modified)。
    304 时 body 为 None 且 not_modified=True。
    其它异常原样抛出，交由调用方分类/重试。
    """
    headers = {"User-Agent": user_agent, "Accept": "*/*"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            new_etag = resp.headers.get("ETag")
            new_modified = resp.headers.get("Last-Modified")
            return body, new_etag, new_modified, False
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            # 304 无正文，读取响应头即可
            new_etag = exc.headers.get("ETag") if exc.headers else None
            new_modified = exc.headers.get("Last-Modified") if exc.headers else None
            return None, new_etag, new_modified, True
        raise


def _fetch_remote(url: str, user_agent: str, timeout: float, retries: int,
                  etag: str | None, modified: str | None,
                  feed_id: int) -> tuple[bytes | None, str | None, str | None, bool]:
    """带指数退避重试的远程抓取。

    返回 (body, new_etag, new_modified, not_modified)。
    """
    attempt = 0
    last_exc: BaseException | None = None
    while attempt <= retries:
        attempt += 1
        try:
            return _http_get(url, user_agent, timeout, etag, modified)
        except BaseException as exc:
            last_exc = exc
            kind = classify_error(exc)
            retryable = _is_retryable(exc)
            logger.warning(
                "抓取失败",
                extra={
                    "feed_id": feed_id,
                    "kind": kind,
                    "attempt": attempt,
                    "retryable": retryable,
                },
            )
            if not retryable or attempt > retries:
                raise
            # 指数退避 + 小 jitter
            delay = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            ra = _retry_after_seconds(exc)
            if ra is not None:
                delay = max(delay, ra)
            delay += random.uniform(0, 0.5)
            time.sleep(delay)
    # 理论不可达
    if last_exc is not None:
        raise last_exc
    raise FetchError("未知抓取错误", "unknown", False)


def _parse_entries(parsed: dict, db_path: str, feed_id: int, user_agent: str,
                   extract_timeout: float = 15) -> int:

    """遍历条目写入数据库，返回新增数量。单条失败不影响整源。"""
    added = 0
    entries = parsed.get("entries") or []
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

            content_html, content_text = extract_text(
                link, summary, user_agent, extract_timeout=extract_timeout
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
            logger.warning(
                "跳过条目失败",
                extra={"feed_id": feed_id, "kind": "unknown", "attempt": 0, "error": str(exc)[:200]},
            )
            continue
    return added


def fetch_feed(db_path: str, feed: dict, user_agent: str,
               timeout: float = 20, retries: int = 3,
               extract_timeout: float = 15, dead_after=None) -> dict:

    """抓取单个源，返回 {added, status, error}。

    - feed_url 为本地路径时直接交给 feedparser 解析，不走网络层。
    - 远程抓取使用 urllib，支持 etag/modified 条件请求与指数退避重试。
    """
    from . import metrics as _metrics

    _t0 = time.monotonic()
    feed_id = feed["id"]
    feed_url = feed["feed_url"]
    etag = feed.get("etag") or None
    modified = feed.get("modified") or None

    added = 0
    status = "ok"
    error = ""
    error_kind = ""
    prev_failures = int(feed.get("consecutive_failures") or 0)
    new_etag = feed.get("etag") or ""
    new_modified = feed.get("modified") or ""

    # 本地文件：直接 feedparser 解析，不走网络
    if os.path.exists(feed_url):
        try:
            parsed = feedparser.parse(feed_url)
            bozo = parsed.get("bozo")
            entries = parsed.get("entries") or []
            if bozo and not entries:
                bozo_exc = parsed.get("bozo_exception")
                status = "error"
                error_kind = "parse_error"
                error = str(bozo_exc)[:300] if bozo_exc else "解析失败"
            else:
                added = _parse_entries(
                    parsed, db_path, feed_id, user_agent,
                    extract_timeout=extract_timeout,
                )
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error_kind = classify_error(exc)
            error = str(exc)[:300]
        new_failures = prev_failures + 1 if status == "error" else 0

        try:
            store.set_fetch_result(
                db_path, feed_id, status, error, new_etag, new_modified,
                error_kind=error_kind, failures=new_failures,
                dead_after=dead_after,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "更新抓取结果失败",
                extra={"feed_id": feed_id, "kind": "unknown", "attempt": 0, "error": str(exc)[:200]},
            )
        try:
            _metrics.observe_fetch_duration(time.monotonic() - _t0)
            _metrics.inc_fetch("ok" if status == "ok" else "error")
            if status == "error" and error_kind:
                _metrics.inc_fetch_error(error_kind)
            _metrics.add_articles(added)
        except Exception as exc:  # noqa: BLE001  # 指标埋点不许影响抓取主流程，故意宽捕获
            logger.warning("指标埋点失败", extra={"feed_id": feed_id, "error": str(exc)[:200]})
        return {"added": added, "status": status, "error": error}

    # 远程抓取
    try:
        body, got_etag, got_modified, not_modified = _fetch_remote(
            feed_url, user_agent, timeout, retries, etag, modified, feed_id,
        )
        if got_etag:
            new_etag = got_etag
        if got_modified:
            new_modified = got_modified

        if not_modified:
            # 304：成功无更新
            status = "ok"
            added = 0
        else:
            parsed = feedparser.parse(body or b"")
            bozo = parsed.get("bozo")
            entries = parsed.get("entries") or []
            if bozo and not entries:
                bozo_exc = parsed.get("bozo_exception")
                status = "error"
                error_kind = "parse_error"
                error = str(bozo_exc)[:300] if bozo_exc else "解析失败"
            else:
                added = _parse_entries(
                    parsed, db_path, feed_id, user_agent,
                    extract_timeout=extract_timeout,
                )
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error_kind = classify_error(exc)
        error = str(exc)[:300]

    new_failures = prev_failures + 1 if status == "error" else 0


    try:
        store.set_fetch_result(
            db_path, feed_id, status, error, new_etag, new_modified,
            error_kind=error_kind, failures=new_failures,
            dead_after=dead_after,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "更新抓取结果失败",
            extra={"feed_id": feed_id, "kind": "unknown", "attempt": 0, "error": str(exc)[:200]},
        )

    try:
        _metrics.observe_fetch_duration(time.monotonic() - _t0)
        _metrics.inc_fetch("ok" if status == "ok" else "error")
        if status == "error" and error_kind:
            _metrics.inc_fetch_error(error_kind)
        _metrics.add_articles(added)
    except Exception as exc:  # noqa: BLE001  # 指标埋点不许影响抓取主流程，故意宽捕获
        logger.warning("指标埋点失败", extra={"feed_id": feed_id, "error": str(exc)[:200]})
    return {"added": added, "status": status, "error": error}
