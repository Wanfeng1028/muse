from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.core_test_reporting import CoreTestReporter, TestTiming

pytestmark = pytest.mark.contract


def design_audit_module():
    script = Path(__file__).resolve().parents[3] / "scripts" / "audit_core_test_design.py"
    spec = importlib.util.spec_from_file_location("audit_core_test_design_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_test_index_module():
    script = Path(__file__).resolve().parents[3] / "scripts" / "generate_core_test_index.py"
    spec = importlib.util.spec_from_file_location("generate_core_test_index_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def timing(
    nodeid: str,
    *,
    primary: str = "contract",
    markers: tuple[str, ...] = ("contract",),
    outcome: str = "passed",
    setup: float = 0.1,
    call: float = 0.2,
    teardown: float = 0.05,
) -> TestTiming:
    value = TestTiming(
        nodeid=nodeid,
        file=nodeid.split("::", 1)[0],
        primary_marker=primary,
        markers=markers,
        worker="main",
        phases={"setup": setup, "call": call, "teardown": teardown},
        phase_outcomes={"setup": "passed", "call": outcome, "teardown": "passed"},
        outcome=outcome,
    )
    return value


def test_report_writes_sanitized_machine_readable_views(tmp_path: Path) -> None:
    reporter = CoreTestReporter(cast(pytest.Config, object()), tmp_path, "fixture")
    reporter.started -= 1
    reporter.collection_seconds = 0.25
    reporter.collected = 2
    reporter.timings = {
        "tests/test_alpha.py::test_ok": timing("tests/test_alpha.py::test_ok"),
        "tests/test_beta.py::test_skip": timing(
            "tests/test_beta.py::test_skip", outcome="skipped", call=0.0
        ),
    }

    reporter.write(0)

    expected = {
        "run.json",
        "tests.jsonl",
        "collected-nodeids.txt",
        "junit.xml",
        "slowest-tests.md",
        "by-file.csv",
        "by-marker.csv",
        "classification.json",
        "classification-suggestions.json",
    }
    # JUnit is owned by pytest itself, not this plugin.
    assert expected - {"junit.xml"} <= {path.name for path in tmp_path.iterdir()}
    run = json.loads((tmp_path / "run.json").read_text())
    assert run["schema_version"] == 1
    assert run["suite"] == "fixture"
    assert run["collected"] == 2
    assert run["passed"] == 1 and run["skipped"] == 1
    rows = [json.loads(line) for line in (tmp_path / "tests.jsonl").read_text().splitlines()]
    assert {row["outcome"] for row in rows} == {"passed", "skipped"}
    assert all(
        {"setup_seconds", "call_seconds", "teardown_seconds", "total_seconds"} <= row.keys()
        for row in rows
    )
    assert (tmp_path / "collected-nodeids.txt").read_text().splitlines() == [
        "tests/test_alpha.py::test_ok",
        "tests/test_beta.py::test_skip",
    ]
    serialized = "\n".join(path.read_text() for path in tmp_path.iterdir())
    assert "ONE_MEMORY_TEST_REAL_HOME" not in serialized
    assert "Authorization" not in serialized


def test_file_and_marker_aggregates_are_stable(tmp_path: Path) -> None:
    values = [
        timing("tests/test_alpha.py::test_one", call=0.2),
        timing("tests/test_alpha.py::test_two", call=0.4),
        timing(
            "tests/test_beta.py::test_three",
            primary="integration",
            markers=("integration", "serial"),
            call=1.0,
        ),
    ]

    CoreTestReporter._write_group_csv(tmp_path / "files.csv", values, lambda item: item.file)
    CoreTestReporter._write_group_csv(
        tmp_path / "markers.csv", values, lambda item: item.primary_marker
    )

    with (tmp_path / "files.csv").open(newline="") as stream:
        files = list(csv.DictReader(stream))
    assert [row["group"] for row in files] == ["tests/test_alpha.py", "tests/test_beta.py"]
    assert files[0]["cases"] == "2"
    with (tmp_path / "markers.csv").open(newline="") as stream:
        markers = list(csv.DictReader(stream))
    assert [row["group"] for row in markers] == ["contract", "integration"]


def test_classification_suggestions_never_guess_unit_contract_or_integration() -> None:
    values = [
        timing(
            "tests/test_scale_benchmark.py::test_scale",
            primary="unclassified",
            markers=(),
        ),
        timing(
            "tests/test_provider_live.py::test_provider",
            primary="unclassified",
            markers=(),
        ),
        timing(
            "tests/test_ordinary.py::test_behavior",
            primary="unclassified",
            markers=(),
        ),
    ]

    suggestions = CoreTestReporter._classification_suggestions(values)

    assert {(item["file"], item["suggested_primary_marker"]) for item in suggestions} == {
        ("tests/test_provider_live.py", "live"),
        ("tests/test_scale_benchmark.py", "performance"),
    }


def test_design_audit_reports_signals_without_declaring_tests_useless(tmp_path: Path) -> None:
    module = design_audit_module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_alpha.py").write_text(
        """
import asyncio
import pytest

@pytest.mark.xfail(reason="review")
def test_legacy_path():
    pass

async def test_shared_name():
    await asyncio.sleep(0.5)
""",
        encoding="utf-8",
    )
    (tests / "test_beta.py").write_text(
        """
def test_shared_name():
    pass
""",
        encoding="utf-8",
    )

    candidates, counts = module.source_candidates(tests)

    assert counts == {
        "duplicate_test_name": 1,
        "fixed_sleep": 1,
        "legacy_name": 1,
        "xfail": 1,
    }
    assert {item["kind"] for item in candidates} == {
        "duplicate_test_name",
        "fixed_sleep",
        "legacy_name",
        "xfail",
    }


def test_design_audit_uses_real_outcomes_and_ignores_collect_only_not_run(tmp_path: Path) -> None:
    module = design_audit_module()
    rows = [
        {
            "file": "tests/test_hot.py",
            "nodeid": "tests/test_hot.py::test_hot",
            "outcome": "xfailed",
            "total_seconds": 6.0,
            "setup_seconds": 1.0,
            "call_seconds": 4.0,
            "teardown_seconds": 1.0,
        },
        {
            "file": "tests/test_skipped.py",
            "nodeid": "tests/test_skipped.py::test_skip",
            "outcome": "skipped",
            "total_seconds": 0.0,
            "setup_seconds": 0.0,
            "call_seconds": 0.0,
            "teardown_seconds": 0.0,
        },
        {
            "file": "tests/test_collected.py",
            "nodeid": "tests/test_collected.py::test_not_run",
            "outcome": "not_run",
            "total_seconds": 0.0,
            "setup_seconds": 0.0,
            "call_seconds": 0.0,
            "teardown_seconds": 0.0,
        },
    ]
    (tmp_path / "tests.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    candidates, counts = module.timing_candidates(tmp_path)

    assert counts == {"all_skipped_file": 1, "timing_hotspot": 1, "xfailed": 1}
    assert {item.get("file") for item in candidates if item["kind"] == "all_skipped_file"} == {
        "tests/test_skipped.py"
    }


def test_generated_test_index_covers_every_test_file_once() -> None:
    module = load_test_index_module()

    rendered = module.render()
    rows = [line for line in rendered.splitlines() if line.startswith("| `test_")]
    files = sorted(path.name for path in module.TESTS_ROOT.glob("test_*.py"))

    assert len(rows) == len(files)
    assert [row.split("`", 2)[1] for row in rows] == files
    assert rendered.endswith(f"共 {len(files)} 个测试文件。\n")
