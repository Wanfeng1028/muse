"""Before/after wall clock for one batch, same fake model, same machine.

Not a test: a measurement. Run with
`uv run --no-sync pytest -q -s -p no:cacheprovider tests/measure_sedimentation_speedup.py`.

Both sides are built here in the sandbox. The real machine's numbers cannot
be a baseline: the log they came from was written with a diagnostic fsync on
every line and a second experiment running alongside.
"""

from __future__ import annotations

import asyncio
import statistics
import time

from tests.test_sedimentation_concurrency import (
    WatchedBridge,
    _conversations,
    _drain,
    _setup,
    _supervise,
)

CONVERSATIONS = 12
ROUNDS = 3
#: Two mixes, because the answer depends entirely on which one you are in.
#: The real machine measured 6.5% of sedimentation inside the model, so the
#: second row is the one that resembles it, and the first is the ceiling.
MIXES = (0.25, 0.005)


def _one_run(tmp_path, *, workers: int | None, MODEL_SECONDS: float) -> tuple[float, int]:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    _conversations(evidence, count=CONVERSATIONS)
    bridge = WatchedBridge(seconds=MODEL_SECONDS)
    kwargs = {} if workers is None else {"max_concurrent_tasks": workers}

    async def exercise() -> float:
        supervisor = _supervise(tmp_path, stores, bridge, **kwargs)
        return await _drain(supervisor, tasks, expected=CONVERSATIONS)

    return asyncio.run(exercise()), bridge.peak


def test_measure(tmp_path_factory) -> None:
    print()
    print(f"{CONVERSATIONS} 段对话，{ROUNDS} 轮取中位数，测于 {time.strftime('%Y-%m-%d %H:%M')}")
    print(
        f"{'假模型每次':>10}{'模型占串行耗时':>16}{'串行':>10}{'并发':>10}{'实测并行度':>12}{'加速比':>9}"
    )
    for model_seconds in MIXES:
        medians, peaks = [], []
        for workers in (1, None):
            times, seen = [], []
            for index in range(ROUNDS):
                elapsed, peak = _one_run(
                    tmp_path_factory.mktemp(f"m{model_seconds}-{workers}-{index}"),
                    workers=workers,
                    MODEL_SECONDS=model_seconds,
                )
                times.append(elapsed)
                seen.append(peak)
            medians.append(statistics.median(times))
            peaks.append(max(seen))
        before, after = medians
        share = CONVERSATIONS * model_seconds / before
        print(
            f"{model_seconds:>9.3f}s{share:>15.1%}{before:>9.2f}s{after:>9.2f}s"
            f"{peaks[1]:>10}{before / after:>8.2f}x"
        )
