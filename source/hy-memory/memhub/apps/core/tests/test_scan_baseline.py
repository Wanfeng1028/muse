"""A4-11: the baseline gate, and the ways baselines go wrong."""

from __future__ import annotations

from one_memory.memory_server.scan_baseline import (
    TOLERANCE,
    Baseline,
    Comparison,
    Observation,
    Status,
    compare,
    from_metrics,
    render,
    snapshot,
)
from one_memory.memory_server.scanner.service import ScanMetrics


def test_from_metrics_bridges_the_scanner_to_the_gate() -> None:
    """Without this the two halves never meet and baselines get typed in by hand
    — which is how they end up recording what someone hoped rather than what
    happened."""
    metrics = ScanMetrics(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=100,
    )
    observed = from_metrics(metrics, elapsed_seconds=0.5)
    assert observed.metadata_enumerated == 100
    assert observed.cursor_batch_lookups == 1
    assert observed.unchanged_files == 100
    assert observed.elapsed_seconds == 0.5


def test_from_metrics_feeds_a_real_comparison() -> None:
    """End-to-end: scanner metrics -> baseline -> later run judged."""
    baseline = snapshot(
        "sweep",
        from_metrics(
            ScanMetrics(
                metadata_enumerated=100,
                cursor_batch_lookups=1,
                files_opened=0,
                bytes_read=0,
                changed_files=0,
                unchanged_files=100,
            )
        ),
    )
    later = from_metrics(
        ScanMetrics(
            metadata_enumerated=100,
            cursor_batch_lookups=1,
            files_opened=0,
            bytes_read=0,
            changed_files=0,
            unchanged_files=100,
        )
    )
    assert compare(baseline=baseline, observed=later).status is Status.OK


def test_from_metrics_preserves_open_and_bytes() -> None:
    """The gate's hard invariant depends on these, so they must survive the
    bridge. (An earlier version of this test only used zero values, so a
    mutation hardcoding them to 0 went undetected.)"""
    metrics = ScanMetrics(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=3,
        bytes_read=900,
        changed_files=2,
        unchanged_files=98,
    )
    observed = from_metrics(metrics)
    assert observed.files_opened == 3
    assert observed.bytes_read == 900


def test_from_metrics_lets_a_broken_gate_be_caught() -> None:
    """End-to-end with a real violation: no changes, yet bytes were read."""
    baseline = snapshot(
        "sweep",
        from_metrics(
            ScanMetrics(
                metadata_enumerated=100,
                cursor_batch_lookups=1,
                files_opened=0,
                bytes_read=0,
                changed_files=0,
                unchanged_files=100,
            )
        ),
    )
    violated = from_metrics(
        ScanMetrics(
            metadata_enumerated=100,
            cursor_batch_lookups=1,
            files_opened=3,
            bytes_read=900,
            changed_files=0,
            unchanged_files=100,
        )
    )
    assert compare(baseline=baseline, observed=violated).status is Status.FAILED


def _clean_sweep() -> Observation:
    """A sweep where nothing changed: the case the metadata gate is judged on."""
    return Observation(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=100,
        elapsed_seconds=0.5,
    )


def test_an_identical_run_is_ok() -> None:
    observed = _clean_sweep()
    assert compare(baseline=snapshot("sweep", observed), observed=observed).status is Status.OK


def test_a_missing_baseline_is_not_a_pass() -> None:
    """Comparing against nothing would let every first run certify itself."""
    result = compare(baseline=None, observed=_clean_sweep())
    assert result.status is Status.NO_BASELINE
    assert result.status is not Status.OK
    assert result.reasons


def test_growth_beyond_tolerance_is_a_regression() -> None:
    baseline = snapshot("sweep", _clean_sweep())
    grown = Observation(
        metadata_enumerated=500,
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=100,
    )
    result = compare(baseline=baseline, observed=grown)
    assert result.status is Status.REGRESSED
    assert "metadata_enumerated" in result.reasons[0]


def test_small_growth_within_tolerance_stays_ok() -> None:
    """The gate catches step changes, not noise; a flaky gate gets ignored."""
    baseline = snapshot("sweep", _clean_sweep())
    slightly = Observation(
        metadata_enumerated=int(100 * (TOLERANCE - 0.1)),
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=100,
    )
    assert compare(baseline=baseline, observed=slightly).status is Status.OK


def test_anything_opened_on_a_no_change_sweep_is_a_failure() -> None:
    """The whole point of the gate is that unchanged files cost nothing."""
    baseline = snapshot("sweep", _clean_sweep())
    violated = Observation(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=3,
        bytes_read=900,
        changed_files=0,
        unchanged_files=100,
    )
    result = compare(baseline=baseline, observed=violated)
    assert result.status is Status.FAILED
    assert result.status is not Status.REGRESSED


def test_opening_is_allowed_when_something_actually_changed() -> None:
    baseline = snapshot("sweep", _clean_sweep())
    changed = Observation(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=2,
        bytes_read=400,
        changed_files=2,
        unchanged_files=98,
    )
    assert compare(baseline=baseline, observed=changed).status is Status.OK


def test_elapsed_time_is_recorded_but_not_gated() -> None:
    """Timing on a dev machine is noise; gating it would make the gate flaky."""
    baseline = snapshot("sweep", _clean_sweep())
    slower = Observation(
        metadata_enumerated=100,
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=100,
        elapsed_seconds=30.0,
    )
    assert compare(baseline=baseline, observed=slower).status is Status.OK
    assert "elapsed_seconds" in render(baseline)
    assert "not gated" in render(baseline)


def test_a_zero_baseline_gives_no_ratio_instead_of_dividing_by_zero() -> None:
    baseline = Baseline(
        name="empty",
        metadata_enumerated=0,
        cursor_batch_lookups=0,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=0,
    )
    result = compare(baseline=baseline, observed=_clean_sweep())
    assert isinstance(result, Comparison)
    assert result.ratios["metadata_enumerated"] == 0.0


def test_snapshot_preserves_the_numbers() -> None:
    observed = _clean_sweep()
    baseline = snapshot("sweep", observed)
    assert baseline.metadata_enumerated == 100
    assert baseline.cursor_batch_lookups == 1
    assert baseline.unchanged_files == 100
    assert baseline.elapsed_seconds == 0.5


def test_render_is_stable_and_diffable() -> None:
    """A baseline you can diff in review."""
    baseline = snapshot("sweep", _clean_sweep())
    assert render(baseline) == render(snapshot("sweep", _clean_sweep()))


def test_render_differs_when_a_number_changes() -> None:
    first = render(snapshot("sweep", _clean_sweep()))
    changed = Observation(
        metadata_enumerated=101,
        cursor_batch_lookups=1,
        files_opened=0,
        bytes_read=0,
        changed_files=0,
        unchanged_files=101,
    )
    assert render(snapshot("sweep", changed)) != first
