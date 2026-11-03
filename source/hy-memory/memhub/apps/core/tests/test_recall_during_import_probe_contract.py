"""Guard the source-level recall-during-import probe's sampling semantics."""

import ast
from pathlib import Path

PROBE = Path(__file__).with_name("measure_c1_recall_during_import.py")


def test_recall_probe_samples_until_terminal_and_separates_unavailable() -> None:
    source = PROBE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "_measure_recall_until" in source
    assert "recall_sampling_terminal" in source
    assert "during_unavailable" in source

    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_measure_recall_until"
    )
    assert any(
        isinstance(node, ast.Compare)
        and any(
            isinstance(comparator, ast.Constant) and comparator.value == 503
            for comparator in node.comparators
        )
        for node in ast.walk(function)
    )
    assert any(
        isinstance(node, ast.Compare)
        and any(
            isinstance(comparator, ast.Constant) and comparator.value == 200
            for comparator in node.comparators
        )
        for node in ast.walk(function)
    )
    assert "time.monotonic() < deadline" in source


def test_recall_probe_does_not_accept_unavailable_as_a_latency_sample() -> None:
    source = PROBE.read_text(encoding="utf-8")
    assert "elif response.status_code == 200:" in source
    assert "latencies.append(elapsed)" in source
    assert 'result["during_unavailable"] = during_unavailable' in source
