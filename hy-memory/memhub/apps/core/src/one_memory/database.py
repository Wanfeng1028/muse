"""What every connection to the one database has to agree on."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager

# One file, several stores, and writers that meet by design: the catch-up on
# old conversations records tasks while the runner works through them, live
# sync imports while the interface reads. SQLite fails the second writer
# outright unless it is told to wait, and on a real corpus that failure was
# reached — the catch-up stopped partway with "database is locked", taking the
# memories it had not recorded yet with it.
#
# Long enough that no single statement here should ever reach it, short enough
# to surface a genuine deadlock rather than hang.
WRITE_LOCK_WAIT_MS = 5_000


def take_the_write_lock_first(connection: sqlite3.Connection) -> None:
    """Begin the transaction as a writer, before anything has been read.

    The other contention `busy_timeout` does not cover. Most writes here
    check something first — whose job this is, what version that memory is on
    — and a connection that has read holds a snapshot. Asked to write after
    someone else has committed, SQLite refuses at once instead of waiting,
    because waiting could only deadlock: neither writer can give up what it
    has already read.

    While every write was made on the event loop this was unreachable, the
    loop having only ever made one at a time. Made in threads so the app
    stays answerable, two of them do meet: importing two sources at once
    failed a job partway with `database is locked`, its evidence written and
    its place in the file lost. Taking the write lock up front turns that
    refusal back into the wait `busy_timeout` is there for.
    """
    connection.autocommit = sqlite3.LEGACY_TRANSACTION_CONTROL
    connection.isolation_level = "IMMEDIATE"
    connection.execute("BEGIN IMMEDIATE")


@contextmanager
def closed_after(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """`with connection:` — commit or roll back — and then close it.

    Leaving a connection to go out of scope does not close it: its statement
    cache refers back to it, so only the cyclic collector frees it, and in the
    core's large heap that collector rarely runs. The interface's polling
    alone once held 61,000 connections open, the per-process file limit, and
    every later open failed.
    """
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def enable_write_ahead_log(
    connection: sqlite3.Connection, *, wait_ms: int = WRITE_LOCK_WAIT_MS
) -> None:
    """Switch the file to WAL, waiting out anyone else opening it.

    `busy_timeout` covers ordinary contention but not this one: changing the
    journal mode needs a moment with the file to itself, and SQLite refuses
    outright instead of waiting. Two Cores opening a fresh database at the
    same instant — which is what a restart racing a not-quite-dead
    predecessor looks like — met that refusal, and the newcomer failed to
    start at all.
    """
    deadline = time.monotonic() + wait_ms / 1_000
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)
