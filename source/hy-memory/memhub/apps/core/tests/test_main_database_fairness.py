"""Waiting for the one database has to be a queue, not a scramble.

A 54-minute catch-up over the user's own corpus died with `database is
locked`. Nothing was locked: the safe stack ends at `database_access.write`,
which is our own admission timing out after five seconds and raising SQLite's
message by hand. Only one write connection exists in a process and a mutex
guards it, so SQLite's writer lock is never contended here — every refusal of
that name is this layer's own.

Admission used `Condition.wait_for` with `notify_all`: each release woke
everyone and let them race, so an arrival could step in front of someone who
had waited all along, again and again, until that caller's budget ran out.
The tests below pin the queue down: served in arrival order, and never passed
over by a stream of callers none of whom hold it for long.
"""

import asyncio
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from one_memory.background_work import in_the_background, shutdown_bulk_pool
from one_memory.database_access import main_database, reader_pool_size
from one_memory.service_levels import ServiceLevel, ServiceLevelScheduler, ServiceResource

# Far below the five-second budget, so a caller that still runs out of it was
# passed over rather than kept waiting by any one holder.
BRIEF_HOLD_SECONDS = 0.02
WRITE_CONTENDERS = 8
UNDER_LOAD_SECONDS = 8.0

# There is no matching starvation test for readers, and that is a finding
# rather than an omission. The same scramble governs the read pool, but it
# hands out four connections rather than one, so a place comes free every few
# milliseconds and a waiting caller takes one long before its budget is out:
# with brief holders it was tried at eight, sixteen and sixty-four contenders
# and never once refused. A reader that does run out of budget — the catch-up
# over Cursor's corpus died that way — was kept waiting by holders that were
# slow, not by ones that pushed in. Ordering is still pinned below, because it
# is what puts a ceiling on the wait; the holds themselves are another matter.


@pytest.fixture
def database(tmp_path: Path):
    access = main_database(tmp_path / "one-memory.sqlite3")
    with access.write() as connection:
        connection.execute("CREATE TABLE t (v INTEGER)")
    yield access
    access.close()


