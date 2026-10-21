"""Measure C1 import cost and status latency at 100k / 430k Evidence scale.

Runs against a throwaway SQLite database and a synthetic native-format tree; no
real host history and no `~/.one-memory` is touched. Reports the seven numbers
the import contract cares about: bytes read, open count, hash count, job count,
duplicate count, commit wait, and end-to-end duration. It also measures how long
after submit the first real job state is visible, and whether later updates land
at least once per second.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from one_memory.database_access import main_database_stats
from one_memory.imports.access import AuthorizedSourceFile
from one_memory.imports.grants import SourceGrantStore
from one_memory.imports.jobs import ImportJobStore
from one_memory.imports.sources.registry import RootCandidateKind, build_source_catalog
from one_memory.imports.storage import EvidenceStore
from one_memory.imports.supervisor import ImportSupervisor


class Counter:
    def __init__(self) -> None:
        self.opens = 0
        self.bytes_read = 0
        self.hashes = 0

    def install(self) -> None:
        self._open = AuthorizedSourceFile.open_binary
        self._sha256 = hashlib.sha256

        def opened(source_file):
            self.opens += 1
            handle = self._open(source_file)
            original_read = handle.read
            original_readline = handle.readline

            def reading(size):
                chunk = original_read(size)
                self.bytes_read += len(chunk)
                return chunk

            def reading_line(size=-1):
                line = original_readline(size)
                self.bytes_read += len(line)
                return line

            handle.read = reading
            handle.readline = reading_line
            return handle

        def counted_sha256(*args, **kwargs):
            self.hashes += 1
            return self._sha256(*args, **kwargs)

        AuthorizedSourceFile.open_binary = opened
        hashlib.sha256 = counted_sha256

    def uninstall(self) -> None:
        AuthorizedSourceFile.open_binary = self._open
        hashlib.sha256 = self._sha256


def build_tree(root: Path, conversations: int, messages: int) -> int:
    total = 0
    for index in range(conversations):
        path = root / f"project/rollout-session-{index}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            for ordinal in range(messages):
                stream.write(
                    json.dumps(
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "user" if ordinal % 2 == 0 else "assistant",
                                "content": [{"type": "input_text", "text": f"s{index}-m{ordinal}"}],
                            },
                        }
                    )
                    + "\n"
                )
                total += 1
    return total


async def measure(tmp: Path, target: int, *, conversations: int = 40) -> dict:
    home = tmp / "home"
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    registration = build_source_catalog(home=home, environment={})["codex"]
    root = registration.candidate.path
    root.mkdir(parents=True, exist_ok=True)
    per_conversation = max(1, target // conversations)
    written = build_tree(root, conversations, per_conversation)

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
    counter = Counter()
    counter.install()
    grant = grants.authorized_root(user_id="local", source_id="codex")
    supervisor = ImportSupervisor(
        adapters={"codex": registration.create_adapter(grant)},
        evidence_store=evidence,
        job_store=jobs,
    )
    try:
        started = time.perf_counter()
        before_stats = main_database_stats()
        job = supervisor.create_job("codex")
        supervisor.enqueue(job.job_id)
        seen_updates: list[float] = []
        first_state_at: float | None = None
        last_snapshot = None
        while True:
            current = jobs.require(job.job_id)
            snapshot = (current.status, current.discovered, current.stored, current.emitted)
            if snapshot != last_snapshot:
                now = time.perf_counter() - started
                if first_state_at is None:
                    first_state_at = now
                seen_updates.append(now)
                last_snapshot = snapshot
            if current.status in {"completed", "failed", "cancelled", "paused"}:
                break
            await asyncio.sleep(0.05)
        final = await supervisor.wait(job.job_id)
        elapsed = time.perf_counter() - started
        after_stats = main_database_stats()
    finally:
        counter.uninstall()

    gaps = [
        round(second - first, 3)
        for first, second in zip(seen_updates, seen_updates[1:], strict=False)
    ]
    return {
        "target": target,
        "written_records": written,
        "stored": final.stored,
        "merged": final.merged,
        "duplicates": _duplicate_evidence_rows(database),
        "errors": final.errors,
        "opens": counter.opens,
        "bytes_read": counter.bytes_read,
        "hashes": counter.hashes,
        "job_count": 1,
        "writer_waits": int(after_stats["writer_waits"] - before_stats["writer_waits"]),
        "writer_wait_ms_total": round(
            float(after_stats["writer_wait_ms_total"])
            - float(before_stats["writer_wait_ms_total"]),
            1,
        ),
        "writer_wait_ms_process_max": float(after_stats["writer_wait_ms_max"]),
        "first_visible_state_seconds": round(first_state_at or -1, 3),
        "status_updates": len(seen_updates),
        "max_status_gap_seconds": max(gaps) if gaps else None,
        "end_to_end_seconds": round(elapsed, 3),
        "records_per_second": round(final.stored / elapsed, 1) if elapsed else None,
    }


def _duplicate_evidence_rows(database: Path) -> int:
    """Count evidence rows beyond the first for each idempotency key."""
    import sqlite3

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(count - 1), 0)
            FROM (
                SELECT COUNT(*) AS count
                FROM evidence
                GROUP BY idempotency_key
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
    return int(row[0]) if row else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=int, default=100_000)
    parser.add_argument("--conversations", type=int, default=40)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="c1-scale-") as directory:
        result = asyncio.run(measure(Path(directory), args.scale, conversations=args.conversations))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
