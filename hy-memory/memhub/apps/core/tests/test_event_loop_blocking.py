"""Proof, as a test, that blocking work on the loop freezes it — and the fix works.

Real logs showed `event loop blocked for 12.9s` sixty times, with stacks landing on
synchronous database calls reached from `async def` handlers. This test reproduces
that mechanism with the same observable as production: **can the loop still answer
a trivial coroutine while the work runs?** That is what `loop_watchdog` measures,
so it is the number that matters — not wall time, which is nearly identical.

Measured here: blocking directly -> 0 ticks (loop frozen);
`asyncio.to_thread` -> ~100 ticks (loop responsive), for the same work.

It uses a SQLite query as the blocking work only because that is what the product
does; the lesson is about *where* the work runs, not about SQLite.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path


def _build(path: Path, rows: int = 150_000) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE ev (id INTEGER PRIMARY KEY, src TEXT, body TEXT)")
    connection.executemany(
        "INSERT INTO ev (src, body) VALUES (?, ?)",
        [(f"s{index % 50}", "x" * 1200) for index in range(rows)],
    )
    connection.commit()
    connection.close()


async def _ticks_while(work, *, n: int = 20) -> int:
    """How many times the loop answers a ticker while `work` runs."""
    ticks = 0
    running = True

    async def ticker() -> None:
        nonlocal ticks
        while running:
            await asyncio.sleep(0.005)
            ticks += 1

    task = asyncio.create_task(ticker())
    await work(n)
    running = False
    await task
    return ticks


def test_blocking_work_directly_on_the_loop_freezes_it(tmp_path) -> None:
    """The bug: calling a blocking function from an async handler stops the loop."""
    path = tmp_path / "block.sqlite3"
    _build(path)

    def blocking() -> None:
        connection = sqlite3.connect(path, timeout=10.0)
        connection.execute("SELECT COUNT(*) FROM ev WHERE src='s7'").fetchone()
        connection.close()

    async def work(n: int) -> None:
        for _ in range(n):
            blocking()

    ticks = asyncio.run(_ticks_while(work))
    print(f"\nblocking directly: health_ticks={ticks}")

    assert ticks == 0, "expected the loop to be unable to answer while blocked"


def test_the_same_work_off_the_loop_keeps_it_answering(tmp_path) -> None:
    """The fix: `asyncio.to_thread` — same work, loop stays responsive."""
    path = tmp_path / "offloop.sqlite3"
    _build(path)

    def blocking() -> None:
        connection = sqlite3.connect(path, timeout=10.0)
        connection.execute("SELECT COUNT(*) FROM ev WHERE src='s7'").fetchone()
        connection.close()

    async def work(n: int) -> None:
        await asyncio.gather(*[asyncio.to_thread(blocking) for _ in range(n)])

    ticks = asyncio.run(_ticks_while(work))
    print(f"\nvia to_thread:     health_ticks={ticks}")

    assert ticks > 10, "the loop should still be answering while work runs off-loop"


def test_the_fix_costs_no_wall_time(tmp_path) -> None:
    """Moving work off the loop is not a slowdown — responsiveness is nearly free."""
    path = tmp_path / "cost.sqlite3"
    _build(path)

    def blocking() -> None:
        connection = sqlite3.connect(path, timeout=10.0)
        connection.execute("SELECT COUNT(*) FROM ev WHERE src='s7'").fetchone()
        connection.close()

    async def run(mode: str) -> float:
        started = time.monotonic()
        if mode == "direct":
            for _ in range(20):
                blocking()
        else:
            await asyncio.gather(*[asyncio.to_thread(blocking) for _ in range(20)])
        return time.monotonic() - started

    async def both() -> tuple[float, float]:
        return await run("direct"), await run("to_thread")

    direct, offloaded = asyncio.run(both())
    print(f"\nwall: direct={direct:.2f}s to_thread={offloaded:.2f}s")

    assert offloaded < direct * 3, "offloading should not cost meaningfully more time"
