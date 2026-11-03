"""Sedimentation runs several harnesses at once, but one harness at a time.

Extraction was serial: `max_concurrent_tasks` defaulted to 1 and nothing ever
passed anything else, so the queue on the user's machine stood at 1,440 with
one task in flight and the scheduler logging `queue_saturated`. Meanwhile the
model profile has carried a `max_concurrency` of 4 all along, copied into
every task's snapshot and never once consulted by the scheduler.

Turning the number up on its own would be wrong. HY decides whether a new
memory supersedes an older one by what it has already been told, so two
extractions from the same harness running at once can each conclude without
knowing about the other. Harnesses run side by side up to the profile's limit.
"""

import asyncio
import sqlite3
import threading
import time

import pytest

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.memory_processing import MemoryProcessingSupervisor
from one_memory.memory_tasks import MemoryTaskStatus
from one_memory.model_profiles import ModelCapabilities, ModelProfilePatch
from tests.test_memory_processing import FakeBridge, _put, _runner, _setup

#: Long enough that an overlap is unmistakable, short enough to stay a unit test.
MODEL_SECONDS = 0.25


class WatchedBridge(FakeBridge):
    """A model that takes a moment, and says who was inside it when.

    Overlap is recorded rather than inferred from timings: every call notes
    which conversations were already in the model when it arrived.
    """

    def __init__(self, seconds: float = MODEL_SECONDS) -> None:
        super().__init__(outputs=())
        self.seconds = seconds
        self.inside: set[str] = set()
        self.peak = 0
        self.overlaps: list[tuple[str, ...]] = []
        self.same_conversation_overlaps: list[str] = []
        self._guard = threading.Lock()

    async def _spend_a_moment(self, request) -> None:
        conversation = getattr(request, "session_id", None) or "?"
        with self._guard:
            if self.inside:
                self.overlaps.append(tuple(sorted(self.inside)))
            if conversation in self.inside:
                self.same_conversation_overlaps.append(conversation)
            self.inside.add(conversation)
            self.peak = max(self.peak, len(self.inside))
        try:
            await asyncio.sleep(self.seconds)
        finally:
            with self._guard:
                self.inside.discard(conversation)

    async def ingest(self, request):
        await self._spend_a_moment(request)
        return await super().ingest(request)

    async def ingest_extracted(self, request, contents):
        await self._spend_a_moment(request)
        return await super().ingest_extracted(request, contents)


