"""Machine-readable Core test timing and classification reports.

The plugin records identities, durations and marker names only. It deliberately
does not serialize captured output, exception text, fixture values, environment
variables or absolute test paths.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

PRIMARY_MARKERS = ("unit", "contract", "integration", "performance", "live")
CAPABILITY_MARKERS = (
    "serial",
    "slow",
    "real_volume",
    "macos",
    "linux",
    "mysql",
    "requires_embedding_assets",
    "resets_main_database_stats",
    "refuses_nested_checkout",
)
SCHEMA_VERSION = 1
PERFORMANCE_FILE_TOKENS = ("benchmark", "scale", "soak", "pressure", "contention")


@dataclass
class TestTiming:
    __test__ = False

    nodeid: str
    file: str
    primary_marker: str
    markers: tuple[str, ...]
    worker: str
    phases: dict[str, float] = field(default_factory=dict)
    phase_outcomes: dict[str, str] = field(default_factory=dict)
    outcome: str = "not_run"

    @property
    def total_seconds(self) -> float:
        return sum(self.phases.values())


def _safe_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999999) - 1))
    return ordered[index]


def _final_outcome(timing: TestTiming) -> str:
    outcomes = timing.phase_outcomes
    if any(value == "error" for value in outcomes.values()):
        return "error"
    if any(value == "failed" for value in outcomes.values()):
        return "failed"
    call = outcomes.get("call")
    if call is not None:
        return call
    if any(value == "skipped" for value in outcomes.values()):
        return "skipped"
    if any(value == "passed" for value in outcomes.values()):
        return "passed"
    return "not_run"


class CoreTestReporter:
    def __init__(self, config: pytest.Config, report_dir: Path, suite: str) -> None:
        self.config = config
        self.report_dir = report_dir
        self.suite = suite
        self.started = time.perf_counter()
        self.collection_started = 0.0
        self.collection_seconds = 0.0
        self.collection_errors = 0
        self.collected = 0
        self.timings: dict[str, TestTiming] = {}
        self.unclassified: list[str] = []
        self.multiple: dict[str, tuple[str, ...]] = {}
        self.missing_serial: list[str] = []

    def begin_collection(self) -> None:
        self.collection_started = time.perf_counter()

    def finish_collection(self, items: list[pytest.Item]) -> None:
        self.collection_seconds = max(0.0, time.perf_counter() - self.collection_started)
        self.collected = len(items)
        worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
        for item in items:
            markers = tuple(sorted({marker.name for marker in item.iter_markers()}))
            primary = tuple(name for name in PRIMARY_MARKERS if name in markers)
            if not primary:
                self.unclassified.append(item.nodeid)
                primary_name = "unclassified"
            elif len(primary) > 1:
                self.multiple[item.nodeid] = primary
                primary_name = "multiple"
            else:
                primary_name = primary[0]
            if primary_name in {"performance", "live"} and "serial" not in markers:
                self.missing_serial.append(item.nodeid)
            self.timings[item.nodeid] = TestTiming(
                nodeid=item.nodeid,
                file=item.nodeid.split("::", 1)[0],
                primary_marker=primary_name,
                markers=markers,
                worker=worker,
            )

    def record(self, report: pytest.TestReport) -> None:
        timing = self.timings.get(report.nodeid)
        if timing is None:
            timing = TestTiming(
                nodeid=report.nodeid,
                file=report.nodeid.split("::", 1)[0],
                primary_marker="unclassified",
                markers=(),
                worker=os.environ.get("PYTEST_XDIST_WORKER", "main"),
            )
            self.timings[report.nodeid] = timing
        timing.phases[report.when] = float(report.duration)
        if getattr(report, "wasxfail", None):
            outcome = "xfailed" if report.skipped else "xpassed"
        elif report.failed and report.when != "call":
            outcome = "error"
        else:
            outcome = report.outcome
        timing.phase_outcomes[report.when] = outcome
        timing.outcome = _final_outcome(timing)

    def write(self, exitstatus: int) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        wall_seconds = max(0.0, time.perf_counter() - self.started)
        values = sorted(self.timings.values(), key=lambda value: value.total_seconds, reverse=True)
        counts = Counter(value.outcome for value in values)
        worker_seconds = sum(value.total_seconds for value in values)
        mode = "xdist" if any(value.worker != "main" for value in values) else "serial"
        workers = len({value.worker for value in values}) or 1
        run = {
            "schema_version": SCHEMA_VERSION,
            "commit": _safe_commit(),
            "suite": self.suite,
            "mode": mode,
            "workers": workers,
            "python": platform.python_version(),
            "pytest": pytest.__version__,
            "sqlite": sqlite3.sqlite_version,
            "platform": sys.platform,
            "cpu_count": os.cpu_count(),
            "collection_seconds": self.collection_seconds,
            "execution_seconds": max(0.0, wall_seconds - self.collection_seconds),
            "wall_seconds": wall_seconds,
            "worker_seconds": worker_seconds,
            "collected": self.collected,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errors": counts["error"] + self.collection_errors,
            "skipped": counts["skipped"],
            "xfailed": counts["xfailed"],
            "xpassed": counts["xpassed"],
            "not_run": counts["not_run"],
            "exit_status": exitstatus,
            "classification": {
                "unclassified": len(self.unclassified),
                "multiple": len(self.multiple),
                "performance_or_live_without_serial": len(self.missing_serial),
            },
        }
        (self.report_dir / "run.json").write_text(
            json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with (self.report_dir / "tests.jsonl").open("w", encoding="utf-8") as stream:
            for value in sorted(values, key=lambda item: item.nodeid):
                stream.write(
                    json.dumps(
                        {
                            "schema_version": SCHEMA_VERSION,
                            "nodeid": value.nodeid,
                            "file": value.file,
                            "primary_marker": value.primary_marker,
                            "markers": value.markers,
                            "worker": value.worker,
                            "setup_seconds": value.phases.get("setup", 0.0),
                            "call_seconds": value.phases.get("call", 0.0),
                            "teardown_seconds": value.phases.get("teardown", 0.0),
                            "total_seconds": value.total_seconds,
                            "outcome": value.outcome,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        (self.report_dir / "collected-nodeids.txt").write_text(
            "".join(f"{value.nodeid}\n" for value in sorted(values, key=lambda item: item.nodeid)),
            encoding="utf-8",
        )
        self._write_group_csv(self.report_dir / "by-file.csv", values, lambda item: item.file)
        self._write_group_csv(
            self.report_dir / "by-marker.csv", values, lambda item: item.primary_marker
        )
        self._write_slowest(self.report_dir / "slowest-tests.md", values, run)
        (self.report_dir / "classification.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "primary_markers": PRIMARY_MARKERS,
                    "capability_markers": CAPABILITY_MARKERS,
                    "unclassified": sorted(self.unclassified),
                    "multiple": {key: value for key, value in sorted(self.multiple.items())},
                    "performance_or_live_without_serial": sorted(self.missing_serial),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.report_dir / "classification-suggestions.json").write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "warning": "Suggestions are review candidates and never alter collection.",
                    "files": self._classification_suggestions(values),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_group_csv(
        target: Path,
        values: list[TestTiming],
        key: Any,
    ) -> None:
        grouped: dict[str, list[TestTiming]] = defaultdict(list)
        for value in values:
            grouped[str(key(value))].append(value)
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["group", "cases", "worker_seconds", "mean_seconds", "p95_seconds", "max_seconds"]
            )
            for name in sorted(grouped):
                durations = [item.total_seconds for item in grouped[name]]
                writer.writerow(
                    [
                        name,
                        len(durations),
                        f"{sum(durations):.6f}",
                        f"{sum(durations) / len(durations):.6f}",
                        f"{_percentile(durations, 0.95):.6f}",
                        f"{max(durations, default=0.0):.6f}",
                    ]
                )

    @staticmethod
    def _classification_suggestions(values: list[TestTiming]) -> list[dict[str, Any]]:
        grouped: dict[str, list[TestTiming]] = defaultdict(list)
        for value in values:
            grouped[value.file].append(value)
        suggestions = []
        for file, items in sorted(grouped.items()):
            if any(item.primary_marker not in {"unclassified", "multiple"} for item in items):
                continue
            lower = file.lower()
            marker_names = {marker for item in items for marker in item.markers}
            suggestion = None
            reason = None
            confidence = "medium"
            if "slow" in marker_names or "real_volume" in marker_names:
                suggestion = "performance"
                reason = "existing slow/real_volume marker"
                confidence = "high"
            elif any(token in lower for token in PERFORMANCE_FILE_TOKENS):
                suggestion = "performance"
                reason = "performance-oriented filename token"
            elif lower.endswith("_live.py"):
                suggestion = "live"
                reason = "live test filename"
                confidence = "high"
            if suggestion is not None:
                suggestions.append(
                    {
                        "file": file,
                        "cases": len(items),
                        "suggested_primary_marker": suggestion,
                        "confidence": confidence,
                        "reason": reason,
                    }
                )
        return suggestions

    @staticmethod
    def _write_slowest(target: Path, values: list[TestTiming], run: dict[str, Any]) -> None:
        sections = [
            (
                "Slowest total",
                sorted(values, key=lambda item: item.total_seconds, reverse=True)[:30],
                "total_seconds",
            ),
            (
                "Slowest setup",
                sorted(
                    values,
                    key=lambda item: item.phases.get("setup", 0.0),
                    reverse=True,
                )[:20],
                "setup",
            ),
            (
                "Slowest teardown",
                sorted(
                    values,
                    key=lambda item: item.phases.get("teardown", 0.0),
                    reverse=True,
                )[:20],
                "teardown",
            ),
        ]
        lines = [
            "# Core test timing",
            "",
            f"- Suite: `{run['suite']}`",
            f"- Collected: {run['collected']}",
            f"- Collection: {run['collection_seconds']:.3f}s",
            f"- Wall: {run['wall_seconds']:.3f}s",
            f"- Worker time: {run['worker_seconds']:.3f}s",
        ]
        for title, items, phase in sections:
            lines.extend(("", f"## {title}", "", "| Seconds | Test |", "| ---: | --- |"))
            for item in items:
                seconds = (
                    item.total_seconds if phase == "total_seconds" else item.phases.get(phase, 0.0)
                )
                lines.append(f"| {seconds:.3f} | `{item.nodeid}` |")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")


REPORTER_KEY: pytest.StashKey[CoreTestReporter] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("core test reporting")
    group.addoption("--core-report-dir", help="write sanitized Core timing reports here")
    group.addoption("--core-suite", default="core", help="stable Core test suite name")
    group.addoption(
        "--core-classification-enforce",
        action="store_true",
        help="fail collection when primary marker classification is incomplete",
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.pluginmanager.hasplugin("xdist") and config.getoption("numprocesses"):
        raise pytest.UsageError(
            "Core xdist is disabled until each worker has isolated HOME, data, tmp and ports"
        )
    raw = config.getoption("--core-report-dir") or os.environ.get("ONE_MEMORY_TEST_REPORT_DIR")
    if not raw:
        return
    reporter = CoreTestReporter(config, Path(raw), str(config.getoption("--core-suite")))
    config.stash[REPORTER_KEY] = reporter


def _reporter(config: pytest.Config) -> CoreTestReporter | None:
    return config.stash.get(REPORTER_KEY, None)


def pytest_sessionstart(session: pytest.Session) -> None:
    reporter = _reporter(session.config)
    if reporter is not None:
        reporter.started = time.perf_counter()


def pytest_collection(session: pytest.Session) -> None:
    reporter = _reporter(session.config)
    if reporter is not None:
        reporter.begin_collection()


def pytest_collection_finish(session: pytest.Session) -> None:
    reporter = _reporter(session.config)
    if reporter is None:
        return
    reporter.finish_collection(list(session.items))
    if session.config.getoption("--core-classification-enforce") and (
        reporter.unclassified or reporter.multiple or reporter.missing_serial
    ):
        raise pytest.UsageError(
            "Core test classification incomplete: "
            f"unclassified={len(reporter.unclassified)} "
            f"multiple={len(reporter.multiple)} "
            f"missing_serial={len(reporter.missing_serial)}"
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    reporter = _reporter(item.config)
    if reporter is not None:
        reporter.record(report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    reporter = _reporter(session.config)
    if reporter is not None:
        recorded_failures = sum(
            timing.outcome in {"failed", "error"} for timing in reporter.timings.values()
        )
        reporter.collection_errors = max(
            reporter.collection_errors,
            max(0, session.testsfailed - recorded_failures),
        )
        reporter.write(exitstatus)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    reporter = _reporter(config)
    if reporter is None:
        return
    terminalreporter.write_sep("-", "Core test architecture")
    terminalreporter.write_line(f"report directory: {reporter.report_dir}")
    terminalreporter.write_line(
        "classification: "
        f"unclassified={len(reporter.unclassified)} "
        f"multiple={len(reporter.multiple)} "
        f"performance/live without serial={len(reporter.missing_serial)}"
    )
