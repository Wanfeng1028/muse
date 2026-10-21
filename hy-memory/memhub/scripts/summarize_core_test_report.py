#!/usr/bin/env python3
"""Write a compact Markdown summary for one Core pytest report directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def summarize(report_dir: Path) -> str:
    run = _read_json(report_dir / "run.json")
    audit = _read_json(report_dir / "design-audit.json")
    lines = [
        "# Core test report",
        "",
        f"- Suite: `{run.get('suite', 'unknown')}`",
        f"- Collected: {run.get('collected', 0)}",
        f"- Passed: {run.get('passed', 0)}",
        f"- Failed: {run.get('failed', 0)}",
        f"- Skipped: {run.get('skipped', 0)}",
        f"- Source review signals: `{audit.get('source_signals', {})}`",
        f"- Timing review signals: `{audit.get('timing_signals', {})}`",
        "",
        "Review signals identify files for human inspection; they do not classify tests as useful or useless.",
        "",
    ]
    rendered = "\n".join(lines)
    (report_dir / "summary.md").write_text(rendered, encoding="utf-8")
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    print(summarize(args.report_dir.resolve()), end="")


if __name__ == "__main__":
    main()
