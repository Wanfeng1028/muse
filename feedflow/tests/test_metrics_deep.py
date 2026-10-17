"""metrics 模块深度测试：解析边界、去重聚类、失败注入、幂等、排序稳定性。

本文件只测试 feedflow.metrics 的对外行为，不 mock 被测模块核心逻辑。
"""

import os
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from feedflow import metrics


@pytest.fixture(autouse=True)
def _reset_metrics_state():
    """每个用例前后把模块级计数器归零，避免用例间串味。"""
    metrics._fetch_total.clear()
    metrics._fetch_errors_total.clear()
    metrics._http_requests_total.clear()
    metrics._articles_stored_total = 0
    metrics._fetch_duration_sum = 0.0
    metrics._rate_limited_total = 0
    yield
    metrics._fetch_total.clear()
    metrics._fetch_errors_total.clear()
    metrics._http_requests_total.clear()
    metrics._articles_stored_total = 0
    metrics._fetch_duration_sum = 0.0
    metrics._rate_limited_total = 0


def _line_for(text, prefix):
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return None


def _value_of(text, prefix):
    line = _line_for(text, prefix)
    assert line is not None, f"没有找到以 {prefix} 开头的行"
    return line.rsplit(" ", 1)[1]


def test_empty_render_has_zero_defaults_and_help_type_lines():
    """空状态渲染：fetch_total 落回 ok/error 两个 0，且 HELP/TYPE 齐全。"""
    out = metrics.render()

    assert out.endswith("\n")
    assert out.count("# HELP feedflow_fetch_total") == 1
    assert out.count("# TYPE feedflow_fetch_total counter") == 1
    assert 'feedflow_fetch_total{status="ok"} 0' in out
    assert 'feedflow_fetch_total{status="error"} 0' in out
    assert "feedflow_articles_stored_total 0" in out
    assert "feedflow_fetch_duration_seconds_total 0" in out
    assert "feedflow_http_rate_limited_total 0" in out


def test_malformed_status_and_kind_labels_are_escaped():
    """畸形状态/错误类型里的引号、换行、反斜杠必须转义，不能破坏 exposition 行。"""
    metrics.inc_fetch('bad"status\nx')
    metrics.inc_fetch_error("timeout\\x")

    out = metrics.render()

    assert 'status="bad\\"status\\nx"' in out
    assert 'kind="timeout\\\\x"' in out
    assert out.count("feedflow_fetch_total{") == 1
    assert out.count("feedflow_fetch_errors_total{") == 1


def test_large_feed_counter_stays_exact_after_many_increments():
    """超大 feed：反复累加后计数不丢、不错位，导出仍是精确整数。"""
    for _ in range(5000):
        metrics.inc_fetch("ok")
    metrics.add_articles(12345)
    metrics.observe_fetch_duration(0.5)
    metrics.observe_fetch_duration(0.5)

    out = metrics.render()

    assert 'feedflow_fetch_total{status="ok"} 5000' in out
    assert "feedflow_articles_stored_total 12345" in out
    assert "feedflow_fetch_duration_seconds_total 1" in out


def test_empty_feed_add_articles_with_nonpositive_or_bad_input_is_noop():
    """空 feed / 脏输入：add_articles 对 0、负数、非数字都静默忽略。"""
    metrics.add_articles(0)
    metrics.add_articles(-3)
    metrics.add_articles("abc")
    metrics.add_articles(None)

    out = metrics.render()

    assert "feedflow_articles_stored_total 0" in out
    value_lines = [
        line for line in out.splitlines()
        if line.startswith("feedflow_articles_stored_total ")
    ]
    assert len(value_lines) == 1


def test_observe_fetch_duration_ignores_negative_and_garbage():
    """非 UTF8 之外的脏时长：负数和非数字不能污染 duration sum。"""
    metrics.observe_fetch_duration(-1.0)
    metrics.observe_fetch_duration("not-a-number")
    metrics.observe_fetch_duration(2.5)

    out = metrics.render()

    assert "feedflow_fetch_duration_seconds_total 2.5" in out
    assert "feedflow_fetch_duration_seconds_total -" not in out


def test_float_formatting_integer_valued_float_prints_without_decimal():
    """_fmt 对整数取值的 float 去掉小数点，非整数保留 repr。"""
    assert metrics._fmt(3.0) == "3"
    assert metrics._fmt(3.5) == "3.5"
    assert metrics._fmt(7) == "7"


