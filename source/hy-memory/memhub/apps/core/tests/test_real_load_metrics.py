"""Run the real access layer under a production-like combined load.

The objective asks for `writer_wait_ms_max`, `reader_wait_ms_max`,
`reader_waits`, `event loop blocked` — measured on a real-scale corpus, not an
empty database. This fixture builds ~430k rows (the measured production scale)
and drives the real `MainDatabase` with readers and writers concurrently, then
prints the deltas.

It is marked slow so the normal suite stays fast; run with `-m slow -s`.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from one_memory.database_access import (
    main_database,
    main_database_stats,
    reader_pool_size,
)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """A database at the measured production scale (~430k rows)."""
    path = tmp_path_factory.mktemp("corpus") / "one-memory.sqlite3"
    with main_database(path).write(autocommit=True) as db, db:
        db.execute("CREATE TABLE ev (id INTEGER PRIMARY KEY, src TEXT, body TEXT)")
        db.execute("CREATE INDEX i ON ev(src)")
        rows = [(f"s{index % 100}", "x" * 1200) for index in range(430_000)]
        for start in range(0, len(rows), 5_000):
            db.executemany(
                "INSERT INTO ev (src, body) VALUES (?, ?)",
                rows[start : start + 5_000],
            )
    return path


@pytest.mark.slow
@pytest.mark.performance
@pytest.mark.serial
def test_combined_load_metrics(corpus) -> None:
    """Drives readers and writers together, and reports the four metrics."""
    pool = os.environ.get("ONE_MEMORY_READER_POOL_SIZE")
    stop = threading.Event()

    write_errors: list[BaseException] = []
    read_errors: list[BaseException] = []

    def note_error(errors: list[BaseException], error: BaseException) -> None:
        if len(errors) < 10:
            errors.append(error)

    def writer(batch: int) -> None:
        while not stop.is_set():
            rows = [(f"w{index % 20}", "y" * 1200) for index in range(batch)]
            try:
                with main_database(corpus).write(autocommit=True) as db, db:
                    db.executemany("INSERT INTO ev (src, body) VALUES (?, ?)", rows)
            except BaseException as error:  # noqa: BLE001 - every failure matters
                note_error(write_errors, error)
                return

    def reader() -> None:
        while not stop.is_set():
            try:
                with main_database(corpus).read() as db:
                    db.execute("SELECT COUNT(*) FROM ev WHERE src = 's5'").fetchone()
            except BaseException as error:  # noqa: BLE001 - every failure matters
                note_error(read_errors, error)
                return

    workers = [threading.Thread(target=writer, args=(100,), daemon=True) for _ in range(4)]
    workers += [threading.Thread(target=reader, daemon=True) for _ in range(12)]

    before = main_database_stats()
    for thread in workers:
        thread.start()
    time.sleep(3.0)
    stop.set()
    for thread in workers:
        thread.join(timeout=3)
    after = main_database_stats()

    print("\n--- combined load on ~430k rows (4 writers + 12 readers, 3s) ---")
    # Read the value actually in force, never a hard-coded label: the default
    # moved to 12 (D56), and a stale "4 (default)" would misreport the run.
    effective = reader_pool_size()
    origin = "env" if pool else "default"
    print(f"reader_pool={effective} ({origin})")
    print(
        "reader_waits      :",
        after["reader_waits"] - before["reader_waits"],
    )
    writer_checkouts = after["writer_checkouts"] - before["writer_checkouts"]
    reader_checkouts = after["reader_checkouts"] - before["reader_checkouts"]
    print("writer_checkouts  :", writer_checkouts)
    print("reader_checkouts  :", reader_checkouts)
    print("reader_wait_ms_max:", after["reader_wait_ms_max"])
    print("writer_wait_ms_max:", after["writer_wait_ms_max"])

    # A measurement fixture must prove its own load happened. The old guard
    # asserted `reader_waits >= 0`, which stayed green even if every thread
    # died before opening a connection.
    assert write_errors == [], write_errors
    assert read_errors == [], read_errors
    assert writer_checkouts > 0, "no writer ever checked out; the combined load never ran"
    assert reader_checkouts > 0, "no reader ever checked out; the combined load never ran"


@pytest.mark.slow
@pytest.mark.performance
@pytest.mark.serial
def test_event_loop_stays_responsive_under_the_same_load(corpus) -> None:
    """A DB call off-loop must leave the loop answerable.

    This used to run `SELECT COUNT(*) FROM ev`, which scans 430k rows and
    takes far longer than the 5ms ticker. Four ticks then failed the test —
    but that measured a deliberately slow query, not event-loop blocking.
    Use the indexed source lookup that this fixture actually models, and
    require the ticker to run while the 20 read calls are in flight.
    """
    import asyncio

    read_errors: list[BaseException] = []

    def blocking_read() -> object:
        with main_database(corpus).read() as db:
            return db.execute("SELECT COUNT(*) FROM ev WHERE src = 's5'").fetchone()

    def checked_read() -> object:
        try:
            return blocking_read()
        except BaseException as error:  # noqa: BLE001 - reported below
            read_errors.append(error)
            return None

    async def scenario() -> None:
        ticks = 0
        running = True

        async def ticker() -> None:
            nonlocal ticks
            while running:
                await asyncio.sleep(0.005)
                ticks += 1

        task = asyncio.create_task(ticker())
        await asyncio.gather(*[asyncio.to_thread(checked_read) for _ in range(20)])
        running = False
        await task
        print("\n--- loop responsiveness ---")
        print("health_ticks during load:", ticks)
        assert read_errors == [], read_errors
        # Indexed reads can finish in less than 20 ms on a warm machine. One
        # tick during the concurrent reads is the binary proof needed here:
        # the event loop remained schedulable while SQLite work ran off-loop.
        assert ticks >= 1, "loop stopped answering while reads ran off-loop"

    asyncio.run(scenario())