def _conversations(
    evidence,
    *,
    count: int,
    turns: int = 1,
    sources: tuple[str, ...] = ("cursor",),
) -> None:
    for conversation in range(count):
        source = sources[conversation % len(sources)]
        for turn in range(turns):
            evidence.put(
                EvidenceInput(
                    source_id=source,
                    message_id=f"c{conversation}-t{turn}",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim=f"第 {conversation} 段对话的第 {turn} 句。",
                    conversation_id=f"conversation-{conversation}",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
            evidence.put(
                EvidenceInput(
                    source_id=source,
                    message_id=f"c{conversation}-t{turn}-answer",
                    role="assistant",
                    written_by=WrittenBy.AGENT,
                    verbatim=f"第 {conversation} 段对话第 {turn} 句的回复。",
                    conversation_id=f"conversation-{conversation}",
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )


async def _drain(supervisor, tasks, *, expected: int, timeout: float = 60.0) -> float:
    started = time.monotonic()
    supervisor.backfill()
    deadline = started + timeout
    while time.monotonic() < deadline:
        recorded = tasks.list()
        if len(recorded) >= expected and all(
            task.status is MemoryTaskStatus.COMPLETED for task in recorded
        ):
            break
        await asyncio.sleep(0.01)
    else:  # pragma: no cover - only on a real stall
        unfinished = [
            (t.task_id, str(t.status))
            for t in tasks.list()
            if t.status is not MemoryTaskStatus.COMPLETED
        ]
        await supervisor.shutdown()
        raise AssertionError(
            f"{expected} expected, {len(tasks.list())} recorded, still unfinished after "
            f"{timeout}s: {unfinished}. A drain that gives up quietly would let every "
            "measurement below be taken off a run that never finished."
        )
    elapsed = time.monotonic() - started
    await supervisor.shutdown()
    return elapsed


def _supervise(tmp_path, stores, bridge, **kwargs):
    evidence, profiles, tasks, governance, secrets, _profile = stores
    return MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=governance,
        data_dir=tmp_path,
        runner_factory=lambda: _runner(tmp_path, stores, bridge),
        **kwargs,
    )


def test_two_turns_of_one_conversation_are_never_in_the_model_together(tmp_path) -> None:
    """HY cannot tell what supersedes what if it is told both at once."""
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    for turn in range(4):
        _put(
            evidence,
            message_id=f"same-{turn}",
            role="user",
            written_by=WrittenBy.PERSON,
            content=f"同一段对话的第 {turn} 句，说的是同一件事的不同版本。",
            conversation_id="the-one-conversation",
        )
    bridge = WatchedBridge()

    async def exercise() -> None:
        # Four workers on purpose: with room to overlap, only the scheduler's
        # own rule can keep these apart.
        supervisor = _supervise(tmp_path, stores, bridge, max_concurrent_tasks=4)
        await _drain(supervisor, tasks, expected=1)

    asyncio.run(exercise())

    assert bridge.requests, "nothing reached the model, so this run proves nothing"
    assert bridge.same_conversation_overlaps == [], (
        f"{len(bridge.same_conversation_overlaps)} extractions from the same "
        "conversation were inside the model at the same time; HY decides "
        "supersede from what it has already been told, so neither could see "
        "the other's conclusion"
    )


def test_separate_harnesses_run_side_by_side(tmp_path) -> None:
    """Harness ordering does not serialize unrelated sources."""
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    _conversations(evidence, count=8, sources=("cursor", "codex"))
    bridge = WatchedBridge()

    async def exercise() -> None:
        # No max_concurrent_tasks: whatever the profile says is what should
        # happen, and nobody in the product passes one.
        supervisor = _supervise(tmp_path, stores, bridge)
        await _drain(supervisor, tasks, expected=8)

    asyncio.run(exercise())

    assert bridge.peak > 1, (
        f"two separate harnesses were extracted {bridge.peak} at a time; "
        "the scheduler is still working through harnesses one after another"
    )


def test_durable_drain_and_scheduler_share_one_source_lock(tmp_path) -> None:
    """A direct durable write cannot overlap the scheduler for one source."""
    stores = _setup(tmp_path)
    evidence, profiles, tasks, governance, secrets, _profile = stores
    _put(
        evidence,
        message_id="scheduled",
        role="user",
        written_by=WrittenBy.PERSON,
        content="后台调度中的 WorkBuddy 对话。",
        conversation_id="scheduled-conversation",
        source_id="workbuddy",
    )
    _put(
        evidence,
        message_id="scheduled-answer",
        role="assistant",
        written_by=WrittenBy.AGENT,
        content="后台调度中的 WorkBuddy 回复。",
        conversation_id="scheduled-conversation",
        source_id="workbuddy",
    )
    with sqlite3.connect(tmp_path / "one-memory.sqlite3") as database:
        database.executescript(
            """
            CREATE TABLE source_grants (
                user_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                root_path TEXT NOT NULL,
                candidate_kind TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                revoked_at TEXT,
                PRIMARY KEY (user_id, source_id)
            );
            INSERT INTO source_grants VALUES (
                'local','workbuddy','/authorized','default',
                '2026-10-04T00:00:00+00:00',NULL
            );
            """
        )
    bridge = WatchedBridge(seconds=0.2)

    async def exercise() -> None:
        scheduled_supervisor = _supervise(
            tmp_path,
            stores,
            bridge,
            max_concurrent_tasks=4,
        )
        direct_supervisor = _supervise(
            tmp_path,
            stores,
            bridge,
            max_concurrent_tasks=4,
        )
        scheduled_supervisor.backfill()
        for _ in range(100):
            if bridge.inside:
                break
            await asyncio.sleep(0.01)
        assert bridge.inside, "scheduler never entered the model"
        direct = _put(
            evidence,
            message_id="direct",
            role="user",
            written_by=WrittenBy.PERSON,
            content="durable drain 同时送来的 WorkBuddy 对话。",
            conversation_id="direct-conversation",
            source_id="workbuddy",
        )
        direct_answer = _put(
            evidence,
            message_id="direct-answer",
            role="assistant",
            written_by=WrittenBy.AGENT,
            content="durable drain 同时送来的 WorkBuddy 回复。",
            conversation_id="direct-conversation",
            source_id="workbuddy",
        )
        await direct_supervisor.process_records((direct, direct_answer))
        for _ in range(100):
            if len(bridge.requests) >= 2:
                break
            await asyncio.sleep(0.01)
        await asyncio.gather(
            scheduled_supervisor.shutdown(),
            direct_supervisor.shutdown(),
        )

    asyncio.run(exercise())

    assert len(bridge.requests) >= 2, "both execution paths must reach the model"
    assert bridge.overlaps == [], (
        f"the durable drain and scheduler entered HY together for one source: {bridge.overlaps}"
    )


def test_side_by_side_stops_at_the_profile_limit(tmp_path) -> None:
    """The limit is the model's own, not a number invented by the scheduler."""
    stores = _setup(tmp_path)
    evidence, profiles, tasks, _governance, secrets, profile = stores
    allowed = 3
    profile = profiles.update(
        profile.profile_id,
        ModelProfilePatch(expected_revision=profile.revision, max_concurrency=allowed),
        secrets,
    )
    # A changed profile has to be probed again before it can be the active one.
    profiles.record_capabilities(
        profile.profile_id,
        expected_revision=profile.revision,
        capabilities=ModelCapabilities(
            endpoint_reachable=True,
            model_available=True,
            structured_output=True,
            embedding_available=True,
        ),
        secrets=secrets,
    )
    profiles.activate(profile.profile_id, secrets)
    _conversations(
        evidence,
        count=8,
        sources=("cursor", "codex", "claude-code", "workbuddy"),
    )
    bridge = WatchedBridge()

    async def exercise() -> None:
        supervisor = _supervise(tmp_path, stores, bridge)
        await _drain(supervisor, tasks, expected=8)

    asyncio.run(exercise())

    assert bridge.peak > 1, "nothing ran side by side, so the ceiling is untested"
    assert bridge.peak <= allowed, (
        f"the profile allows {allowed} at a time and {bridge.peak} were in the model together"
    )


def test_a_queue_that_is_entirely_blocked_stops_starting_workers(tmp_path) -> None:
    """Serialising by conversation must not turn into a spin.

    A worker that finds nothing to take exits, and a worker exiting is what
    starts the next one. So a queue that is full but entirely blocked on the
    one conversation already running will start workers forever unless the
    question asked before starting one is "is there anything runnable",
    not "is the queue non-empty".

    The bound is deliberately loose: the difference between correct and
    wrong here is a handful against thousands, not a tuned number.
    """
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    turns = 6
    _conversations(evidence, count=1, turns=turns)
    bridge = WatchedBridge(seconds=0.05)
    starts = 0

    async def exercise() -> None:
        nonlocal starts
        supervisor = _supervise(tmp_path, stores, bridge)
        start_one = supervisor._start_worker  # noqa: SLF001 - counting the thing under test

        def counted() -> None:
            nonlocal starts
            starts += 1
            start_one()

        supervisor._start_worker = counted  # noqa: SLF001
        await _drain(supervisor, tasks, expected=turns)

    asyncio.run(exercise())

    assert starts > 0, "no worker was ever started, so the count proves nothing"
    assert starts <= 10 * turns, (
        f"{starts} workers were started for {turns} pieces of work, all of one "
        "conversation; each one found nothing to take and its exit started the next"
    )


def test_nothing_queued_is_lost_when_the_core_stops(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    _conversations(evidence, count=8)
    bridge = WatchedBridge(seconds=0.5)

    async def exercise() -> None:
        supervisor = _supervise(tmp_path, stores, bridge)
        supervisor.backfill()
        deadline = asyncio.get_running_loop().time() + 10.0
        try:
            while not tasks.list():
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError(
                        "backfill recorded no task within 10s; an unbounded wait "
                        "would hang the complete Core release gate"
                    )
                await asyncio.sleep(0.01)
            # Stop in the middle, which is what closing the window does.
        finally:
            await supervisor.shutdown()

    asyncio.run(exercise())

    recorded = tasks.list()
    assert recorded, "no task was ever recorded, so nothing was at risk"
    stranded = [
        task for task in recorded if task.status not in {MemoryTaskStatus.COMPLETED, *_CLAIMABLE}
    ]
    assert stranded == [], (
        f"{len(stranded)} tasks were left in a state no later run will pick up: "
        f"{[(t.task_id, str(t.status)) for t in stranded]}"
    )


_CLAIMABLE = {
    MemoryTaskStatus.PENDING,
    MemoryTaskStatus.WAITING_FOR_MODEL,
    MemoryTaskStatus.FAILED,
    MemoryTaskStatus.RUNNING,
}


def test_running_several_at_once_never_reports_the_database_locked(tmp_path) -> None:
    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    _conversations(evidence, count=12)
    bridge = WatchedBridge(seconds=0.05)

    async def exercise() -> None:
        supervisor = _supervise(tmp_path, stores, bridge)
        await _drain(supervisor, tasks, expected=12)

    asyncio.run(exercise())

    refused = [
        (task.task_id, task.last_error_code)
        for task in tasks.list()
        if task.last_error_code and "lock" in task.last_error_code.lower()
    ]
    assert refused == [], (
        f"extraction was refused the database while running side by side: {refused}"
    )
    assert all(task.status is MemoryTaskStatus.COMPLETED for task in tasks.list()), (
        "not every task finished, so a locked database could simply not have been reached yet"
    )


@pytest.mark.parametrize("workers", [1, 4])
def test_no_database_connection_is_held_while_the_model_thinks(tmp_path, workers) -> None:
    """Waiting on a model must not cost anyone a connection.

    Asked of the waiting thread itself, not of the database as a whole: with
    several workers, another one being mid-write while this one waits is
    exactly what is supposed to happen, and a process-wide reading calls that
    a fault. What must not happen is the thread that is about to sit on an
    `await` still holding a checkout of its own — the loop thread does every
    model call, so one held there is one nobody else can have for as long as
    the model takes.

    Checked at both settings because holding one only costs something when
    there is someone else to take it from.
    """
    from one_memory.database_access import main_database

    stores = _setup(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, _profile = stores
    _conversations(evidence, count=4)
    access = main_database(tmp_path / "one-memory.sqlite3")
    held: list[tuple[bool, int]] = []

    class Sampling(WatchedBridge):
        async def _spend_a_moment(self, request) -> None:
            me = threading.get_ident()
            held.append(
                (
                    access._writer_owner == me,  # noqa: SLF001 - the point of the test
                    access._reader_holders.get(me, 0),  # noqa: SLF001
                )
            )
            await super()._spend_a_moment(request)

    bridge = Sampling(seconds=0.1)

    async def exercise() -> None:
        supervisor = _supervise(tmp_path, stores, bridge, max_concurrent_tasks=workers)
        await _drain(supervisor, tasks, expected=4)

    asyncio.run(exercise())

    assert held, "the model was never reached, so nothing was sampled"
    assert [sample for sample in held if sample != (False, 0)] == [], (
        f"the thread about to wait on the model was still holding a checkout of its own: {held}"
    )
