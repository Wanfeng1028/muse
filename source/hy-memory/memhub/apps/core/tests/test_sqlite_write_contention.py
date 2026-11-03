"""Measure whether SQLite's single writer actually blocks us.

Why this file exists: the MySQL migration is justified by "SQLite's global
single writer becomes the bottleneck". That is plausible but it has never been
measured. A decision worth dozens of hours of migration work should rest on a
number, not on an intuition — especially when WAL already lets readers run
alongside the writer.

These are measurement tests, not pass/fail assertions about correctness: they
print the figures and assert only the invariants that must hold for the
measurement to mean anything (no lost writes, no cross-thread corruption).
Run with `-s` to see the numbers.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from one_memory.database_access import main_database, main_database_stats

pytestmark = [pytest.mark.performance, pytest.mark.serial]


def _create(path: Path) -> None:
    with main_database(path).write(autocommit=True) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS counter (id INTEGER PRIMARY KEY, n INTEGER)")
        db.execute("INSERT OR REPLACE INTO counter VALUES (1, 0)")


def test_single_writer_throughput_and_wait(tmp_path) -> None:
    """N threads each doing M small write transactions.

    Reports total wall time and, crucially, `writer_waits` / `writer_wait_ms_max`
    from the store's own instrumentation: how often a writer had to queue, and
    how long the unluckiest one waited.
    """
    path = tmp_path / "contend.sqlite3"
    _create(path)

    threads_n = 8
    per_thread = 25

    def worker() -> None:
        for _ in range(per_thread):
            with main_database(path).write(autocommit=True) as db, db:
                db.execute("UPDATE counter SET n = n + 1 WHERE id = 1")

    started = time.monotonic()
    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.monotonic() - started

    total = threads_n * per_thread
    with main_database(path).read() as db:
        final = db.execute("SELECT n FROM counter WHERE id = 1").fetchone()[0]

    stats = main_database_stats()
    print("\n--- SQLite single-writer measurement ---")
    print(f"threads={threads_n} writes_each={per_thread} total_writes={total}")
    print(f"wall_seconds={elapsed:.3f}  writes/sec={total / elapsed:.0f}")
    print(f"writer_waits={stats.get('writer_waits')}")
    print(f"writer_wait_ms_total={stats.get('writer_wait_ms_total')}")
    print(f"writer_wait_ms_max={stats.get('writer_wait_ms_max')}")
    print(f"reader_waits={stats.get('reader_waits')}")

    # The measurement is only meaningful if nothing was lost.
    assert final == total, f"lost writes: {final} != {total}"


def test_readers_do_not_block_behind_the_writer(tmp_path) -> None:
    """WAL's promise: reads proceed while a write transaction is open.

    If this is slow, the "readers are blocked too" concern is real. If it is
    fast, the remaining problem is writes only.
    """
    path = tmp_path / "wal.sqlite3"
    _create(path)

    stop = threading.Event()

    def writer() -> None:
        while not stop.is_set():
            with main_database(path).write(autocommit=True) as db, db:
                db.execute("UPDATE counter SET n = n + 1 WHERE id = 1")
            time.sleep(0.001)

    writer_thread = threading.Thread(target=writer, daemon=True)
    writer_thread.start()

    reads = 0
    started = time.monotonic()
    while time.monotonic() - started < 0.5:
        with main_database(path).read() as db:
            db.execute("SELECT n FROM counter WHERE id = 1").fetchone()
        reads += 1
    stop.set()
    writer_thread.join(timeout=2)

    print("\n--- WAL read-under-write ---")
    print(f"reads_in_0.5s={reads}  reads/sec={reads / 0.5:.0f}")

    assert reads > 0


def test_a_long_write_transaction_stalls_other_writers(tmp_path) -> None:
    """The actual risk, stated plainly.

    One slow write transaction holds the single writer; everyone else queues.
    This measures how bad that gets, which is what tuning (shorter transactions,
    bigger batches) has to fix regardless of engine.
    """
    path = tmp_path / "stall.sqlite3"
    _create(path)

    hold = threading.Event()
    done = threading.Event()

    def holder() -> None:
        with main_database(path).write(autocommit=True) as db, db:
            db.execute("UPDATE counter SET n = n + 1 WHERE id = 1")
            hold.wait(timeout=1.0)
        done.set()

    thread = threading.Thread(target=holder)
    thread.start()
    # Give the holder time to take the write connection.
    time.sleep(0.05)

    started = time.monotonic()
    with main_database(path).write(autocommit=True) as db, db:
        db.execute("UPDATE counter SET n = n + 1 WHERE id = 1")
    waited = time.monotonic() - started

    hold.set()
    done.wait(timeout=2)
    thread.join(timeout=2)

    print("\n--- long write stalls others ---")
    print(f"second_writer_waited_seconds={waited:.3f}")

    assert waited >= 0.0


@contextmanager
def _pool_size(size: str):
    """Set the reader pool size for the block, then restore it.

    Deliberately does NOT `importlib.reload` the module: reloading swaps the
    module object and silently detaches `monkeypatch` patches in other tests —
    that broke `test_library_upgrade`. The size is read at use time, so setting
    the environment is enough.
    """
    original = os.environ.get("ONE_MEMORY_READER_POOL_SIZE")
    os.environ["ONE_MEMORY_READER_POOL_SIZE"] = size
    try:
        yield
    finally:
        if original is None:
            os.environ.pop("ONE_MEMORY_READER_POOL_SIZE", None)
        else:
            os.environ["ONE_MEMORY_READER_POOL_SIZE"] = original


def test_reader_pool_capacity_is_tunable() -> None:
    """Read capacity must be adjustable without editing code.

    Production measured `readers_waiting` up to 20 and `reader_wait_ms_max` at
    18 seconds with a pool of 4 — reads were queueing behind *each other*, not
    behind the writer. Tuning that has to be possible from configuration.
    """
    from one_memory.database_access import reader_pool_size

    with _pool_size("16"):
        assert reader_pool_size() == 16
    assert reader_pool_size() == 12, "the default is restored afterwards"


def test_a_wider_reader_pool_reduces_reader_waits(tmp_path) -> None:
    """Measure the effect of widening the pool, rather than assuming it helps.

    If reader waits do not fall, the pool was not the constraint and the fix
    belongs elsewhere — which is exactly what this number is for.
    """
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "pool.sqlite3"
    with main_database(path).write(autocommit=True) as db, db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, n INTEGER)")
        db.execute("INSERT INTO t VALUES (1, 0)")

    def read_once(_: int) -> None:
        with main_database(path).read() as db:
            db.execute("SELECT n FROM t WHERE id = 1").fetchone()

    def run(concurrency: int) -> dict:
        # `main_database_stats()` is cumulative for the process, so the figure
        # that matters is the DELTA across the run. Reading the totals directly
        # once made a wider pool look perfect simply because an earlier
        # module reload had reset the counters — a false green.
        before = main_database_stats()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(read_once, range(concurrency * 20)))
        after = main_database_stats()
        return {
            "reader_waits": after["reader_waits"] - before["reader_waits"],
            "reader_wait_ms_max": after["reader_wait_ms_max"],
        }

    original = os.environ.get("ONE_MEMORY_READER_POOL_SIZE")
    try:
        with _pool_size("4"):
            narrow = run(12)
        with _pool_size("12"):
            wide = run(12)

        print("\n--- reader pool width (12 concurrent readers) ---")
        print(
            f"pool=4   reader_waits={narrow['reader_waits']} max={narrow['reader_wait_ms_max']}ms"
        )
        print(f"pool=12  reader_waits={wide['reader_waits']} max={wide['reader_wait_ms_max']}ms")

        assert wide["reader_waits"] <= narrow["reader_waits"], (
            "a wider pool must not increase reader waits"
        )
    finally:
        if original is None:
            os.environ.pop("ONE_MEMORY_READER_POOL_SIZE", None)
        else:
            os.environ["ONE_MEMORY_READER_POOL_SIZE"] = original


def test_write_batching_beats_many_small_transactions(tmp_path) -> None:
    """One batched transaction instead of one per row, for the same row count.

    This is the write-side half of the tuning. The number that matters is wall
    time for equal work: holding the single writer once for 500 rows instead of
    500 times is what removes the queueing measured in production.
    """
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "batch.sqlite3"
    rows_each = 2000

    def per_row() -> None:
        connection = sqlite3.connect(path, timeout=30.0)
        for _ in range(rows_each):
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO ev (src, body) VALUES (?, ?)", ("a", "y" * 400))
            connection.commit()
        connection.close()

    def batched(size: int) -> None:
        connection = sqlite3.connect(path, timeout=30.0)
        done = 0
        while done < rows_each:
            chunk = min(size, rows_each - done)
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "INSERT INTO ev (src, body) VALUES (?, ?)",
                [("b", "z" * 400)] * chunk,
            )
            connection.commit()
            done += chunk
        connection.close()

    def run(fn) -> float:
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: fn(), range(4)))
        return time.monotonic() - started

    with main_database(path).write(autocommit=True) as db, db:
        db.execute("CREATE TABLE ev (id INTEGER PRIMARY KEY, src TEXT, body TEXT)")

    slow = run(per_row)
    fast = run(lambda: batched(500))

    print("\n--- write batching (4 workers x 2000 rows) ---")
    print(f"per-row txn : {slow:.2f}s")
    print(f"batch=500   : {fast:.2f}s  -> {slow / max(fast, 1e-9):.1f}x faster")

    assert fast < slow, "batching must be faster for the same number of rows"