def test_http_requests_grouped_and_sorted_by_method_route_status():
    """去重聚类式归并：同三元组累加，不同三元组分行，且按 key 排序稳定。"""
    metrics.inc_http_request("GET", "/feed", 200)
    metrics.inc_http_request("GET", "/feed", 200)
    metrics.inc_http_request("POST", "/feed", 404)
    metrics.inc_http_request("GET", "/feed", 200)

    out = metrics.render()
    lines = [l for l in out.splitlines() if l.startswith("feedflow_http_requests_total{")]

    assert len(lines) == 2
    assert lines[0].startswith('feedflow_http_requests_total{method="GET",route="/feed",status="200"}')
    assert lines[0].endswith(" 3")
    assert lines[1].startswith('feedflow_http_requests_total{method="POST",route="/feed",status="404"}')
    assert lines[1].endswith(" 1")


def test_inc_http_request_empty_route_falls_back_to_unknown():
    """转载/空路由变体：route 为空时归一到 unknown，不产生空标签。"""
    metrics.inc_http_request("GET", "", 200)
    metrics.inc_http_request("GET", None, 200)

    out = metrics.render()

    assert 'route="unknown"' in out
    assert 'route=""' not in out
    assert out.count('feedflow_http_requests_total{method="GET",route="unknown",status="200"}') == 1
    assert 'feedflow_http_requests_total{method="GET",route="unknown",status="200"} 2' in out


def test_rate_limited_counter_accumulates_each_rejection():
    """失败注入式限流：每次拒绝都计数，重复拉取不丢不重。"""
    for _ in range(4):
        metrics.inc_rate_limited()

    out = metrics.render()

    assert "feedflow_http_rate_limited_total 4" in out
    value_lines = [
        line for line in out.splitlines()
        if line.startswith("feedflow_http_rate_limited_total ")
    ]
    assert len(value_lines) == 1


def test_render_is_idempotent_and_does_not_mutate_counters():
    """幂等：重复拉取 render 结果一致，且不会重复入库/重复计数。"""
    metrics.inc_fetch("ok")
    metrics.add_articles(2)
    metrics.inc_fetch_error("timeout")

    first = metrics.render()
    second = metrics.render()
    third = metrics.render()

    assert first == second
    assert second == third
    assert "feedflow_articles_stored_total 2" in first
    assert 'feedflow_fetch_total{status="ok"} 1' in first
    assert 'feedflow_fetch_errors_total{kind="timeout"} 1' in first


def test_status_and_kind_output_sorted_stably():
    """重要性排序稳定性：不同 status/kind 输出顺序固定，不受插入顺序影响。"""
    metrics.inc_fetch("z_error")
    metrics.inc_fetch("a_ok")
    metrics.inc_fetch("m_warn")
    metrics.inc_fetch_error("zeta")
    metrics.inc_fetch_error("alpha")

    out = metrics.render()
    fetch_lines = [l for l in out.splitlines() if l.startswith("feedflow_fetch_total{")]
    err_lines = [l for l in out.splitlines() if l.startswith("feedflow_fetch_errors_total{")]

    assert fetch_lines == [
        'feedflow_fetch_total{status="a_ok"} 1',
        'feedflow_fetch_total{status="m_warn"} 1',
        'feedflow_fetch_total{status="z_error"} 1',
    ]
    assert err_lines == [
        'feedflow_fetch_errors_total{kind="alpha"} 1',
        'feedflow_fetch_errors_total{kind="zeta"} 1',
    ]


def test_render_with_db_path_exposes_gauges(tmp_db):
    """带 db_path 渲染：四个 gauge 段落都出现且类型是 gauge。"""
    out = metrics.render(db_path=tmp_db)

    for name in (
        "feedflow_feeds_total",
        "feedflow_articles_total",
        "feedflow_unread_total",
        "feedflow_starred_total",
    ):
        assert f"# HELP {name} " in out
        assert f"# TYPE {name} gauge" in out
        line = _line_for(out, name + " ")
        assert line is not None
        value = line.rsplit(" ", 1)[1]
        assert value.isdigit()


def test_render_with_broken_db_path_still_returns_full_metrics():
    """失败注入：DB 打不开时 /metrics 不炸，gauge 全部回退为 0。"""
    out = metrics.render(db_path="/nonexistent/dir/definitely_missing.db")

    assert "# TYPE feedflow_fetch_total counter" in out
    assert "feedflow_feeds_total 0" in out
    assert "feedflow_articles_total 0" in out
    assert "feedflow_unread_total 0" in out
    assert "feedflow_starred_total 0" in out


def test_concurrent_increments_are_thread_safe():
    """并发拉取：多线程同时加计数，最终值精确等于总次数。"""
    threads = []
    per_thread = 500

    def worker():
        for _ in range(per_thread):
            metrics.inc_fetch("ok")
            metrics.inc_http_request("GET", "/feed", 200)

    for _ in range(8):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    out = metrics.render()

    assert 'feedflow_fetch_total{status="ok"} 4000' in out
    assert 'feedflow_http_requests_total{method="GET",route="/feed",status="200"} 4000' in out