"""进程内 OCR 全路径可观测指标，手写 Prometheus exposition。"""

from __future__ import annotations

import threading

from ledger.logging import get_logger

_logger = get_logger("ocr_metrics")

# asyncio 单进程内足够，进程重启计数清零是预期行为。
_lock = threading.Lock()

OCR_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf"))

_VALID_RESULTS = ("ok", "empty", "error")

_VALID_REASONS = ("unavailable", "unsupported", "invalid", "oversize", "internal")

_requests: dict[str, int] = {"ok": 0, "empty": 0, "error": 0}
_failures: dict[str, int] = {
    "unavailable": 0,
    "unsupported": 0,
    "invalid": 0,
    "oversize": 0,
    "internal": 0,
}
_duration_count: int = 0
_duration_sum: float = 0.0
_bucket_counts: list[int] = [0] * len(OCR_DURATION_BUCKETS)
_confidence_sum: float = 0.0
_confidence_count: int = 0


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


def record_ocr_failure(reason: str) -> None:
    """记录一次 OCR 失败请求的原因分类，自身异常永不外抛。"""
    try:
        if reason not in _VALID_REASONS:
            reason = "internal"
        with _lock:
            _failures[reason] += 1
    except Exception as exc:
        _logger.warning(
            "ocr_metrics_record_failed",
            extra={"extra_data": {"error": repr(exc)}},
        )


def record_ocr_confidence(avg: float | None) -> None:
    """记录一次 tesseract 词置信度均值样本（0~1），非法值忽略，自身异常永不外抛。"""
    try:
        if avg is None:
            return
        try:
            value = float(avg)
        except (TypeError, ValueError):
            return
        if value != value:  # NaN
            return
        if value < 0 or value > 1:
            return
        with _lock:
            global _confidence_sum, _confidence_count
            _confidence_sum += value
            _confidence_count += 1
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
        failures_snapshot = dict(_failures)
        duration_count = _duration_count
        duration_sum = _duration_sum
        bucket_counts = list(_bucket_counts)
        confidence_sum = _confidence_sum
        confidence_count = _confidence_count

    lines: list[str] = []

    lines.append("# HELP ledger_ocr_requests_total OCR 全路径请求总数（按结果分组）")
    lines.append("# TYPE ledger_ocr_requests_total counter")
    for result in _VALID_RESULTS:
        lines.append(f'ledger_ocr_requests_total{{result="{result}"}} {int(requests_snapshot.get(result, 0))}')

    lines.append("# HELP ledger_ocr_failures_total OCR 失败请求总数（按原因分组）")
    lines.append("# TYPE ledger_ocr_failures_total counter")
    for reason in _VALID_REASONS:
        lines.append(f'ledger_ocr_failures_total{{reason="{reason}"}} {int(failures_snapshot.get(reason, 0))}')

    lines.append("# HELP ledger_ocr_duration_seconds OCR 请求耗时（秒）")
    lines.append("# TYPE ledger_ocr_duration_seconds histogram")
    for i, le in enumerate(OCR_DURATION_BUCKETS):
        lines.append(f'ledger_ocr_duration_seconds_bucket{{le="{_format_le(le)}"}} {int(bucket_counts[i])}')
    lines.append(f"ledger_ocr_duration_seconds_count {int(duration_count)}")
    lines.append(f"ledger_ocr_duration_seconds_sum {duration_sum:.6f}")

    confidence_avg = confidence_sum / confidence_count if confidence_count > 0 else 0.0
    lines.append("# HELP ledger_ocr_confidence_avg tesseract 词置信度均值（0~1，无样本时为 0）")
    lines.append("# TYPE ledger_ocr_confidence_avg gauge")
    lines.append(f"ledger_ocr_confidence_avg {confidence_avg:.6f}")

    return "\n".join(lines) + "\n"
