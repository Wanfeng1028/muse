"""Measure event-loop blocking during a large import.

The contract asks that a long import must not freeze WorkBuddy or the UI main
thread for more than a second. What that really means for this process is one
number: how long the event loop goes without yielding while an import runs.
This measures it directly with a heartbeat coroutine, and also reports the loop
lag an ordinary queued callback would see, which is what a recall request waits
behind.
"""

import argparse
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from measure_c1_import_scale import build_tree  # noqa: E402

from one_memory.imports.grants import SourceGrantStore  # noqa: E402
from one_memory.imports.jobs import ImportJobStore  # noqa: E402
from one_memory.imports.sources.registry import (  # noqa: E402
    RootCandidateKind,
    build_source_catalog,
    workbuddy_default_homes,
)
from one_memory.imports.storage import EvidenceStore  # noqa: E402
from one_memory.imports.supervisor import ImportSupervisor  # noqa: E402

TICK_SECONDS = 0.02


async def measure_root_selection(tmp: Path, projects: int, files_per_project: int) -> dict:
    """Measure WorkBuddy root selection over a real-shaped project tree."""
    home = tmp / "home"
    root = workbuddy_default_homes(home)[1]
    for project in range(projects):
        directory = root / f"project-{project}"
        directory.mkdir(parents=True)
        for index in range(files_per_project):
            (directory / f"session-{index:04}.jsonl").write_text("{}\n", encoding="utf-8")

    gaps: list[float] = []
    previous = time.perf_counter()
    running = True

    async def heartbeat() -> None:
        nonlocal previous
        while running:
            await asyncio.sleep(TICK_SECONDS)
            now = time.perf_counter()
            gaps.append(now - previous)
            previous = now

    probe = asyncio.create_task(heartbeat())
    await asyncio.sleep(TICK_SECONDS * 2)
    started = time.perf_counter()
    catalog = build_source_catalog(home=home, environment={})
    elapsed = time.perf_counter() - started
    running = False
    await probe
    blocking = [gap - TICK_SECONDS for gap in gaps]
    return {
        "target": projects * files_per_project,
        "projects": projects,
        "files_per_project": files_per_project,
        "root_selection_seconds": round(elapsed, 3),
        "ticks": len(gaps),
        "max_loop_gap_seconds": round(max(gaps), 3) if gaps else None,
        "max_blocking_seconds": round(max(blocking), 3) if blocking else None,
        "over_one_second_ticks": sum(1 for value in blocking if value > 1.0),
        "chosen": str(catalog["workbuddy"].candidate.path),
    }


async def measure(tmp: Path, target: int) -> dict:
    home = tmp / "home"
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    registration = build_source_catalog(home=home, environment={})["codex"]
    root = registration.candidate.path
    root.mkdir(parents=True, exist_ok=True)
    build_tree(root, 40, max(1, target // 40))

    database = tmp / "core.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=home)
    grants.grant(
        user_id="local",
        source_id="codex",
        root=root,
        candidate_kind=RootCandidateKind.DEFAULT,
    )
    supervisor = ImportSupervisor(
        adapters={
            "codex": registration.create_adapter(
                grants.authorized_root(user_id="local", source_id="codex")
            )
        },
        evidence_store=evidence,
        job_store=jobs,
    )

    gaps: list[float] = []
    running = True
    previous = time.perf_counter()

    async def heartbeat() -> None:
        nonlocal previous
        while running:
            await asyncio.sleep(TICK_SECONDS)
            now = time.perf_counter()
            gaps.append(now - previous)
            previous = now

    probe = asyncio.create_task(heartbeat())
    started = time.perf_counter()
    job = supervisor.create_job("codex")
    supervisor.enqueue(job.job_id)
    final = await supervisor.wait(job.job_id)
    elapsed = time.perf_counter() - started
    running = False
    await probe

    # What a callback queued now would wait behind, sampled while the import ran.
    blocking = [gap - TICK_SECONDS for gap in gaps]
    return {
        "target": target,
        "stored": final.stored,
        "end_to_end_seconds": round(elapsed, 3),
        "ticks": len(gaps),
        "max_loop_gap_seconds": round(max(gaps), 3) if gaps else None,
        "max_blocking_seconds": round(max(blocking), 3) if blocking else None,
        "p95_blocking_seconds": round(statistics.quantiles(blocking, n=20)[-1], 3)
        if len(blocking) >= 20
        else None,
        "over_one_second_ticks": sum(1 for value in blocking if value > 1.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=int, default=100_000)
    parser.add_argument(
        "--root-selection",
        action="store_true",
        help="measure WorkBuddy root selection, not import",
    )
    parser.add_argument("--projects", type=int, default=250)
    parser.add_argument("--files-per-project", type=int, default=450)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="c1-blocking-") as directory:
        if args.root_selection:
            result = asyncio.run(
                measure_root_selection(
                    Path(directory),
                    projects=args.projects,
                    files_per_project=args.files_per_project,
                )
            )
        else:
            result = asyncio.run(measure(Path(directory), args.scale))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
