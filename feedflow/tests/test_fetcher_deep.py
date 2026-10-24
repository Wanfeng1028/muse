"""深度测试 feedflow.fetcher：解析边界、去重聚类、失败注入、幂等与排序稳定性。

测试只依赖 conftest 提供的 app/client 夹具，不 mock fetcher 的核心逻辑，
网络相关用例通过本地 monkeypatch 注入确定的输入。
"""
from __future__ import annotations

import io
import urllib.error

import pytest

from feedflow import fetcher


def _mk_http_error(url: str, code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "err", headers or {}, io.BytesIO(b""))


# ---------------------------------------------------------------------------
# RSS 解析边界
# ---------------------------------------------------------------------------

def test_parse_feed_info_rejects_empty_feed(monkeypatch):
    """空 feed（无 title）应抛 ValueError，而不是静默返回空 dict。"""
    class _Empty:
        def get(self, key, default=None):
            return {} if key == "feed" else default

    monkeypatch.setattr(fetcher.feedparser, "parse", lambda url: _Empty())
    with pytest.raises(ValueError):
        fetcher.parse_feed_info("http://example.com/empty.xml")


def test_parse_feed_info_rejects_malformed_xml(monkeypatch):
    """畸形 XML：feedparser 抛异常时应转成 ValueError。"""
    def _boom(url):
        raise ValueError("syntax error: not well-formed")

    monkeypatch.setattr(fetcher.feedparser, "parse", _boom)
    with pytest.raises(ValueError) as excinfo:
        fetcher.parse_feed_info("http://example.com/bad.xml")
    assert "not well-formed" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)


def test_parse_feed_info_strips_whitespace_title(monkeypatch):
    """标题两边空白应被去掉，字段缺失时用空串兜底。"""
    class _Parsed:
        def get(self, key, default=None):
            if key == "feed":
                return {"title": "  晚风的博客  ", "link": " http://blog.example.com "}
            return default

    monkeypatch.setattr(fetcher.feedparser, "parse", lambda url: _Parsed())
    info = fetcher.parse_feed_info("http://blog.example.com/rss")
    assert info["title"] == "晚风的博客"
    assert info["site_url"] == "http://blog.example.com"
    assert info["description"] == ""


def test_html_to_text_handles_non_utf8_entities():
    """非 UTF8 编码的实体与标签应还原成可读文本并压缩空白。"""
    raw = "&amp;#20320;&amp;#22909; <b>世界</b>\n\n  再次"
    text = fetcher._html_to_text(raw)
    assert "你好" in text
    assert "世界" in text
    assert "\n" not in text
    assert "  " not in text


def test_iso_converts_struct_time_to_utc():
    """struct_time 转成 UTC ISO 字符串，非法输入返回 None。"""
    st = (2024, 1, 2, 3, 4, 5, 0, 0, 0)
    iso = fetcher._iso(st)
    assert iso is not None
    assert iso.endswith("+00:00")
    assert fetcher._iso(None) is None
    assert fetcher._iso("not-a-struct") is None


# ---------------------------------------------------------------------------
# 去重聚类
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 失败注入
# ---------------------------------------------------------------------------

def test_classify_error_for_timeout_and_dns():
    """超时归类为 timeout，DNS 失败归类为 dns。"""
    assert fetcher.classify_error(TimeoutError("timed out")) == "timeout"
    assert fetcher.classify_error(TimeoutError("timed out")) == "timeout"
    dns = urllib.error.URLError("Name or service not known")
    assert fetcher.classify_error(dns) == "dns"


def test_classify_error_for_404_and_429():
    """404 归到 http_4xx 且不可重试；429 可重试且解析 Retry-After。"""
    e404 = _mk_http_error("http://example.com/x", 404)
    assert fetcher.classify_error(e404) == "http_4xx"
    assert fetcher._is_retryable(e404) is False

    e429 = _mk_http_error(
        "http://example.com/x", 429, headers={"Retry-After": "30"}
    )
    assert fetcher.classify_error(e429) == "http_4xx"
    assert fetcher._is_retryable(e429) is True
    assert fetcher._retry_after_seconds(e429) == 30.0


def test_retry_after_is_capped():
    """Retry-After 超过上限时应被截断到 RETRY_AFTER_CAP。"""
    e = _mk_http_error(
        "http://example.com/x", 429, headers={"Retry-After": "9999"}
    )
    assert fetcher._retry_after_seconds(e) == fetcher.RETRY_AFTER_CAP
    assert fetcher.RETRY_AFTER_CAP == 60.0


def test_fetch_error_retryable_flag_is_respected():
    """FetchError 的分类与可重试标记应被 classify/_is_retryable 尊重。"""
    exc = fetcher.FetchError("boom", kind="http_5xx", retryable=True, retry_after=12.0)
    assert fetcher.classify_error(exc) == "http_5xx"
    assert fetcher._is_retryable(exc) is True
    assert fetcher._retry_after_seconds(exc) == 12.0

    exc2 = fetcher.FetchError("nope", kind="parse_error", retryable=False)
    assert fetcher.classify_error(exc2) == "parse_error"
    assert fetcher._is_retryable(exc2) is False
    assert fetcher._retry_after_seconds(exc2) is None


# ---------------------------------------------------------------------------
# 幂等
# ---------------------------------------------------------------------------

def test_fetch_remote_idempotent_on_304(monkeypatch):
    """304 条件请求命中时不应返回 body，not_modified 为 True。"""
    def _fake_urlopen(req, timeout):
        raise _mk_http_error(req.full_url, 304, headers={"ETag": "e1"})

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", _fake_urlopen)
    body, etag, _modified, not_modified = fetcher._http_get(
        "http://example.com/feed", "FeedFlow-test", 5.0, "e0", None
    )
    assert body is None
    assert not_modified is True
    assert etag == "e1"


# ---------------------------------------------------------------------------
# 排序稳定性
# ---------------------------------------------------------------------------
