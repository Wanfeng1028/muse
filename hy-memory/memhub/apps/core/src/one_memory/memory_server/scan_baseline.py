"""A4-11: turn one scan's numbers into a baseline you can regression against.

`scanner.service` already counts the five things D54 demands. What was missing
is the part that makes them useful over time: a **recorded baseline** and a
rule for deciding whether a later run is a regression.

Three decisions, each guarding a specific way baselines go wrong:

- **Only the bounded costs are gated.** Enumerated metadata and batch lookups
  must stay proportional; wall-clock time is *recorded but not gated*, because
  timing on a developer machine is noise and would make the gate flaky. A gate
  that flakes gets ignored, which is worse than no gate.
- **The zero-open guarantee is a hard invariant, not a budget.** If anything
  was opened on a no-change sweep, the metadata gate has failed — that is a
  correctness bug. It is reported as `FAILED`, never as "slightly worse".
- **A missing baseline is not a pass.** Comparing against nothing would let
  every first run certify itself. Absence is reported, not treated as
  agreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from one_memory.memory_server.scanner.service import ScanMetrics


class Status(StrEnum):
    OK = "ok"
    REGRESSED = "regressed"
    FAILED = "failed"
    #: No baseline to compare against; the run says nothing about regressions.
    NO_BASELINE = "no_baseline"


@dataclass(frozen=True)
class Baseline:
    """A recorded measurement to compare later runs against."""

    name: str
    metadata_enumerated: int
    cursor_batch_lookups: int
    files_opened: int
    bytes_read: int
    changed_files: int
    unchanged_files: int
    #: Seconds, recorded for humans, deliberately not gated.
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class Observation:
    """One measured run."""

    metadata_enumerated: int
    cursor_batch_lookups: int
    files_opened: int
    bytes_read: int
    changed_files: int
    unchanged_files: int
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class Comparison:
    status: Status
    #: Human-readable reasons; empty when there is nothing wrong.
    reasons: tuple[str, ...] = ()
    #: Per-metric ratios (observed / baseline); 0.0 when the baseline is 0.
    ratios: dict[str, float] = field(default_factory=dict)


#: How much worse a bounded cost may get before it counts as a regression.
#: Generous on purpose: the gate exists to catch step changes, not noise.
TOLERANCE = 1.5


def _ratio(observed: int, baseline: int) -> float:
    """observed/baseline, with 0 meaning the baseline had nothing to compare."""
    if baseline <= 0:
        return 0.0
    return observed / baseline


def compare(*, baseline: Baseline | None, observed: Observation) -> Comparison:
    """Judge one run against a baseline.

    A no-change sweep that opened or read anything is a correctness failure —
    the whole point of the metadata gate is that unchanged files cost nothing.
    """
    if baseline is None:
        return Comparison(Status.NO_BASELINE, ("no baseline recorded; cannot judge regression",))

    reasons: list[str] = []
    ratios = {
        "metadata_enumerated": _ratio(observed.metadata_enumerated, baseline.metadata_enumerated),
        "cursor_batch_lookups": _ratio(
            observed.cursor_batch_lookups, baseline.cursor_batch_lookups
        ),
        "files_opened": _ratio(observed.files_opened, baseline.files_opened),
        "bytes_read": _ratio(observed.bytes_read, baseline.bytes_read),
    }

    # Hard invariant: nothing to do means nothing opened.
    if observed.changed_files == 0 and (observed.files_opened > 0 or observed.bytes_read > 0):
        return Comparison(
            Status.FAILED,
            ("a sweep with no changes opened files or read bytes; the metadata gate has failed",),
            ratios,
        )

    for name in ("metadata_enumerated", "cursor_batch_lookups"):
        ratio = ratios[name]
        if ratio > TOLERANCE:
            reasons.append(f"{name} grew {ratio:.2f}x beyond the {TOLERANCE:.2f}x tolerance")

    return Comparison(
        Status.REGRESSED if reasons else Status.OK,
        tuple(reasons),
        ratios,
    )


def snapshot(name: str, observed: Observation) -> Baseline:
    """Record a run as the baseline for later comparisons."""
    return Baseline(
        name=name,
        metadata_enumerated=observed.metadata_enumerated,
        cursor_batch_lookups=observed.cursor_batch_lookups,
        files_opened=observed.files_opened,
        bytes_read=observed.bytes_read,
        changed_files=observed.changed_files,
        unchanged_files=observed.unchanged_files,
        elapsed_seconds=observed.elapsed_seconds,
    )


def from_metrics(
    metrics: ScanMetrics,
    *,
    elapsed_seconds: float = 0.0,
) -> Observation:
    """Turn a `ScanMetrics` into an `Observation`.

    This is what makes the baseline usable in practice: `scan_once` produces
    `ScanMetrics`, and the gate consumes `Observation`. Without this the two
    halves never meet, and a baseline has to be typed in by hand — which is how
    baselines end up recording what someone hoped rather than what happened.
    """
    return Observation(
        metadata_enumerated=metrics.metadata_enumerated,
        cursor_batch_lookups=metrics.cursor_batch_lookups,
        files_opened=metrics.files_opened,
        bytes_read=metrics.bytes_read,
        changed_files=metrics.changed_files,
        unchanged_files=metrics.unchanged_files,
        elapsed_seconds=elapsed_seconds,
    )


def render(baseline: Baseline) -> str:
    """One line per metric, so a baseline can be diffed in review."""
    return "\n".join(
        [
            f"baseline: {baseline.name}",
            f"  metadata_enumerated: {baseline.metadata_enumerated}",
            f"  cursor_batch_lookups: {baseline.cursor_batch_lookups}",
            f"  files_opened: {baseline.files_opened}",
            f"  bytes_read: {baseline.bytes_read}",
            f"  changed_files: {baseline.changed_files}",
            f"  unchanged_files: {baseline.unchanged_files}",
            f"  elapsed_seconds: {baseline.elapsed_seconds:.3f} (recorded, not gated)",
        ]
    )
