"""Rule 8: a lease must outlive the work it covers, and be renewed while it runs.

hy memory app's failure (§三 反模式 6) was a lock TTL *shorter* than the outer
timeout (330 < 360): the lock lapsed while the work was still going, so a
second drain picked the same job up and wrote it twice. Their fix has two
halves, and both are about us too:

- the lease must be longer than the ceiling on the work it guards;
- while the work is running, the lease is extended, because "long enough" is
  a guess about someone else's machine.

The second half is the one that actually holds in production. A timeout is a
budget, not a promise: a slow disk or a wedged model can keep a job past it,
and `hy_invoked` has already been recorded, so a lapsed lease sends the job to
`unknown` — permanently unwritten, on a job that may well have succeeded.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from one_memory.memory_server.queue import (
    DEFAULT_LEASE,
    RENEW_LEASE_SQL,
    ClaimedJob,
    QueueRoles,
    WriteQueuePipelines,
    lease_covers,
)
from tests.test_memory_server_queue import FakeDatabase


def _job(job_id: str = "job-1", owner: str = "claimer-0") -> ClaimedJob:
    return ClaimedJob(
        job_id=job_id,
        session_key="session-1",
        batch_id="batch-1",
        idempotency_key="idem-1",
        payload_json="{}",
        attempts=1,
        owner=owner,
    )


def test_a_lease_shorter_than_the_work_ceiling_is_refused() -> None:
    """The relation hy got backwards, made executable.

    A job allowed to run for 300s under a 120s lease can be reclaimed while
    it is still running, which is how one write becomes two.
    """
    assert lease_covers(DEFAULT_LEASE, timedelta(seconds=300)) is False
    assert lease_covers(timedelta(seconds=360), timedelta(seconds=300)) is True


def test_renewal_sql_only_extends_the_lease_the_owner_holds() -> None:
    """A renewal must not resurrect a lease someone else now owns.

    Without the owner and state guards, a job reclaimed after its lease
    lapsed would be re-leased by the old owner still grinding away on it.
    """
    assert "lease_owner = %s" in RENEW_LEASE_SQL
    assert "state = 'running'" in RENEW_LEASE_SQL
    assert "lease_expires_at = DATE_ADD(NOW(6), INTERVAL %s SECOND)" in RENEW_LEASE_SQL


def test_a_running_job_renews_its_lease_while_it_is_still_executing() -> None:
    """The half that holds in production: extend, don't just guess long.

    The job outlives one renewal interval, so a queue that never renewed
    would let the lease lapse mid-execution and hand the job to `unknown`
    — a write that may have succeeded, recorded as permanently lost.
    """
    release = asyncio.Event()

    async def execute(job: ClaimedJob) -> None:
        await release.wait()

    database = FakeDatabase([])

    async def run() -> None:
        pipelines = WriteQueuePipelines(
            database,  # type: ignore[arg-type]
            execute=execute,
            roles=QueueRoles(claimers=1, executors=1),
            lease=timedelta(seconds=0.2),
            renew_every=timedelta(seconds=0.05),
        )
        await pipelines.start()
        try:
            await pipelines._handoff.put(_job(owner="claimer-0"))  # noqa: SLF001
            await asyncio.sleep(0.25)
        finally:
            release.set()
            await pipelines.stop()

    asyncio.run(run())
    # Observed through the statements the real code issued, not a hook: a
    # renewal the production path never sends would not show up here.
    renewals = [
        params
        for sql, params in database.cursor.statements
        if sql.strip().startswith("UPDATE memory_write_jobs")
        and "lease_expires_at = DATE_ADD" in sql
    ]
    assert renewals, "a job that ran past one interval renewed nothing"
    # Each renewal extends by the lease, and names the owner holding it.
    assert all(params[0] == 0 or params[0] == 1 for params in renewals)
    assert {params[2] for params in renewals} == {"claimer-0"}


def test_renewal_stops_when_the_job_finishes() -> None:
    """A renewal task that outlives its job would keep extending a dead lease."""

    renewed_after_finish: list[bool] = []

    async def execute(job: ClaimedJob) -> None:
        return None

    async def run() -> None:
        database = FakeDatabase([])
        pipelines = WriteQueuePipelines(
            database,  # type: ignore[arg-type]
            execute=execute,
            roles=QueueRoles(claimers=1, executors=1),
            lease=timedelta(seconds=5),
            renew_every=timedelta(seconds=0.05),
        )
        await pipelines.start()
        try:
            await pipelines._handoff.put(_job())  # noqa: SLF001
            await asyncio.sleep(0.25)
            # The job is long done by now. Wait out another renewal interval
            # and see whether anything is still being extended: a leaked
            # renewal task keeps a finished job looking live, which holds off
            # reclaim forever.
            after = len(
                [
                    sql
                    for sql, _ in database.cursor.statements
                    if "lease_expires_at = DATE_ADD" in sql
                ]
            )
            await asyncio.sleep(0.15)
            later = len(
                [
                    sql
                    for sql, _ in database.cursor.statements
                    if "lease_expires_at = DATE_ADD" in sql
                ]
            )
            renewed_after_finish.append(later > after)
        finally:
            await pipelines.stop()
        assert pipelines._renewal_tasks == []  # noqa: SLF001

    asyncio.run(run())
    assert renewed_after_finish == [False], "the lease kept being extended after the job ended"
