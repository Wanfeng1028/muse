"""进程内 OCR 全路径可观测指标，手写 Prometheus exposition。"""

from __future__ import annotations

import threading

from ledger.logging import get_logger

_logger = get_logger("ocr_metrics")

OCR_DURATION_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, float("inf"))

_VALID_RESULTS = ("ok", "empty", "error")

_VALID_REASONS = ("unavailable", "unsupported", "invalid", "oversize", "internal")


def _format_le(le: float) -> str:
    if le == float("inf"):
        return "+Inf"
    return repr(le)


class _OcrMetrics:
    """单个指标名前缀下的一组 OCR 全路径计数器（实例间状态完全隔离）。"""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        # asyncio 单进程内足够，进程重启计数清零是预期行为。
        self._lock = threading.Lock()
        self._requests: dict[str, int] = {"ok": 0, "empty": 0, "error": 0}
        self._failures: dict[str, int] = {
            "unavailable": 0,
            "unsupported": 0,
            "invalid": 0,
            "oversize": 0,
            "internal": 0,
        }
        self._duration_count: int = 0
        self._duration_sum: float = 0.0
        self._bucket_counts: list[int] = [0] * len(OCR_DURATION_BUCKETS)
        self._confidence_sum: float = 0.0
        self._confidence_count: int = 0

    def record_request(self, result: str, duration_seconds: float) -> None:
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
            with self._lock:
                self._requests[result] += 1
                self._duration_count += 1
                self._duration_sum += duration
                for i, le in enumerate(OCR_DURATION_BUCKETS):
                    if duration <= le:
                        self._bucket_counts[i] += 1
        except Exception as exc:
            _logger.warning(
                "ocr_metrics_record_failed",
                extra={"extra_data": {"error": repr(exc)}},
            )

    def record_failure(self, reason: str) -> None:
        """记录一次 OCR 失败请求的原因分类，自身异常永不外抛。"""
        try:
            if reason not in _VALID_REASONS:
                reason = "internal"
            with self._lock:
                self._failures[reason] += 1
        except Exception as exc:
            _logger.warning(
                "ocr_metrics_record_failed",
                extra={"extra_data": {"error": repr(exc)}},
            )

    def record_confidence(self, avg: float | None) -> None:
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
            with self._lock:
                self._confidence_sum += value
                self._confidence_count += 1
        except Exception as exc:
            _logger.warning(
                "ocr_metrics_record_failed",
                extra={"extra_data": {"error": repr(exc)}},
            )

    def render(self) -> str:
        """渲染本实例指标的 Prometheus 文本 exposition。"""
        prefix = self._prefix
        with self._lock:
            requests_snapshot = dict(self._requests)
            failures_snapshot = dict(self._failures)
            duration_count = self._duration_count
            duration_sum = self._duration_sum
            bucket_counts = list(self._bucket_counts)
            confidence_sum = self._confidence_sum
            confidence_count = self._confidence_count

        lines: list[str] = []

        lines.append(f"# HELP {prefix}_requests_total OCR 全路径请求总数（按结果分组）")
        lines.append(f"# TYPE {prefix}_requests_total counter")
        for result in _VALID_RESULTS:
            lines.append(f'{prefix}_requests_total{{result="{result}"}} {int(requests_snapshot.get(result, 0))}')

        lines.append(f"# HELP {prefix}_failures_total OCR 失败请求总数（按原因分组）")
        lines.append(f"# TYPE {prefix}_failures_total counter")
        for reason in _VALID_REASONS:
            lines.append(f'{prefix}_failures_total{{reason="{reason}"}} {int(failures_snapshot.get(reason, 0))}')

        lines.append(f"# HELP {prefix}_duration_seconds OCR 请求耗时（秒）")
        lines.append(f"# TYPE {prefix}_duration_seconds histogram")
        for i, le in enumerate(OCR_DURATION_BUCKETS):
            lines.append(f'{prefix}_duration_seconds_bucket{{le="{_format_le(le)}"}} {int(bucket_counts[i])}')
        lines.append(f"{prefix}_duration_seconds_count {int(duration_count)}")
        lines.append(f"{prefix}_duration_seconds_sum {duration_sum:.6f}")

        confidence_avg = confidence_sum / confidence_count if confidence_count > 0 else 0.0
        lines.append(f"# HELP {prefix}_confidence_avg tesseract 词置信度均值（0~1，无样本时为 0）")
        lines.append(f"# TYPE {prefix}_confidence_avg gauge")
        lines.append(f"{prefix}_confidence_avg {confidence_avg:.6f}")

        return "\n".join(lines) + "\n"


_ocr_metrics = _OcrMetrics("ledger_ocr")
_bills_ocr_metrics = _OcrMetrics("ledger_bills_ocr")


def record_ocr_request(result: str, duration_seconds: float) -> None:
    """记录一次 OCR 请求的结果与耗时，自身异常永不外抛。"""
    _ocr_metrics.record_request(result, duration_seconds)


def record_ocr_failure(reason: str) -> None:
    """记录一次 OCR 失败请求的原因分类，自身异常永不外抛。"""
    _ocr_metrics.record_failure(reason)


def record_ocr_confidence(avg: float | None) -> None:
    """记录一次 tesseract 词置信度均值样本（0~1），非法值忽略，自身异常永不外抛。"""
    _ocr_metrics.record_confidence(avg)


def render_ocr_metrics() -> str:
    """渲染 OCR 指标的 Prometheus 文本 exposition。"""
    return _ocr_metrics.render()


def record_bills_ocr_request(result: str, duration_seconds: float) -> None:
    """记录一次 bills OCR 请求的结果与耗时，自身异常永不外抛。"""
    _bills_ocr_metrics.record_request(result, duration_seconds)


def record_bills_ocr_failure(reason: str) -> None:
    """记录一次 bills OCR 失败请求的原因分类，自身异常永不外抛。"""
    _bills_ocr_metrics.record_failure(reason)


def record_bills_ocr_confidence(avg: float | None) -> None:
    """记录一次 bills OCR 词置信度均值样本（0~1），非法值忽略，自身异常永不外抛。"""
    _bills_ocr_metrics.record_confidence(avg)


def render_bills_ocr_metrics() -> str:
    """渲染 bills OCR 指标的 Prometheus 文本 exposition。"""
    return _bills_ocr_metrics.render()
