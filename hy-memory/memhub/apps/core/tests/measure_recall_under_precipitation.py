"""Rule 2/9: does raising precipitation concurrency starve interactive recall?

`api.py` pins `max_concurrent_tasks=1`, and `a59f4b5` says why: "keep
precipitation from competing with interactive recall for the same reader pool"
— and calls the pin *temporary*, for an acceptance package. The pin has
outlived that package and it contradicts rule 9 (parameters configurable, not
hardcoded small) and rule 2 (don't hardcode an upper bound).

But the concern behind it is real and measurable: reads share a pool of 4, and
precipitation is store-call heavy. So this does not argue from principle — it
measures recall latency while precipitation runs at concurrency 1 and at 4, on
the same machine, with the same corpus and the same fake model delay.

Not collected by pytest (no `test_` prefix); run it directly:

    .venv/bin/python tests/measure_recall_under_precipitation.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from one_memory.database_access import main_database_stats
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_processing import MemoryProcessingSupervisor
from tests.test_memory_queue_recency import _stores, _task

TASKS = 24
RECALL_CALLS = 40
# Long enough that readers are genuinely held while recall is trying to read.
# At 0.02s every row came out identical, which is the warning sign the repo
# calls out explicitly: two equal values are not evidence of no difference.
MODEL_DELAY = 0.05
STORE_CALLS_PER_TASK = 6

# A second, deliberately brutal configuration, run alongside the first. Its
# job is not to be realistic but to prove the harness *can* show a difference:
# if even this comes out flat, the measurement is blind and no conclusion
# (in either direction) can be drawn from it.
STRESS_DELAY = 0.4
STRESS_STORE_CALLS = 40
STRESS_RECALL_CALLS = 60
# Enough held readers to actually exhaust a pool of 4.
STRESS_HOLD = 0.25
STRESS_PARALLEL_RECALLS = 8


class StoreHeavyRunner:
    """A runner that uses the reader pool the way precipitation really does.

    A runner that only `sleep`s holds no reader, so concurrency cannot contend
    with anything and every row of the table comes out identical — a
    measurement that cannot detect the thing it is looking for. The real path
    claims the task, reads its inputs, and writes the outcome; all of those go
    through the same pool recall uses.
    """

    def __init__(
        self,
        tasks,
        delay: float = MODEL_DELAY,
        store_calls: int = STORE_CALLS_PER_TASK,
        hold: float = 0.0,
    ) -> None:
        self.tasks = tasks
        self.delay = delay
        self.store_calls = store_calls
        self.hold = hold
        self.calls = 0

    async def run(self, task_id: str, *, timeout: float | None = None) -> None:
        self.calls += 1
        await asyncio.sleep(self.delay)
        # Real store work, off the loop exactly as the production runner does:
        # what is under measurement is contention for readers, not the loop.
        await asyncio.to_thread(self._store_work, task_id)

    def _store_work(self, task_id: str) -> None:
        for _ in range(self.store_calls):
            self.tasks.inputs(task_id)
            self.tasks.require(task_id)
            if self.hold > 0:
                # Hold the reader across the whole batch rather than checking it
                # back between calls: a pool of 4 only saturates if readers are
                # held, and `peak_open` staying at 2 is how you can tell the
                # measurement never reproduced the production condition.
                time.sleep(self.hold)


def _held_reader_work(store, hold: float) -> None:
    """A reader held for `hold` seconds, the way a slow recall query is."""
    store.list(statuses=())
    time.sleep(hold)


TASK_SOURCES = ("cursor", "claude-code", "codex", "workbuddy", "pi", "qwen-code")


def _put_multi(
    evidence: EvidenceStore,
    *,
    message_id: str,
    content: str,
    created_at: datetime,
    conversation_id: str,
    source_id: str,
    workspace: str | None = None,
) -> object:
    """`_put` with a caller-chosen source.

    The harness cap is per `source_id`, so seeding every task under one source
    serialises all of them and concurrency can never exceed 1 — a measurement
    that would report "no difference" for the wrong reason.
    """
    return evidence.put(
        EvidenceInput(
            source_id=source_id,
            workspace=workspace,
            conversation_id=conversation_id,
            message_id=message_id,
            correlation_id=message_id,
            role="user",
            written_by=WrittenBy.PERSON,
            created_at=created_at,
            verbatim=content,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record


def _seed(tmp_path: Path, count: int) -> tuple[list[str], object]:
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    now = datetime.now(UTC)
    ids = []
    for index in range(count):
        source_id = TASK_SOURCES[index % len(TASK_SOURCES)]
        record = _put_multi(
            evidence,
            message_id=f"m{index}",
            content=f"content {index}",
            created_at=now - timedelta(minutes=index),
            source_id=source_id,
            conversation_id=f"c{index}",
            workspace="workspace:v1:measure",
        )
        ids.append(_task(tasks, profile, record, suffix=f"s{index}").task_id)
    return ids, stores


async def _measure(
    concurrency: int | None,
    *,
    delay: float = MODEL_DELAY,
    store_calls: int = STORE_CALLS_PER_TASK,
    recall_calls: int = RECALL_CALLS,
    hold: float = 0.0,
    parallel_recalls: int = 1,
) -> dict[str, float]:
    """Recall latency while precipitation runs at a given concurrency."""
    tmp_path = Path(tempfile.mkdtemp(prefix="om-measure-"))
    _ids, stores = _seed(tmp_path, TASKS)
    supervisor = MemoryProcessingSupervisor(
        tasks=stores[2],
        profiles=stores[1],
        secrets=stores[4],
        evidence=stores[0],
        governance=stores[3],
        data_dir=tmp_path,
        runner_factory=lambda: StoreHeavyRunner(  # noqa: B023
            stores[2], delay=delay, store_calls=store_calls, hold=hold
        ),
        max_concurrent_tasks=concurrency,
    )
    supervisor._schedule_tasks(supervisor.prepare_resume())

    # A recall-shaped read, off the loop in a thread exactly as the recall path
    # does it: what is under measurement is contention for readers, not the loop.
    samples: list[float] = []
    peak_in_flight = 0
    for _ in range(recall_calls):
        peak_in_flight = max(peak_in_flight, len(supervisor._in_flight))
        started = monotonic()
        # `parallel_recalls` reads at once: a pool of 4 cannot saturate from a
        # single reader, so without this the measurement cannot observe the
        # contention it is looking for.
        await asyncio.gather(
            *(
                asyncio.to_thread(_held_reader_work, stores[2], hold)
                for _ in range(parallel_recalls)
            )
        )
        samples.append((monotonic() - started) * 1000)
        await asyncio.sleep(0)

    await supervisor.shutdown()
    # The pool metrics the database decision was argued on. Recall latency
    # alone can look flat while reads are quietly queueing behind each other,
    # which is exactly how `reader_wait_ms_max` reached 18s in production.
    stats = main_database_stats()
    return {
        "concurrency": float("nan" if concurrency is None else concurrency),
        "median_ms": statistics.median(samples),
        "p95_ms": sorted(samples)[int(len(samples) * 0.95) - 1],
        "max_ms": max(samples),
        "peak_in_flight": float(peak_in_flight),
        "reader_wait_ms_max": float(stats["reader_wait_ms_max"]),
        "reader_waits": float(stats["reader_waits"]),
        "peak_open": float(stats["peak_open_connections"]),
    }


def _row(result: dict[str, float]) -> str:
    return (
        f"{int(result['concurrency']):>12} "
        f"{result['median_ms']:>10.1f} {result['p95_ms']:>10.1f} "
        f"{result['max_ms']:>10.1f} {int(result['peak_in_flight']):>14} "
        f"{result['reader_waits']:>12.0f} {result['reader_wait_ms_max']:>18.1f} "
        f"{int(result['peak_open']):>11}"
    )


def main() -> None:
    print(f"{TASKS} tasks x {RECALL_CALLS} recall reads, model delay {MODEL_DELAY}s")
    print(
        f"{'concurrency':>12} {'median_ms':>10} {'p95_ms':>10} "
        f"{'max_ms':>10} {'peak_inflight':>14} {'reader_waits':>12} "
        f"{'reader_wait_ms_max':>18} {'peak_open':>11}"
    )
    for concurrency in (1, 2, 4, 8):
        result = asyncio.run(_measure(concurrency))
        print(_row(result))

    # Positive control. Two equal columns above prove nothing on their own —
    # the repo has been burned by exactly that. So: drive the same harness
    # into real contention and confirm the numbers actually move. If they do
    # not, the flat columns above are a blind measurement, not a finding.
    print()
    print("positive control (heavy store load, long-held readers):")
    print(
        f"{'concurrency':>12} {'median_ms':>10} {'p95_ms':>10} "
        f"{'max_ms':>10} {'peak_inflight':>14} {'reader_waits':>12} "
        f"{'reader_wait_ms_max':>18} {'peak_open':>11}"
    )
    for concurrency in (1, 4, 8):
        result = asyncio.run(
            _measure(
                concurrency,
                delay=STRESS_DELAY,
                store_calls=STRESS_STORE_CALLS,
                recall_calls=STRESS_RECALL_CALLS,
                hold=STRESS_HOLD,
                parallel_recalls=STRESS_PARALLEL_RECALLS,
            )
        )
        print(_row(result))


if __name__ == "__main__":
    main()
