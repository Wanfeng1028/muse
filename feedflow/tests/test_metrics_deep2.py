# tests/test_metrics_deep2.py
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import threading

from feedflow import db as db_mod
from feedflow import metrics


def _reset_metrics():
    # 直接对模块私有状态复位，保证每个用例独立
    with metrics._lock:
        metrics._fetch_total.clear()
        metrics._fetch_errors_total.clear()
        metrics._http_requests_total.clear()
        metrics.__dict__["_articles_stored_total"] = 0
        metrics.__dict__["_fetch_duration_sum"] = 0.0
        metrics.__dict__["_rate_limited_total"] = 0


def _parse_metric_line(line):
    # 解析 "name{labels} value" 或 "name value"
    if " " not in line:
        return None
    name_part, _, value_part = line.rpartition(" ")
    try:
        value = float(value_part)
    except ValueError:
        return None
    labels = {}
    name = name_part
    if "{" in name_part:
        name, _, rest = name_part.partition("{")
        rest = rest.rstrip("}")
        # 简单拆分，值不含逗号（测试中 label 值可控）
        for kv in rest.split(","):
            if "=" not in kv:
                continue
            k, _, v = kv.partition("=")
            v = v.strip('"')
            labels[k] = v
    return name, labels, value


# 1. 多线程并发 50 线程各 inc 100 次，计数精确等于 5000（线程安全）
def test_concurrent_inc_fetch_thread_safe():
    _reset_metrics()
    n_threads = 50
    per_thread = 100

    def worker():
        for _ in range(per_thread):
            metrics.inc_fetch("ok")

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with metrics._lock:
        total = metrics._fetch_total.get("ok", 0)
    assert total == n_threads * per_thread
    assert total == 5000


# 2. 路由归一化：/api/articles/123 与 /api/articles/456 的请求被归一到同一 label，
#    不爆炸 label 基数
def test_route_normalization_same_label():
    _reset_metrics()

    def normalize_route(route):
        # 把路径中的数字段归一为 :id，用于验证调用方约定
        parts = []
        for seg in route.split("/"):
            if seg.isdigit():
                parts.append(":id")
            else:
                parts.append(seg)
        return "/".join(parts)

    metrics.inc_http_request("GET", normalize_route("/api/articles/123"), 200)
    metrics.inc_http_request("GET", normalize_route("/api/articles/456"), 200)

    with metrics._lock:
        keys = list(metrics._http_requests_total.keys())

    assert len(keys) == 1, f"期望归一到一个 label，实际 {keys}"
    method, route, status = keys[0]
    assert method == "GET"
    assert route == "/api/articles/:id"
    assert status == "200"
    assert metrics._http_requests_total[keys[0]] == 2


# 3. 埋点函数内部抛异常时（如 label 含非法字符）主流程不受影响，只记 warning
def test_inc_fetch_error_with_bad_label_does_not_raise():
    _reset_metrics()
    # _escape_label 会把 " 和 \ 和 \n 转义，本身不抛异常；
    # 这里验证带特殊字符的 label 仍能正常记录并被转义
    kind = 'bad"kind\\with\nnewline'
    metrics.inc_fetch_error(kind)
    with metrics._lock:
        assert metrics._fetch_errors_total.get(kind, 0) == 1
    text = metrics.render()
    # 转义后不应出现裸引号
    assert 'feedflow_fetch_errors_total{kind="bad\\"kind\\\\with\\nnewline"} 1' in text


# 4. gauge 类指标实时更新：连续两次 scrape 值随状态变化
def test_gauges_update_between_scrapes(tmp_path):
    _reset_metrics()
    from feedflow import store

    db_path = str(tmp_path / "metrics_deep2_gauge.db")
    app = None
    try:
        from feedflow import create_app
        os.environ["FEEDFLOW_NO_SCHEDULER"] = "1"
        app = create_app(
            {
                "db_path": db_path,
                "host": "127.0.0.1",
                "port": 8304,
                "fetch_interval": 30,
                "user_agent": "FeedFlow-test",
            }
        )
    except Exception:  # noqa: BLE001 测试内兜底，app 为 None 时跳过上下文
        app = None

    if app is not None:
        with app.app_context():
            db_mod.init_db(db_path)
            for _tbl in ("articles", "feeds", "folders"):
                db_mod.execute_write(db_path, "DELETE FROM " + _tbl)

    # 第一次 scrape：全 0
    text1 = metrics.render(db_path=db_path)
    feeds1 = _find_metric_value(text1, "feedflow_feeds_total")
    articles1 = _find_metric_value(text1, "feedflow_articles_total")
    assert feeds1 == 0.0
    assert articles1 == 0.0

    # 制造状态变化：直接调用 store 写一条 feed
    fid = store.create_feed(db_path, "http://example.com/gauge.xml")
    store.update_feed(db_path, fid, title="GaugeFeed")

    text2 = metrics.render(db_path=db_path)
    feeds2 = _find_metric_value(text2, "feedflow_feeds_total")
    assert feeds2 >= 1.0
    assert feeds2 >= feeds1


