#!/usr/bin/env python
"""Measure short-write transaction cost under the D56 SQLite access layer.

The database decision records the operating rule "short write transactions:
batch 500 -> 459ms, batch 20 -> 47ms; bigger batches are worse". That number
was measured once without a reusable command. This script makes the claim
reproducible on an isolated database:

    .venv/bin/python scripts/measure_short_write_batches.py

It alternates the two batch sizes across repeats so a warm-cache or
first-run advantage cannot decide the result, and it prints both total wall
time and per-row cost. The direction is not baked in: a prior single
measurement found the 500-row batch slower in wall time, while per-row cost
can move the other way when commit latency dominates. Treat this as a probe,
not a universal latency promise.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from one_memory.database_access import close_main_databases, main_database  # noqa: E402


def _rows(batch: int, *, batch_index: int) -> list[tuple[str, str]]:
    prefix = f"{batch}:{batch_index}"
    return [(f"{prefix}:{index}", "x" * 256) for index in range(batch)]


def _warm(database_path: Path, *, rows: int) -> None:
    if rows <= 0:
        return
    payload = ((f"warm:{index}", "w" * 256) for index in range(rows))
    with main_database(database_path).write(autocommit=True) as connection, connection:
        connection.executemany("INSERT INTO short_write_probe VALUES (?,?)", payload)


def _one_write(
    database_path: Path,
    batch: int,
    *,
    batch_index: int,
    sleep_per_commit_ms: float = 0.0,
) -> float:
    payload = _rows(batch, batch_index=batch_index)
    started = time.perf_counter()
    with main_database(database_path).write(autocommit=True) as connection, connection:
        connection.executemany("INSERT INTO short_write_probe VALUES (?,?)", payload)
    if sleep_per_commit_ms:
        time.sleep(sleep_per_commit_ms / 1000)
    return (time.perf_counter() - started) * 1_000


def _measure(
    database_path: Path,
    batch: int,
    *,
    repeats: int,
    sleep_per_commit_ms: float = 0.0,
) -> list[float]:
    return [
        _one_write(
            database_path,
            batch,
            batch_index=index,
            sleep_per_commit_ms=sleep_per_commit_ms,
        )
        for index in range(repeats)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--batch-large", type=int, default=500)
    parser.add_argument("--batch-small", type=int, default=20)
    parser.add_argument(
        "--warm-rows",
        type=int,
        default=50_000,
        help="prefill rows so page-cache/commit behavior resembles a live table",
    )
    parser.add_argument(
        "--sleep-per-commit-ms",
        type=float,
        default=0.0,
        help="positive control: add fixed commit latency to expose the per-row batch effect",
    )
    parser.add_argument(
        "--assert-large-slower",
        action="store_true",
        help=(
            "fail unless the large batch costs more total time "
            "(for reproducing the original machine)"
        ),
    )
    args = parser.parse_args(argv)
    if (
        min(args.repeats, args.batch_large, args.batch_small) < 1
        or args.warm_rows < 0
        or args.sleep_per_commit_ms < 0
    ):
        parser.error("batch sizes and repeats must be positive")

    with tempfile.TemporaryDirectory(prefix="om-short-write-") as raw:
        database_path = Path(raw) / "one-memory.sqlite3"
        with main_database(database_path).write(autocommit=True) as connection, connection:
            connection.execute("CREATE TABLE short_write_probe (id TEXT, body TEXT)")
        _warm(database_path, rows=args.warm_rows)
        print(f"warm_rows={args.warm_rows}")

        # Alternate large and small so neither order gets all the warm cache.
        large: list[float] = []
        small: list[float] = []
        for index in range(args.repeats):
            large.append(
                _one_write(
                    database_path,
                    args.batch_large,
                    batch_index=index,
                    sleep_per_commit_ms=args.sleep_per_commit_ms,
                )
            )
            small.append(
                _one_write(
                    database_path,
                    args.batch_small,
                    batch_index=index,
                    sleep_per_commit_ms=args.sleep_per_commit_ms,
                )
            )

        close_main_databases()

    def report(label: str, samples: list[float], batch: int) -> float:
        p50 = statistics.median(samples)
        print(
            f"{label} batch={batch} p50_ms={p50:.3f} "
            f"per_row_us={p50 * 1000 / batch:.1f} "
            f"samples_ms={','.join(f'{value:.3f}' for value in samples)}"
        )
        return p50

    print(f"repeats={args.repeats}")
    large_total = report("large", large, args.batch_large)
    small_total = report("small", small, args.batch_small)

    ratio = large_total / small_total
    if args.assert_large_slower and large_total <= small_total:
        print(
            f"RESULT: failed - large wall-time ratio={ratio:.2f}; expected >1 on this machine",
            file=sys.stderr,
        )
        return 1
    print(
        f"RESULT: measured - large/small wall-time ratio={ratio:.2f}; "
        "this run does not by itself prove the direction"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
