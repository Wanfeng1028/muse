"""Contrast import concurrency against event-loop latency.

The shipped default is one import job at a time, so "import ten sources" never
actually runs concurrently. Raising it is a product decision, and the trade-off
is real: several sources reading big histories at once contend for I/O and the
SQLite writer, which is exactly what could push a recall past its budget.

This measures both sides at once: how long the import takes, and how long a
callback queued on the loop waits while it runs — the same number a recall
request would wait behind.
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

from one_memory.imports.grants import SourceGrantStore  # noqa: E402
from one_memory.imports.jobs import ImportJobStore  # noqa: E402
from one_memory.imports.sources.registry import (  # noqa: E402
    RootCandidateKind,
    build_source_catalog,
)
from one_memory.imports.storage import EvidenceStore  # noqa: E402
from one_memory.imports.supervisor import ImportSupervisor  # noqa: E402

TICK_SECONDS = 0.02


def _record(source: str, index: int) -> dict:
    text = f"{source}-{index}"
    if source == "codex":
        return {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user" if index % 2 == 0 else "assistant",
                "content": [{"type": "input_text", "text": text}],
            },
        }
    if source == "cursor":
        return {
            "role": "user" if index % 2 == 0 else "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
        }
    # claude-code / workbuddy / pi / qwenwork all read role + message content.
    return {
        "type": "user" if index % 2 == 0 else "assistant",
        "sessionId": f"session-{source}",
        "timestamp": "2026-09-28T10:00:00+08:00",
        "message": {"content": text},
    }


def _write(path: Path, source: str, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for index in range(count):
            stream.write(json.dumps(_record(source, index)) + "\n")


async def measure(tmp: Path, sources: int, per_source: int, concurrent: int) -> dict:
    home = tmp / "home"
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    catalog = build_source_catalog(home=home, environment={})
    database = tmp / "core.sqlite3"
    jobs = ImportJobStore(database)
    evidence = EvidenceStore(database)
    grants = SourceGrantStore(database, home=home)

    adapters = {}
    job_ids = []
    # Distinct real sources, each with its own layout and parser. Reusing one
    # source id for several roots would just re-point the same grant and import
    # a single tree, which measures nothing about concurrency.
    chosen = ["codex", "claude-code", "workbuddy", "cursor", "pi", "qwenwork"][:sources]
    for index, source in enumerate(chosen):
        root = tmp / f"root-{index}"
        root.mkdir()
        # Cursor's unified reader only looks at `agent-transcripts/*.jsonl`;
        # writing a Codex-shaped path there would import nothing and quietly
        # turn this into a three-source measurement.
        relative = (
            Path("projects/acme/agent-transcripts") / f"matrix-{index}" / "matrix.jsonl"
            if source == "cursor"
            else Path("project") / f"rollout-{index}.jsonl"
        )
        _write(root / relative, source, per_source)
        grants.grant(
            user_id="local",
            source_id=source,
            root=root,
            candidate_kind=RootCandidateKind.DEFAULT,
        )
        adapters[source] = catalog[source].create_adapter(
            grants.authorized_root(user_id="local", source_id=source)
        )

    supervisor = ImportSupervisor(
        adapters=adapters,
        evidence_store=evidence,
        job_store=jobs,
        max_concurrent_jobs=concurrent,
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
    for source in chosen:
        job = supervisor.create_job(source)
        supervisor.enqueue(job.job_id)
        job_ids.append(job.job_id)
    final = None
    for job_id in job_ids:
        final = await supervisor.wait(job_id)
    elapsed = time.perf_counter() - started
    running = False
    await probe

    blocking = [gap - TICK_SECONDS for gap in gaps]
    return {
        "sources": sources,
        "per_source": per_source,
        "concurrent": concurrent,
        "end_to_end_seconds": round(elapsed, 3),
        "stored_total": evidence.count(),
        "final_stored": final.stored if final else None,
        "max_blocking_seconds": round(max(blocking), 3) if blocking else None,
        "p95_blocking_seconds": round(statistics.quantiles(blocking, n=20)[-1], 3)
        if len(blocking) >= 20
        else None,
        "over_one_second_ticks": sum(1 for value in blocking if value > 1.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=int, default=4)
    parser.add_argument("--per-source", type=int, default=5000)
    parser.add_argument("--concurrent", type=int, default=1)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="c1-conc-") as directory:
        result = asyncio.run(
            measure(Path(directory), args.sources, args.per_source, args.concurrent)
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