class _Contest:
    """A stream of brief holders, and one caller trying to get a turn."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.turns_taken = 0
        self.locked_out = 0
        self.longest_wait_ms = 0.0
        self._count = threading.Lock()

    def took_a_turn(self) -> None:
        with self._count:
            self.turns_taken += 1

    def waited(self, milliseconds: float, *, locked: bool) -> None:
        with self._count:
            self.longest_wait_ms = max(self.longest_wait_ms, milliseconds)
            if locked:
                self.locked_out += 1

    def run(self, contender, latecomer, *, contenders: int) -> None:
        threads = [
            threading.Thread(target=contender, args=(self,), daemon=True) for _ in range(contenders)
        ]
        threads.append(threading.Thread(target=latecomer, args=(self,), daemon=True))
        for thread in threads:
            thread.start()
        time.sleep(UNDER_LOAD_SECONDS)
        self.stop.set()
        for thread in threads:
            thread.join(timeout=30)


def _write_briefly(access, contest: _Contest) -> None:
    while not contest.stop.is_set():
        try:
            with access.write() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("INSERT INTO t VALUES (1)")
                time.sleep(BRIEF_HOLD_SECONDS)
                connection.execute("COMMIT")
            contest.took_a_turn()
        except sqlite3.OperationalError:
            pass


def _ask_for_a_turn(checkout, contest: _Contest) -> None:
    while not contest.stop.is_set():
        started = time.monotonic()
        try:
            with checkout() as connection:
                connection.execute("SELECT count(*) FROM t").fetchone()
            contest.waited((time.monotonic() - started) * 1_000, locked=False)
        except sqlite3.OperationalError:
            contest.waited((time.monotonic() - started) * 1_000, locked=True)
        time.sleep(0.001)


def test_a_stream_of_brief_writers_never_locks_out_the_one_that_waits(database) -> None:
    contest = _Contest()
    contest.run(
        lambda c: _write_briefly(database, c),
        lambda c: _ask_for_a_turn(database.write, c),
        contenders=WRITE_CONTENDERS,
    )

    # The positive control's other half: the connection was free and being
    # handed out throughout, and nobody held it for even a fortieth of the
    # budget. A caller that ran out of budget here was passed over.
    assert contest.turns_taken > 100, (
        "the contenders never got going, so this run says nothing about fairness"
    )
    assert contest.locked_out == 0, (
        f"a caller waiting for the write connection was refused "
        f"{contest.locked_out} times with 'database is locked' while "
        f"{contest.turns_taken} arrivals that came later were served, none of "
        f"them holding it longer than {BRIEF_HOLD_SECONDS * 1000:.0f}ms"
    )


def _queue_up(access, checkout, waiting_now, expected: int) -> list[int]:
    """Start callers one at a time, each in the queue before the next asks."""
    served: list[int] = []
    order = threading.Lock()
    threads = []
    for position in range(expected):

        def wait_for_a_turn(position: int = position) -> None:
            with checkout() as connection:
                with order:
                    served.append(position)
                connection.execute("SELECT count(*) FROM t").fetchone()

        thread = threading.Thread(target=wait_for_a_turn, daemon=True)
        thread.start()
        threads.append(thread)
        # Deterministic: the next caller does not ask until this one is
        # counted as waiting, so arrival order is the loop's order and no
        # sleep is guessing at it.
        deadline = time.monotonic() + 10
        while waiting_now(access) < position + 1:
            if time.monotonic() > deadline:
                raise AssertionError(f"caller {position} never reached the queue")
            time.sleep(0.001)
    return served, threads


def _writers_waiting(access) -> int:
    return access.stats().writers_waiting


def _readers_waiting(access) -> int:
    return access.stats().readers_waiting


def test_writers_are_served_in_the_order_they_arrived(database) -> None:
    started = threading.Event()
    release = threading.Event()

    def hold_it() -> None:
        with database.write():
            started.set()
            release.wait(30)

    holder = threading.Thread(target=hold_it, daemon=True)
    holder.start()
    assert started.wait(10)

    served, threads = _queue_up(database, database.write, _writers_waiting, 6)
    release.set()
    for thread in threads:
        thread.join(timeout=30)
    holder.join(timeout=30)

    assert served == sorted(served), (
        f"the write connection went to callers in the order {served} rather "
        "than the order they asked in; whoever arrives during a handover can "
        "step in front of someone already waiting"
    )


def test_readers_are_served_in_the_order_they_arrived(database) -> None:
    started = threading.Event()
    release = threading.Event()
    holders = []

    def hold_one() -> None:
        with database.read():
            holders.append(1)
            if len(holders) == reader_pool_size():
                started.set()
            release.wait(30)

    pool = [threading.Thread(target=hold_one, daemon=True) for _ in range(reader_pool_size())]
    for thread in pool:
        thread.start()
    assert started.wait(10)

    served, threads = _queue_up(database, database.read, _readers_waiting, 6)
    release.set()
    for thread in threads + pool:
        thread.join(timeout=30)

    assert served == sorted(served), (
        f"read connections went to callers in the order {served} rather than "
        "the order they asked in"
    )


def test_a_checkout_that_ran_out_of_its_budget_is_counted_as_a_wait(database) -> None:
    started = threading.Event()
    release = threading.Event()

    def hold_it() -> None:
        with database.write():
            started.set()
            release.wait(30)

    holder = threading.Thread(target=hold_it, daemon=True)
    holder.start()
    assert started.wait(10)

    before = database.stats()
    with pytest.raises(sqlite3.OperationalError), database.write(busy_timeout_ms=200):
        pass
    after = database.stats()

    release.set()
    holder.join(timeout=30)

    # Waits were only ever recorded once a caller got in, so the ones that ran
    # out of budget — the only ones that cost a user anything — were missing
    # from the log, and the reported maximum could never reach the budget.
    assert after.writer_waits == before.writer_waits + 1, (
        "a caller that waited its whole budget and was refused was not counted "
        "as having waited at all"
    )
    assert after.writer_wait_ms_max >= 200, (
        f"the longest write wait is reported as {after.writer_wait_ms_max:.0f}ms, "
        "which leaves out the caller that waited 200ms and was refused"
    )


def test_realtime_writer_is_admitted_before_an_older_background_waiter(database) -> None:
    holder_started = threading.Event()
    release_holder = threading.Event()
    served: list[str] = []

    def hold_writer() -> None:
        with database.write():
            holder_started.set()
            release_holder.wait(10)

    def write(label: str) -> None:
        with database.write():
            served.append(label)

    holder = threading.Thread(target=hold_writer, daemon=True)
    holder.start()
    assert holder_started.wait(5)

    async def scenario() -> None:
        scheduler = ServiceLevelScheduler()
        async with scheduler.admit(
            ServiceResource.MODEL,
            ServiceLevel.BACKGROUND,
            work_id="background-write",
        ):
            background = asyncio.create_task(in_the_background(write, "background"))
        while database.stats().writers_waiting < 1:
            await asyncio.sleep(0.001)
        async with scheduler.admit(
            ServiceResource.MODEL,
            ServiceLevel.REALTIME,
            work_id="realtime-write",
        ):
            realtime = asyncio.create_task(in_the_background(write, "realtime"))
        while database.stats().writers_waiting < 2:
            await asyncio.sleep(0.001)
        release_holder.set()
        await asyncio.gather(realtime, background)

    try:
        asyncio.run(scenario())
    finally:
        release_holder.set()
        holder.join(timeout=10)
        shutdown_bulk_pool()

    assert served == ["realtime", "background"]
