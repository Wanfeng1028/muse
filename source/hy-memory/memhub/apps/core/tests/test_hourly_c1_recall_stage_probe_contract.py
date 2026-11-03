"""Guard the packaged recall stage probe's command and error semantics."""

import ast
from pathlib import Path

PROBE = Path(__file__).with_name("hourly_c1_recall_stage_probe.py")


def test_recall_stage_probe_uses_positional_query_and_fails_on_errors() -> None:
    tree = ast.parse(PROBE.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_run"
    ]
    recall_list = next(
        node
        for call in calls
        for node in call.args
        if isinstance(node, ast.List)
        and any(isinstance(item, ast.Constant) and item.value == "recall" for item in node.elts)
    )
    assert any(
        isinstance(item, ast.Constant) and item.value == "budget decision"
        for item in recall_list.elts
    )
    assert not any(
        isinstance(item, ast.Constant) and item.value == "--query" for item in recall_list.elts
    )

    source = PROBE.read_text(encoding="utf-8")
    assert "if result.returncode != 0:" in source
    assert 'receipt["state"] = "passed" if not errors else "failed"' in source
