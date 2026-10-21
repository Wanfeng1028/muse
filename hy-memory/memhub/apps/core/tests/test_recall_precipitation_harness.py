"""The precipitation measurement harness must stay loadable and single-sourced.

`measure_recall_under_precipitation.py` is not collected by pytest, so nothing
notices when its constants drift. It previously defined `MODEL_DELAY` and
`STORE_CALLS_PER_TASK` twice; the second value won silently. This guard keeps
the runnable harness importable and pins the normal-load constants the C2
hourly evidence cites.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HARNESS = Path(__file__).with_name("measure_recall_under_precipitation.py")


def _load_harness():
    spec = importlib.util.spec_from_file_location("measure_recall_under_precipitation", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harness_loads_with_one_normal_load_contract() -> None:
    module = _load_harness()
    assert module.MODEL_DELAY == 0.05
    assert module.STORE_CALLS_PER_TASK == 6
    assert module.TASKS == 24
    assert module.RECALL_CALLS == 40
    assert module.STRESS_PARALLEL_RECALLS == 8
