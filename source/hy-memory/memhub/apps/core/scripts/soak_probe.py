#!/usr/bin/env python
"""8-hour soak probe: queue / connection / handle / disk trend, as JSONL.

The objective asks for a soak that can show nothing grows without bound:
open connections, file handles, threads, queue depth and on-disk size. This
probe samples them periodically and writes one JSON object per line, so the
trend can be read without a dashboard.

It is deliberately read-only with respect to One Memory data: it never opens
the daily Home, only the database path it is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from one_memory.database_access import (  # noqa: E402
    close_main_databases,
    main_database,
    main_database_stats,
)
from one_memory.imports.models import (  # noqa: E402
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore  # noqa: E402
from one_memory.memory_server.contracts import BatchIdentity, WriteRequest  # noqa: E402
from one_memory.memory_server.durable_queue import DurableWriteQueue  # noqa: E402


def _probe_initialize(database_path: Path) -> None:
    """Create the schema a soak needs, in this process.

    The sampler used to rely on a separate `soak_load_driver.py` process to
    create Evidence and queue rows. Beyond leaving the sampler's process-local
    wait counters at zero, that also meant the sampled database could be empty
    if the driver was not started. Initializing here makes the probe
    self-contained: the same process both writes and measures.
    """
    EvidenceStore(database_path)
    DurableWriteQueue(database_path)


def _run_in_process_load(
    database_path: Path,
    *,
    seconds: float,
    every: float,
    batch: int,
    readers: int = 0,
) -> int:
    """Run the soak load on this process's access layer.

    `main_database_stats()` is process-local, so a load in another process is
    invisible to the sampler: `open_connections` and `writer/reader waits`
    would read zero no matter how much contention existed. This writes the
    same Evidence + durable queue rows as `soak_load_driver` but in the
    sampling process, so the wait figures are real. Returns accepted writes.
    """
    store = EvidenceStore(database_path)
    queue = DurableWriteQueue(database_path)
    stop = threading.Event()

    def read_loop() -> None:
        # One writer thread can never make a reader wait, so a writer-only soak
        # reports `reader_waits=0` by construction and says nothing about the
        # read path under an import peak. These readers make the wait figures
        # meaningful.
        while not stop.is_set():
            try:
                with main_database(database_path).read() as connection:
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE source_id='soak-in-process'"
                    ).fetchone()
            except sqlite3.Error:
                # The load under test is the writer contention, not the read
                # statement; a failed read still counts in the access layer's
                # own refusal counters, which is what the probe reports.
                pass

    reader_threads = [
        threading.Thread(target=read_loop, name=f"soak-reader-{index}", daemon=True)
        for index in range(max(0, readers))
    ]
    for thread in reader_threads:
        thread.start()
    end = time.monotonic() + seconds
    accepted = 0
    try:
        while time.monotonic() < end:
            ids = []
            for index in range(batch):
                stamp = datetime.now(UTC)
                record = store.put(
                    EvidenceInput(
                        source_id="soak-in-process",
                        conversation_id="soak",
                        message_id=f"soak-{stamp.timestamp()}-{index}",
                        role="user" if index % 2 else "assistant",
                        written_by=WrittenBy.PERSON if index % 2 else WrittenBy.AGENT,
                        verbatim=f"soak load {stamp.isoformat()} #{index}",
                        created_at=stamp,
                        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                    )
                ).record
                ids.append(record.evidence_id)
            queue.submit(
                WriteRequest(
                    internal_session_id="soak-session",
                    batch_identity=BatchIdentity(
                        internal_session_id="soak-session", first_round=1, last_round=1
                    ),
                    evidence_ids=ids,
                    idempotency_key=f"soak-{time.time_ns()}",
                )
            )
            accepted += 1
            time.sleep(max(0.0, every))
    finally:
        stop.set()
        for thread in reader_threads:
            thread.join(timeout=5)
    return accepted


def _directory_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            total += entry.stat().st_size
        except OSError:
            continue
    return total


def _threads() -> int:
    """Thread count for this process, on Linux then macOS.

    `/proc/<pid>/status` is Linux-only. macOS `ps` has no `nlwp` keyword, so
    `ps -M` is used: it prints one line per thread. A probe reporting -1 would
    make the soak trend unreadable, so both paths are attempted.
    """
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("Threads:"):
                    return int(line.split()[1])
    except OSError:
        pass
    # `ps -M` fails transiently under load. Retry once: a single bogus `-1`
    # in the trend is worse than a second attempt, because the sample file is
    # read later as evidence that threads did not grow.
    for attempt in range(2):
        try:
            output = subprocess.run(
                ["ps", "-M", "-p", str(os.getpid())],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            lines = [line for line in output.stdout.splitlines() if line.strip()]
            if not lines:
                raise ValueError("ps -M returned no rows")
            # One header line precedes the per-thread rows.
            return max(1, len(lines) - 1)
        except (OSError, ValueError, subprocess.SubprocessError):
            if attempt == 1:
                return -1
    return -1


def _open_handles() -> int:
    """Open file descriptors for this process, excluding the listing itself.

    `os.listdir("/dev/fd")` includes the fd opened by the listing call, so a
    naive count climbs by one per sample and masquerades as a leak. The
    directory fd is opened before the snapshot and subtracted.
    """
    try:
        listing = os.open("/dev/fd", os.O_RDONLY)
    except OSError:
        return -1
    try:
        entries = os.listdir("/dev/fd")
    except OSError:
        return -1
    finally:
        os.close(listing)
    names = {name for name in entries if name.isdigit()}
    # `listing` was closed already; drop it if it still appears in the snapshot.
    names.discard(str(listing))
    return len(names)


def _table_counts(database_path: Path) -> dict[str, dict[str, int]]:
    """Row counts for both queues, so a soak can show queue depth.

    `memory_tasks` is the scheduler queue; `memory_write_jobs` is the durable
    unified-write queue. Counting only the first would report an empty queue
    while durable writes accumulate.
    """
    counts: dict[str, dict[str, int]] = {}
    try:
        # `with sqlite3.connect(...)` only scopes the transaction; it does NOT
        # close the connection. A probe that leaked one fd per sample would
        # itself look like the unbounded growth the soak is meant to rule out.
        connection = sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            # `memory_tasks` uses `status`; the durable write queue uses `state`
            # (it keeps the queue's column names). Pick whichever exists.
            for table in ("memory_tasks", "memory_write_jobs"):
                if table not in tables:
                    continue
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                column = "status" if "status" in columns else "state"
                if column not in columns:
                    continue
                rows = connection.execute(
                    f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}"
                ).fetchall()
                counts[table] = {str(state): int(count) for state, count in rows}
        finally:
            connection.close()
    except sqlite3.Error:
        return {}
    return counts


def _sample(database_path: Path) -> dict[str, object]:
    stats = main_database_stats()
    database = main_database(database_path)
    counts = database.counts() if hasattr(database, "counts") else {}
    handles = _open_handles()
    threads = _threads()
    return {
        "epoch": round(time.time(), 3),
        "database": {
            "open_connections": stats["open_connections"],
            "peak_open_connections": stats["peak_open_connections"],
            # Checkout counters, not just waits: a soak that delegates its load
            # to another process would report zero checkouts here, which is how
            # we prove the load and the sampler share one process.
            "writer_checkouts": stats.get("writer_checkouts", 0),
            "reader_checkouts": stats.get("reader_checkouts", 0),
            "writer_waits": stats["writer_waits"],
            "writer_wait_ms_max": stats["writer_wait_ms_max"],
            "reader_waits": stats["reader_waits"],
            "reader_wait_ms_max": stats["reader_wait_ms_max"],
            "writers_waiting": stats["writers_waiting"],
            "readers_waiting": stats["readers_waiting"],
            "nested_refusals": stats["nested_refusals"],
        },
        "queue": {"memory_tasks": dict(counts), **_table_counts(database_path)},
        "process": {"file_handles": handles, "threads": threads},
        "disk": {
            "database_bytes": database_path.stat().st_size if database_path.exists() else 0,
            "directory_bytes": _directory_bytes(database_path.parent),
        },
    }


def _open_output(path: Path, *, archive_existing: Path | None = None) -> TextIO:
    """Open the evidence stream without ever truncating an existing run.

    A second supervisor starting the same command with ``--out`` used to
    open the file with ``"w"`` and erase an already-complete soak before the
    first sample was written. The safer contract is exclusive creation; a
    caller that intentionally starts a fresh run must first move the old
    evidence to ``--archive-existing`` (or choose a new output path).
    """
    if archive_existing is not None and path.exists():
        if archive_existing.exists():
            raise FileExistsError(f"archive path already exists: {archive_existing}")
        path.replace(archive_existing)
    return cast(TextIO, path.open("x", encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="SQLite database to sample")
    parser.add_argument("--seconds", type=float, default=60.0, help="total duration")
    parser.add_argument("--interval", type=float, default=30.0, help="sample interval")
    parser.add_argument("--out", type=Path, required=True, help="JSONL output path")
    parser.add_argument(
        "--archive-existing",
        type=Path,
        help="move an existing JSONL file here before starting a fresh run",
    )
    parser.add_argument(
        "--load-in-process",
        action="store_true",
        help=(
            "also drive write load in this process, so process-local wait "
            "counters reflect that load instead of reading a quiet sampler"
        ),
    )
    parser.add_argument(
        "--load-every",
        type=float,
        default=5.0,
        help="seconds between in-process load batches (with --load-in-process)",
    )
    parser.add_argument(
        "--load-batch",
        type=int,
        default=4,
        help="Evidence rows per in-process load batch",
    )
    parser.add_argument(
        "--load-readers",
        type=int,
        default=0,
        help=(
            "concurrent reader threads for the in-process load; without them "
            "reader/writer waits are zero by construction"
        ),
    )
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = _open_output(args.out, archive_existing=args.archive_existing)
    except FileExistsError as error:
        print(
            f"soak output/archive already exists: {error}; choose a fresh path",
            file=sys.stderr,
        )
        return 2
    if args.load_in_process:
        _probe_initialize(args.database)
        loader = threading.Thread(
            target=_run_in_process_load,
            kwargs={
                "database_path": args.database,
                "seconds": args.seconds,
                "every": args.load_every,
                "batch": args.load_batch,
                "readers": args.load_readers,
            },
            name="soak-in-process-load",
            daemon=True,
        )
        loader.start()
    end = time.monotonic() + args.seconds
    try:
        with output as stream:
            while time.monotonic() < end:
                stream.write(json.dumps(_sample(args.database), sort_keys=True) + "\n")
                stream.flush()
                time.sleep(max(0.5, args.interval))
    finally:
        if args.load_in_process:
            loader.join(timeout=10)
        close_main_databases()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
