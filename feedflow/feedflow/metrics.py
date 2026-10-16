"""Prometheus 指标（手写 exposition，零依赖，线程安全）。"""

import threading

_lock = threading.Lock()

_fetch_total = {}          # status -> count
_fetch_errors_total = {}   # kind -> count
_articles_stored_total = 0
_fetch_duration_sum = 0.0
_http_requests_total = {}  # (method, route, status) -> count


def inc_fetch(status):
    with _lock:
        _fetch_total[status] = _fetch_total.get(status, 0) + 1


def inc_fetch_error(kind):
    with _lock:
        _fetch_errors_total[kind] = _fetch_errors_total.get(kind, 0) + 1


def add_articles(n):
    global _articles_stored_total
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return
    with _lock:
        _articles_stored_total += n


def observe_fetch_duration(seconds):
    global _fetch_duration_sum
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return
    if seconds < 0:
        return
    with _lock:
        _fetch_duration_sum += seconds


def inc_http_request(method, route, status):
    method = str(method)
    route = str(route) if route else "unknown"
    status = str(status)
    key = (method, route, status)
    with _lock:
        _http_requests_total[key] = _http_requests_total.get(key, 0) + 1


def _fmt(value):
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value)
    return str(value)


def _escape_label(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def render(db_path=None):
    lines = []

    with _lock:
        fetch_total = dict(_fetch_total)
        fetch_errors = dict(_fetch_errors_total)
        articles_stored = _articles_stored_total
        duration_sum = _fetch_duration_sum
        http_requests = dict(_http_requests_total)

    lines.append("# HELP feedflow_fetch_total Total feed fetch attempts by status.")
    lines.append("# TYPE feedflow_fetch_total counter")
    if fetch_total:
        for status in sorted(fetch_total):
            lines.append(
                f'feedflow_fetch_total{{status="{_escape_label(status)}"}} '
                f"{_fmt(fetch_total[status])}"
            )
    else:
        lines.append('feedflow_fetch_total{status="ok"} 0')
        lines.append('feedflow_fetch_total{status="error"} 0')

    lines.append("# HELP feedflow_fetch_errors_total Total feed fetch errors by kind.")
    lines.append("# TYPE feedflow_fetch_errors_total counter")
    if fetch_errors:
        for kind in sorted(fetch_errors):
            lines.append(
                f'feedflow_fetch_errors_total{{kind="{_escape_label(kind)}"}} '
                f"{_fmt(fetch_errors[kind])}"
            )

    lines.append("# HELP feedflow_articles_stored_total Total articles stored.")
    lines.append("# TYPE feedflow_articles_stored_total counter")
    lines.append(f"feedflow_articles_stored_total {_fmt(articles_stored)}")

    lines.append(
        "# HELP feedflow_fetch_duration_seconds_total Cumulative feed fetch duration in seconds."
    )
    lines.append("# TYPE feedflow_fetch_duration_seconds_total counter")
    lines.append(
        f"feedflow_fetch_duration_seconds_total {_fmt(duration_sum)}"
    )

    lines.append(
        "# HELP feedflow_http_requests_total Total HTTP requests by method, route, status."
    )
    lines.append("# TYPE feedflow_http_requests_total counter")
    if http_requests:
        for key in sorted(http_requests):
            method, route, status = key
            lines.append(
                f'feedflow_http_requests_total{{method="{_escape_label(method)}",'
                f'route="{_escape_label(route)}",status="{_escape_label(status)}"}} '
                f"{_fmt(http_requests[key])}"
            )

    stats = None
    if db_path is not None:
        try:
            from . import store as _store

            stats = _store.stats(db_path)
        except Exception:  # noqa: BLE001  # 指标抓取不许因 DB 异常炸掉 /metrics，故意宽捕获
            stats = None

    def _gauge(name, help_text, key):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        value = 0
        if isinstance(stats, dict):
            value = stats.get(key, 0) or 0
        lines.append(f"{name} {_fmt(value)}")

    _gauge("feedflow_feeds_total", "Total number of feeds.", "feeds")
    _gauge("feedflow_articles_total", "Total number of articles.", "articles")
    _gauge("feedflow_unread_total", "Total number of unread articles.", "unread")
    _gauge("feedflow_starred_total", "Total number of starred articles.", "starred")

    return "\n".join(lines) + "\n"
