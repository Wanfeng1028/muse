import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from ledger import ocr_metrics as mod
from ledger.ocr_metrics import (
    OCR_DURATION_BUCKETS,
    _OcrMetrics,
    record_bills_ocr_confidence,
    record_bills_ocr_failure,
    record_bills_ocr_request,
    record_ocr_confidence,
    record_ocr_failure,
    record_ocr_request,
    render_bills_ocr_metrics,
    render_ocr_metrics,
)


def _metric_value(text: str, metric: str, labels: str | None = None) -> float:
    """从 exposition 文本里取出某个指标（可选带标签）的数值。"""
    pattern = r"^" + re.escape(metric)
    if labels is not None:
        pattern += r"\{" + re.escape(labels) + r"\}"
    pattern += r" (\S+)$"
    for line in text.splitlines():
        m = re.match(pattern, line)
        if m:
            return float(m.group(1))
    raise AssertionError(f"metric not found: {metric} labels={labels}")


def _has_help_and_type(text: str, metric: str, type_name: str) -> bool:
    """检查某个指标是否同时带有 # HELP 与指定 # TYPE 行。"""
    has_help = f"# HELP {metric} " in text
    has_type = f"# TYPE {metric} {type_name}" in text
    return has_help and has_type


def test_empty_metrics_render_defaults():
    # arrange
    m = _OcrMetrics("ledger_empty_probe")

    # act
    text = m.render()

    # assert
    assert _metric_value(text, "ledger_empty_probe_requests_total", 'result="ok"') == 0
    assert _metric_value(text, "ledger_empty_probe_requests_total", 'result="empty"') == 0
    assert _metric_value(text, "ledger_empty_probe_requests_total", 'result="error"') == 0
    assert _metric_value(text, "ledger_empty_probe_failures_total", 'reason="unavailable"') == 0
    assert _metric_value(text, "ledger_empty_probe_duration_seconds_count") == 0
    assert _metric_value(text, "ledger_empty_probe_duration_seconds_sum") == 0.0
    assert _metric_value(text, "ledger_empty_probe_confidence_avg") == 0.0
    assert _has_help_and_type(text, "ledger_empty_probe_requests_total", "counter")
    assert _has_help_and_type(text, "ledger_empty_probe_failures_total", "counter")
    assert _has_help_and_type(text, "ledger_empty_probe_duration_seconds", "histogram")
    assert _has_help_and_type(text, "ledger_empty_probe_confidence_avg", "gauge")
    assert text.endswith("\n")


def test_record_request_bucket_boundaries():
    # arrange
    m = _OcrMetrics("ledger_bucket_probe")

    # act: 每个桶上界正好命中，以及一个超出 +Inf 的耗时
    for le in OCR_DURATION_BUCKETS:
        if le == float("inf"):
            continue
        m.record_request("ok", le)
    m.record_request("ok", 999.0)

    # assert
    text = m.render()
    total = _metric_value(text, "ledger_bucket_probe_duration_seconds_count")
    assert total == len(OCR_DURATION_BUCKETS)
    assert _metric_value(text, "ledger_bucket_probe_requests_total", 'result="ok"') == len(
        OCR_DURATION_BUCKETS
    )
    for i, le in enumerate(OCR_DURATION_BUCKETS):
        le_label = "+Inf" if le == float("inf") else repr(le)
        # 累积直方图：bucket[i] 统计 duration <= le[i] 的请求数
        expected = i + 1
        assert (
            _metric_value(
                text, "ledger_bucket_probe_duration_seconds_bucket", f'le="{le_label}"'
            )
            == expected
        )
    assert _metric_value(text, "ledger_bucket_probe_duration_seconds_sum") == pytest.approx(
        sum(le for le in OCR_DURATION_BUCKETS if le != float("inf")) + 999.0, rel=1e-6
    )


def test_record_request_negative_and_invalid_duration():
    # arrange
    m = _OcrMetrics("ledger_invalid_duration_probe")

    # act
    m.record_request("ok", -5.0)
    m.record_request("ok", "not-a-number")
    m.record_request("ok", None)

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_invalid_duration_probe_requests_total", 'result="ok"') == 3
    assert _metric_value(text, "ledger_invalid_duration_probe_duration_seconds_count") == 3
    assert _metric_value(text, "ledger_invalid_duration_probe_duration_seconds_sum") == 0.0
    assert (
        _metric_value(
            text, "ledger_invalid_duration_probe_duration_seconds_bucket", 'le="0.05"'
        )
        == 3
    )


