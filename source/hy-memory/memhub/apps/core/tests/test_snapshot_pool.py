"""A whole-directory snapshot must not hold a thread everything else is waiting for.

On a cold start Codex, Cursor and WorkBuddy began copying at once — minutes
each — and every other hand-off queued behind them: Claude Code's twenty files
took 5.5 minutes, and the first memory task was created three seconds after
the Codex copy finished. Everything here runs on temporary fixtures.
"""

import asyncio
import inspect
import threading
import time

from one_memory.background_work import in_the_background, shutdown_bulk_pool
from one_memory.imports.runner import ImportRunner
from one_memory.imports.snapshots import SourceSnapshotStore
from tests.test_snapshot_adapter import (
    Fixture,
    cleanup_readonly_fixtures,  # noqa: F401 - autouse, snapshot copies are read-only
)

LONG_COPIES = ("codex", "cursor", "workbuddy")


def test_small_import_and_memory_hand_off_proceed_while_three_long_copies_run(
    tmp_path, monkeypatch
):
    long_copies = {source: Fixture(tmp_path / source, source) for source in LONG_COPIES}
    for fixture in long_copies.values():
        fixture.append("a long history")
    small = Fixture(tmp_path / "claude-code", "claude-code")
    small.append("twenty small files")

    copying: set[str] = set()
    all_copying = threading.Event()
    finish_copying = threading.Event()
    counting = threading.Lock()
    real_capture = SourceSnapshotStore.capture

    def long_copy(store, **kwargs):
        if kwargs["source_id"] in LONG_COPIES:
            with counting:
                copying.add(kwargs["source_id"])
                if len(copying) == len(LONG_COPIES):
                    all_copying.set()
            assert finish_copying.wait(30)
        return real_capture(store, **kwargs)

    monkeypatch.setattr(SourceSnapshotStore, "capture", long_copy)

    async def scenario() -> tuple[bool, bool, int]:
        runs = [
            asyncio.create_task(
                ImportRunner(evidence_store=f.evidence, job_store=f.jobs).run(
                    adapter=f.adapter(), job_id=f.job.job_id
                )
            )
            for f in long_copies.values()
        ]
        small_run = handoff = None
        try:
            assert await asyncio.to_thread(all_copying.wait, 10), "三个长快照没有同时开始"
            handoff = asyncio.create_task(in_the_background(time.perf_counter))
            small_run = asyncio.create_task(
                ImportRunner(evidence_store=small.evidence, job_store=small.jobs).run(
                    adapter=small.adapter(), job_id=small.job.job_id
                )
            )
            handed_off, _ = await asyncio.wait({handoff}, timeout=1.0)
            imported, _ = await asyncio.wait({small_run}, timeout=5.0)
            copies_still_running = sum(not run.done() for run in runs)
        finally:
            # Released either way, so a red run ends instead of hanging on them.
            finish_copying.set()
            await asyncio.gather(
                *runs, *(task for task in (small_run, handoff) if task), return_exceptions=True
            )
        return handoff in handed_off, small_run in imported, copies_still_running

    try:
        handed_off, imported, copies_still_running = asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()

    assert copies_still_running == len(LONG_COPIES), "长快照提前结束，场景没有测到占用"
    assert handed_off, "三个长快照复制期间，一次后台交接 1 秒内没被执行"
    assert imported, "三个长快照复制期间，小来源导入 5 秒内没完成"
    assert small.evidence.count() == 1
    assert all(f.evidence.count() == 1 for f in long_copies.values())


def test_every_import_the_supervisor_runs_at_once_can_be_copying():
    """A narrower snapshot pool puts a small source's copy behind a long one."""
    from one_memory.background_work import SNAPSHOT_WORKERS
    from one_memory.imports.supervisor import ImportSupervisor

    at_once = inspect.signature(ImportSupervisor).parameters["max_concurrent_jobs"].default
    assert at_once <= SNAPSHOT_WORKERS
