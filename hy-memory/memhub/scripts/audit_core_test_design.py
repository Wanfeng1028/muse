#!/usr/bin/env python3
"""Report review signals in the Core test suite without judging test value."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TIMING_HOTSPOT_SECONDS = 5.0


def _candidate(kind: str, path: Path, **details: Any) -> dict[str, Any]:
    return {"kind": kind, "file": path.as_posix(), **details}


def source_candidates(tests_root: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates: list[dict[str, Any]] = []
    names: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(tests_root.glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, path.name)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                names[node.name].append(path)
                if "legacy" in node.name.lower():
                    candidates.append(_candidate("legacy_name", path, test=node.name))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, (int, float))
                and node.args[0].value > 0
            ):
                candidates.append(
                    _candidate(
                        "fixed_sleep",
                        path,
                        line=node.lineno,
                        seconds=float(node.args[0].value),
                    )
                )
        if "pytest.mark.xfail" in source:
            candidates.append(_candidate("xfail", path))
    for name, paths in sorted(names.items()):
        unique = sorted({path.as_posix() for path in paths})
        if len(unique) > 1:
            candidates.append(
                {
                    "kind": "duplicate_test_name",
                    "test": name,
                    "files": unique,
                }
            )
    candidates.sort(
        key=lambda item: (
            str(item["kind"]),
            str(item.get("file", "")),
            str(item.get("test", "")),
        )
    )
    return candidates, dict(sorted(Counter(item["kind"] for item in candidates).items()))


def timing_candidates(report_dir: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    path = report_dir / "tests.jsonl"
    if not path.is_file():
        return [], {}
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    candidates: list[dict[str, Any]] = []
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        file = str(row.get("file", ""))
        if file:
            by_file[file].append(row)
        outcome = row.get("outcome")
        if outcome == "xfailed":
            candidates.append(
                {
                    "kind": "xfailed",
                    "file": file,
                    "nodeid": row.get("nodeid"),
                }
            )
        total = row.get("total_seconds")
        if isinstance(total, (int, float)) and total >= TIMING_HOTSPOT_SECONDS:
            candidates.append(
                {
                    "kind": "timing_hotspot",
                    "file": file,
                    "nodeid": row.get("nodeid"),
                    "total_seconds": total,
                }
            )
    for file, file_rows in sorted(by_file.items()):
        executed = [row for row in file_rows if row.get("outcome") != "not_run"]
        if executed and all(row.get("outcome") == "skipped" for row in executed):
            candidates.append({"kind": "all_skipped_file", "file": file})
    candidates.sort(
        key=lambda item: (
            str(item["kind"]),
            str(item.get("file", "")),
            str(item.get("nodeid", "")),
        )
    )
    return candidates, dict(sorted(Counter(item["kind"] for item in candidates).items()))


def audit(report_dir: Path, tests_root: Path) -> dict[str, Any]:
    source, source_counts = source_candidates(tests_root)
    timing, timing_counts = timing_candidates(report_dir)
    result = {
        "schema_version": 1,
        "source_signals": source_counts,
        "timing_signals": timing_counts,
        "candidates": [*source, *timing],
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "design-audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("tests_root", type=Path)
    args = parser.parse_args()
    result = audit(args.report_dir.resolve(), args.tests_root.resolve())
    print(
        "Core test design signals: "
        f"source={result['source_signals']} timing={result['timing_signals']}"
    )


if __name__ == "__main__":
    main()