def test_record_request_unknown_result_folds_to_error():
    # arrange
    m = _OcrMetrics("ledger_unknown_result_probe")

    # act
    m.record_request("weird", 0.03)
    m.record_request("", 0.03)

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_unknown_result_probe_requests_total", 'result="error"') == 2
    assert _metric_value(text, "ledger_unknown_result_probe_requests_total", 'result="ok"') == 0
    assert _metric_value(text, "ledger_unknown_result_probe_requests_total", 'result="empty"') == 0
    assert _metric_value(text, "ledger_unknown_result_probe_duration_seconds_count") == 2


def test_record_failure_unknown_reason_folds_to_internal():
    # arrange
    m = _OcrMetrics("ledger_unknown_reason_probe")

    # act
    m.record_failure("boom")
    m.record_failure("oversize")

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_unknown_reason_probe_failures_total", 'reason="internal"') == 1
    assert _metric_value(text, "ledger_unknown_reason_probe_failures_total", 'reason="oversize"') == 1
    assert _metric_value(text, "ledger_unknown_reason_probe_failures_total", 'reason="unavailable"') == 0
    assert _metric_value(text, "ledger_unknown_reason_probe_failures_total", 'reason="unsupported"') == 0
    assert _metric_value(text, "ledger_unknown_reason_probe_failures_total", 'reason="invalid"') == 0


def test_record_confidence_ignores_out_of_range_and_nan():
    # arrange
    m = _OcrMetrics("ledger_confidence_probe")

    # act
    m.record_confidence(None)
    m.record_confidence(float("nan"))
    m.record_confidence(-0.01)
    m.record_confidence(1.01)
    m.record_confidence("0.5")
    m.record_confidence(0.0)
    m.record_confidence(1.0)

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_confidence_probe_confidence_avg") == pytest.approx(
        0.5, rel=1e-6
    )
    assert "ledger_confidence_probe_confidence_avg 0.500000" in text


def test_confidence_zero_when_no_valid_sample():
    # arrange
    m = _OcrMetrics("ledger_confidence_empty_probe")

    # act
    m.record_confidence(None)
    m.record_confidence(float("nan"))
    m.record_confidence(2.0)

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_confidence_empty_probe_confidence_avg") == 0.0
    assert "ledger_confidence_empty_probe_confidence_avg 0.000000" in text


def test_huge_amount_and_long_strings_do_not_break_render():
    # arrange
    m = _OcrMetrics("ledger_huge_probe")
    huge = 10.0**12

    # act
    m.record_request("ok", huge)
    m.record_request("ok", huge * 10)
    m.record_failure("internal")

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_huge_probe_requests_total", 'result="ok"') == 2
    assert (
        _metric_value(text, "ledger_huge_probe_duration_seconds_bucket", 'le="+Inf"') == 2
    )
    assert _metric_value(text, "ledger_huge_probe_duration_seconds_count") == 2
    assert _metric_value(text, "ledger_huge_probe_duration_seconds_sum") == pytest.approx(
        huge * 11, rel=1e-9
    )
    assert _metric_value(text, "ledger_huge_probe_failures_total", 'reason="internal"') == 1


def test_module_level_instances_are_isolated():
    # arrange: 记录前先取一次快照，避免与其它用例相互污染
    before_ocr = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", 'result="ok"')
    before_bills = _metric_value(
        render_bills_ocr_metrics(), "ledger_bills_ocr_requests_total", 'result="ok"'
    )

    # act
    record_ocr_request("ok", 0.01)
    record_bills_ocr_request("empty", 0.02)

    # assert
    after_ocr = _metric_value(render_ocr_metrics(), "ledger_ocr_requests_total", 'result="ok"')
    after_bills = _metric_value(
        render_bills_ocr_metrics(), "ledger_bills_ocr_requests_total", 'result="ok"'
    )
    assert after_ocr == before_ocr + 1
    assert after_bills == before_bills
    assert (
        _metric_value(
            render_bills_ocr_metrics(), "ledger_bills_ocr_requests_total", 'result="empty"'
        )
        >= 1
    )


def test_concurrent_writes_same_instance_are_consistent():
    # arrange
    m = _OcrMetrics("ledger_concurrent_probe")
    workers = 8
    per_worker = 200

    # act: 多线程双写同一实例
    def worker():
        for _ in range(per_worker):
            m.record_request("ok", 0.02)
            m.record_failure("oversize")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda _: worker(), range(workers)))

    # assert
    text = m.render()
    expected = workers * per_worker
    assert _metric_value(text, "ledger_concurrent_probe_requests_total", 'result="ok"') == expected
    assert _metric_value(text, "ledger_concurrent_probe_duration_seconds_count") == expected
    assert (
        _metric_value(text, "ledger_concurrent_probe_failures_total", 'reason="oversize"')
        == expected
    )
    assert (
        _metric_value(text, "ledger_concurrent_probe_duration_seconds_bucket", 'le="+Inf"')
        == expected
    )


