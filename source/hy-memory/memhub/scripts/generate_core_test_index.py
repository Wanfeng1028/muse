#!/usr/bin/env python3
"""Render the reviewed Core test-file index deterministically."""

from __future__ import annotations

import argparse
import ast
import difflib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = ROOT / "apps/core/tests"
CLASSIFICATION = TESTS_ROOT / "core_test_classification.py"
OUTPUT = TESTS_ROOT / "TEST_INDEX.md"
ROW = re.compile(r"^\| `(?P<file>test_[^`]+\.py)` \| `[^`]+` \| (?P<summary>.*) \|$")


def _reviewed_files(name: str) -> frozenset[str]:
    tree = ast.parse(CLASSIFICATION.read_text(encoding="utf-8"), CLASSIFICATION.name)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if (
            not isinstance(value, ast.Call)
            or not isinstance(value.func, ast.Name)
            or value.func.id != "frozenset"
            or len(value.args) != 1
        ):
            break
        literal = ast.literal_eval(value.args[0])
        if not isinstance(literal, set) or not all(isinstance(item, str) for item in literal):
            break
        return frozenset(literal)
    raise ValueError(f"{name} must be a literal frozenset in {CLASSIFICATION}")


def _existing_summaries() -> dict[str, str]:
    if not OUTPUT.is_file():
        return {}
    summaries: dict[str, str] = {}
    for line in OUTPUT.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            summaries[match.group("file")] = match.group("summary")
    return summaries


def _fallback_summary(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), path.name)
    doc = ast.get_docstring(tree, clean=True)
    if doc:
        first_paragraph = doc.split("\n\n", 1)[0]
        summary = " ".join(part.strip() for part in first_paragraph.splitlines() if part.strip())
        if summary:
            return summary
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            names.append(node.name.removeprefix("test_").replace("_", " "))
    names.sort()
    if not names:
        return "Core test module."
    preview = "、".join(names[:3])
    suffix = f" 等 {len(names)} 个场景。" if len(names) > 3 else " 场景。"
    return f"覆盖 {preview}{suffix}"


def _safe_cell(value: str) -> str:
    return " ".join(value.split()).replace("|", r"\|")


def render() -> str:
    files = tuple(sorted(TESTS_ROOT.glob("test_*.py"), key=lambda path: path.name))
    names = {path.name for path in files}
    unit = _reviewed_files("UNIT_FILES")
    integration = _reviewed_files("INTEGRATION_FILES")
    missing = sorted((unit | integration) - names)
    overlap = sorted(unit & integration)
    if missing or overlap:
        raise ValueError(
            f"classification references missing={missing} overlap={overlap}"
        )
    existing = _existing_summaries()
    lines = [
        "# Core 测试文件清单",
        "",
        "此文件由 `scripts/generate_core_test_index.py` 生成；每个 Core 测试文件必须有且只有一条记录。",
        "",
        "| 测试文件 | 等级 | 一句话说明 |",
        "| --- | --- | --- |",
    ]
    for path in files:
        level = (
            "unit"
            if path.name in unit
            else "integration"
            if path.name in integration
            else "contract"
        )
        summary = existing.get(path.name) or _fallback_summary(path)
        lines.append(f"| `{path.name}` | `{level}` | {_safe_cell(summary)} |")
    lines.extend(("", f"共 {len(files)} 个测试文件。", ""))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
    if args.check:
        if current != rendered:
            diff = difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(OUTPUT),
                tofile=f"{OUTPUT} (generated)",
                lineterm="",
            )
            print("\n".join(diff))
            raise SystemExit(1)
        print(f"Core test index is current: {len(tuple(TESTS_ROOT.glob('test_*.py')))} files")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Core test index updated: {len(tuple(TESTS_ROOT.glob('test_*.py')))} files")


if __name__ == "__main__":
    main()
