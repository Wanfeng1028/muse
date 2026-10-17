"""进程内 OCR 请求计数与耗时直方图，手写 Prometheus exposition。"""

from __future__ import annotations

import threading

from ledger.logging import get_logger

_logger = get_logger("ocr_metrics")

# asyncio 单进程内足够，进程重启计数清零是预期行为。
_lock = threading.Lock()

OCR_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf"))

_VALID_RESULTS = ("ok", "unavailable", "error")

_requests: dict[str, int] = {"ok": 0, "unavailable": 0, "error": 0}
_duration_count: int = 0
_duration_sum: float = 0.0
_bucket_counts: list[int] = [0] * len(OCR_DURATION_BUCKETS)


def record_ocr_request(result: str, duration_seconds: float) -> None:
    """记录一次 OCR 请求的结果与耗时，自身异常永不外抛。"""
    try:
        if result not in _VALID_RESULTS:
            result = "error"
        try:
            duration = float(duration_seconds)
        except (TypeError, ValueError):
            duration = 0.0
        if duration < 0:
            duration = 0.0
        with _lock:
            _requests[result] += 1
            global _duration_count, _duration_sum
            _duration_count += 1
            _duration_sum += duration
            for i, le in enumerate(OCR_DURATION_BUCKETS):
                if duration <= le:
                    _bucket_counts[i] += 1
    except Exception as exc:
        _logger.warning(
            "ocr_metrics_record_failed",
            extra={"extra_data": {"error": repr(exc)}},
        )


def _format_le(le: float) -> str:
    if le == float("inf"):
        return "+Inf"
    return repr(le)


def render_ocr_metrics() -> str:
    """渲染 OCR 指标的 Prometheus 文本 exposition。"""
    with _lock:
        requests_snapshot = dict(_requests)
        duration_count = _duration_count
        duration_sum = _duration_sum
        bucket_counts = list(_bucket_counts)

    lines: list[str] = []

    lines.append("# HELP ocr_requests_total OCR 请求总数（按结果分组）")
    lines.append("# TYPE ocr_requests_total counter")
    for result in _VALID_RESULTS:
        lines.append(f'ocr_requests_total{{result="{result}"}} {int(requests_snapshot.get(result, 0))}')

    lines.append("# HELP ocr_duration_seconds OCR 请求耗时（秒）")
    lines.append("# TYPE ocr_duration_seconds histogram")
    for i, le in enumerate(OCR_DURATION_BUCKETS):
        lines.append(f'ocr_duration_seconds_bucket{{le="{_format_le(le)}"}} {int(bucket_counts[i])}')
    lines.append(f"ocr_duration_seconds_count {int(duration_count)}")
    lines.append(f"ocr_duration_seconds_sum {duration_sum:.6f}")

    return "\n".join(lines) + "\n"