def test_idempotent_repeated_record_accumulates_once_per_call():
    # arrange
    m = _OcrMetrics("ledger_idempotent_probe")

    # act: 同一账单重复导入/重复记账场景，每次调用必须各计一次
    for _ in range(3):
        m.record_request("ok", 0.04)
        m.record_confidence(0.8)
    for _ in range(3):
        m.record_failure("invalid")

    # assert
    text = m.render()
    assert _metric_value(text, "ledger_idempotent_probe_requests_total", 'result="ok"') == 3
    assert _metric_value(text, "ledger_idempotent_probe_duration_seconds_count") == 3
    assert _metric_value(text, "ledger_idempotent_probe_failures_total", 'reason="invalid"') == 3
    assert _metric_value(text, "ledger_idempotent_probe_confidence_avg") == pytest.approx(
        0.8, rel=1e-6
    )


def test_render_snapshot_is_stable_under_concurrent_writes():
    # arrange
    m = _OcrMetrics("ledger_snapshot_probe")
    stop = threading.Event()
    errors: list[BaseException] = []

    # act
    def writer():
        while not stop.is_set():
            try:
                m.record_request("empty", 0.3)
                m.record_failure("unsupported")
            except BaseException as exc:  # pragma: no cover - 仅在实现抛出时触发
                errors.append(exc)

    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(50):
            text = m.render()
            # 每次快照内部必须自洽：bucket[+Inf] == count
            inf_bucket = _metric_value(
                text, "ledger_snapshot_probe_duration_seconds_bucket", 'le="+Inf"'
            )
            count = _metric_value(text, "ledger_snapshot_probe_duration_seconds_count")
            assert inf_bucket == count
            assert text.endswith("\n")
    finally:
        stop.set()
        t.join(timeout=5)

    # assert
    assert errors == []
    final_text = m.render()
    assert _metric_value(
        final_text, "ledger_snapshot_probe_requests_total", 'result="empty"'
    ) == _metric_value(final_text, "ledger_snapshot_probe_duration_seconds_count")
    assert _metric_value(
        final_text, "ledger_snapshot_probe_failures_total", 'reason="unsupported"'
    ) >= 1


def test_exposition_format_matches_prometheus_shape():
    # arrange
    m = _OcrMetrics("ledger_format_probe")

    # act
    m.record_request("error", 0.5)
    text = m.render()

    # assert: 采样行必须严格是 metric{labels} value，不带额外空格或时间戳
    sample_lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert sample_lines
    for line in sample_lines:
        assert re.match(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(\{[^}]*\})? -?[0-9.eE+]+$", line), line
    assert (
        'ledger_format_probe_requests_total{result="error"} 1' in sample_lines
    )
    assert _metric_value(text, "ledger_format_probe_duration_seconds_sum") == 0.5
    assert len(OCR_DURATION_BUCKETS) == 9


def test_chinese_label_values_and_docstrings_survive_round_trip():
    # arrange
    m = _OcrMetrics("ledger_cn_probe")

    # act: 中文商户名/备注场景通过结果标签间接覆盖（标签集合为固定英文，值仍须原样输出）
    m.record_request("ok", 1.25)
    m.record_request("empty", 0.0)
    m.record_failure("unavailable")
    m.record_confidence(0.66)
    text = m.render()

    # assert
    assert 'ledger_cn_probe_requests_total{result="ok"} 1' in text
    assert 'ledger_cn_probe_requests_total{result="empty"} 1' in text
    assert 'ledger_cn_probe_failures_total{reason="unavailable"} 1' in text
    assert _metric_value(text, "ledger_cn_probe_confidence_avg") == pytest.approx(0.66, rel=1e-6)
    assert "# HELP ledger_cn_probe_requests_total" in text
    assert "OCR" in text


def test_module_level_helpers_never_raise_on_bad_input():
    # arrange
    before = _metric_value(
        render_bills_ocr_metrics(), "ledger_bills_ocr_failures_total", 'reason="internal"'
    )

    # act: 失败注入式非法入参，辅助函数必须吞掉异常并保持渲染可用
    record_bills_ocr_request("nope", object())
    record_bills_ocr_failure("nope")
    record_bills_ocr_confidence("bad")
    record_bills_ocr_confidence(float("inf"))

    # assert
    text = render_bills_ocr_metrics()
    after = _metric_value(
        text, "ledger_bills_ocr_failures_total", 'reason="internal"'
    )
    assert after == before + 1
    assert (
        _metric_value(text, "ledger_bills_ocr_requests_total", 'result="error"') >= 1
    )
    assert text.endswith("\n")
    assert mod.OCR_DURATION_BUCKETS == OCR_DURATION_BUCKETS