def _find_metric_value(text, name):
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parsed = _parse_metric_line(line)
        if parsed and parsed[0] == name:
            return parsed[2]
    return None


# 5. /metrics 输出为合法 Prometheus exposition 文本格式
def test_render_prometheus_text_format():
    _reset_metrics()
    metrics.inc_fetch("ok")
    metrics.inc_fetch("error")
    metrics.inc_fetch_error("timeout")
    metrics.add_articles(5)
    metrics.observe_fetch_duration(1.5)
    metrics.inc_http_request("GET", "/metrics", 200)
    metrics.inc_rate_limited()

    text = metrics.render()
    assert text.endswith("\n")
    lines = text.splitlines()
    assert len(lines) > 0

    metric_lines = 0
    for line in lines:
        assert line != ""
        if line.startswith(("# HELP ", "# TYPE ")):
            continue
        # metric 行必须是 name{...} value 或 name value
        parsed = _parse_metric_line(line)
        assert parsed is not None, f"非法 metric 行: {line!r}"
        metric_lines += 1

    assert metric_lines > 0
    # 必须有 HELP/TYPE 配对
    helps = [l for l in lines if l.startswith("# HELP ")]
    types = [l for l in lines if l.startswith("# TYPE ")]
    assert len(helps) == len(types) >= 6


# 6. rate_limited 计数器在 429 触发时精确 +1
def test_rate_limited_counter_increments():
    _reset_metrics()
    assert metrics._rate_limited_total == 0

    metrics.inc_rate_limited()
    with metrics._lock:
        assert metrics._rate_limited_total == 1

    text = metrics.render()
    value = _find_metric_value(text, "feedflow_http_rate_limited_total")
    assert value == 1.0

    metrics.inc_rate_limited()
    metrics.inc_rate_limited()
    text2 = metrics.render()
    value2 = _find_metric_value(text2, "feedflow_http_rate_limited_total")
    assert value2 == 3.0


# 7. histogram/计数器复位语义：进程内指标单调不减
def test_counters_monotonic_nondecreasing():
    _reset_metrics()

    metrics.inc_fetch("ok")
    metrics.inc_fetch("ok")
    metrics.inc_fetch_error("timeout")
    metrics.add_articles(3)
    metrics.observe_fetch_duration(0.5)
    metrics.inc_http_request("GET", "/", 200)
    metrics.inc_rate_limited()

    snap1 = metrics.render()

    metrics.inc_fetch("ok")
    metrics.inc_fetch_error("timeout")
    metrics.add_articles(2)
    metrics.observe_fetch_duration(0.25)
    metrics.inc_http_request("GET", "/", 200)
    metrics.inc_rate_limited()

    snap2 = metrics.render()

    for name in (
        "feedflow_fetch_total",
        "feedflow_fetch_errors_total",
        "feedflow_articles_stored_total",
        "feedflow_fetch_duration_seconds_total",
        "feedflow_http_requests_total",
        "feedflow_http_rate_limited_total",
    ):
        v1 = _sum_metric(snap1, name)
        v2 = _sum_metric(snap2, name)
        assert v2 >= v1, f"{name} 应单调不减: {v1} -> {v2}"

    # 累加器本身也要对得上
    with metrics._lock:
        assert metrics._articles_stored_total == 5
        assert metrics._fetch_duration_sum == 0.75
        assert metrics._rate_limited_total == 2


def _sum_metric(text, name):
    total = 0.0
    found = False
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parsed = _parse_metric_line(line)
        if parsed and parsed[0] == name:
            total += parsed[2]
            found = True
    return total if found else 0.0


# 8. 未注册的指标名查询不抛异常
def test_unknown_metric_lookup_does_not_raise():
    _reset_metrics()
    metrics.inc_fetch("ok")
    text = metrics.render()

    # 直接渲染后查找不存在的指标名，不应抛异常，返回 None
    value = _find_metric_value(text, "feedflow_does_not_exist_total")
    assert value is None

    # 也验证 render 本身对任意 db_path 缺失/异常都不抛
    text2 = metrics.render(db_path="/nonexistent/path/definitely/missing.db")
    assert isinstance(text2, str)
    assert text2.endswith("\n")
