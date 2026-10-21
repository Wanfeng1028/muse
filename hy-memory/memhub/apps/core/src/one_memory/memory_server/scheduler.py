"""A2-04: scheduling policy for the durable write queue.

The policy is separated from storage on purpose. The claim itself needs MySQL
(`FOR UPDATE SKIP LOCKED`), but the *decision* of what may run next does not,
and it is the part most likely to be wrong in a way tests should catch: two
writes for one session overlapping would interleave a conversation's rounds,
while a single busy session must not starve the others.

So this module is pure. It answers "given what is running and what is waiting,
which jobs may start?" and never touches the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JobRef:
    """The minimum the scheduler needs to know about a queued job."""

    job_id: str
    #: Internal session id. Writes for one session must never overlap.
    internal_session_id: str
    #: Live injections (a user waiting on a prompt) outrank background work.
    priority: str = "normal"
    #: Lower enqueue sequence means older. Used for fairness, not priority.
    sequence: int = 0


@dataclass(frozen=True)
class SchedulerConfig:
    max_concurrent: int = 4
    #: Reserved slots for live work so a background backlog cannot fill them.
    live_reserved: int = 1


@dataclass
class SchedulerState:
    running: list[JobRef] = field(default_factory=list)

    @property
    def running_session_ids(self) -> set[str]:
        return {job.internal_session_id for job in self.running}


def plan_next_batch(
    *,
    waiting: list[JobRef],
    state: SchedulerState,
    config: SchedulerConfig,
) -> list[JobRef]:
    """Choose which waiting jobs may start now.

    Three rules, in order of importance:

    1. A session already running may not start again. Two writes for one
       session could commit in the wrong order and interleave a conversation.
    2. Live work takes priority, and keeps a reserved slot so a full backlog
       of background writes cannot crowd it out.
    3. Among equals, older jobs go first, and each session may only claim one
       slot per round, so one session with a long backlog cannot take over.

    The reservation is a *deferral*, not a permanent hole. It applies only
    while live work still needs a slot in this round: once a live job has been
    started, the reservation is satisfied and background work may use every
    remaining slot. With no live demand at all, background runs full too.
    Holding a slot empty unconditionally would cap throughput below the
    configured limit for no benefit.
    """
    if config.max_concurrent <= 0:
        return []

    free = config.max_concurrent - len(state.running)
    if free <= 0:
        return []

    busy = state.running_session_ids
    ordered = sorted(waiting, key=lambda job: (job.priority != "live", job.sequence))
    live_waiting = [job for job in ordered if job.priority == "live"]

    chosen: list[JobRef] = []
    claimed_sessions: set[str] = set()
    live_started = 0

    for job in ordered:
        if len(chosen) >= free:
            break
        if job.internal_session_id in busy or job.internal_session_id in claimed_sessions:
            continue
        if job.priority == "live":
            chosen.append(job)
            claimed_sessions.add(job.internal_session_id)
            live_started += 1
            continue
        # Hold the reserved slot only for live work that has not started yet.
        pending_live = sum(
            1
            for live in live_waiting
            if live.internal_session_id not in busy
            and live.internal_session_id not in claimed_sessions
        )
        if pending_live > 0 and len(chosen) >= free - config.live_reserved:
            continue
        chosen.append(job)
        claimed_sessions.add(job.internal_session_id)

    return chosen
