"""Guard the package peak-replay probe's error accounting.

C8 independently found that the idle recall baseline discarded its process
exit code, so a failing recall could contribute a low latency to the idle
maximum while the run still passed. The probe is a standalone script, so this
guard inspects its executable source rather than importing it.
"""

import ast
from pathlib import Path

PROBE = Path(__file__).with_name("hourly_c1_import_peak_replay.py")


def test_peak_replay_records_and_rejects_idle_recall_errors() -> None:
    source = PROBE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    main = functions["main"]

    idle_assign = next(
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "idle_latencies"
            for target in node.targets
        )
    )
    idle_loop = next(
        node
        for node in ast.walk(main)
        if isinstance(node, ast.For) and node.lineno > idle_assign.lineno
    )
    idle_body = [ast.dump(node) for node in idle_loop.body]

    assert any("idle_errors" in part for part in idle_body), "idle errors are not collected"
    assert any(
        isinstance(node, ast.Compare)
        and isinstance(node.ops[0], ast.NotEq)
        and any(
            isinstance(comparator, ast.Constant) and comparator.value == 0
            for comparator in node.comparators
        )
        for node in ast.walk(idle_loop)
    ), "idle exit code is not checked"
    assert "idle_recall_error_codes" in source
    assert "and not idle_errors" in source
