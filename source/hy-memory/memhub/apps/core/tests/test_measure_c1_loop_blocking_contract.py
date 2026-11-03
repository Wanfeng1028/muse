"""Contract guards for the C1 event-loop blocking measurement."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("measure_c1_import_loop_blocking.py")


def test_root_selection_mode_reports_the_issue_6_observable(tmp_path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            str(SCRIPT),
            "--root-selection",
            "--projects",
            "2",
            "--files-per-project",
            "3",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["target"] == 6
    assert payload["projects"] == 2
    assert payload["files_per_project"] == 3
    assert payload["over_one_second_ticks"] >= 0
    assert payload["max_blocking_seconds"] >= 0
    assert payload["chosen"].endswith("/projects")
