"""Deferring out-of-window work, and letting it back in a batch at a time.

The 675-item backlog came from one place: every imported chat was treated as
extractable, and the whole table was handed to the scheduler at once. Both
halves have to stay fixed. Work outside the window must be marked deferred
rather than left pending, and widening the window must not put the newly
eligible work back in one shot.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from one_memory.extraction_settings import ExtractionSettingsStore
from one_memory.imports.models import EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceInput, EvidenceStore
from one_memory.memory_processing import MemoryProcessingSupervisor
from one_memory.memory_queue import MANUAL_EXTRACT_BATCH_SIZE, ExtractionWindowPreset
from one_memory.memory_tasks import (
    ACTIVE_WINDOW_DEFER_LIMIT,
    MemoryTaskKind,
    MemoryTaskStatus,
    MemoryTaskStore,
)
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def _stores(tmp_path):
    database_path = tmp_path / "one-memory.sqlite3"
    evidence = EvidenceStore(database_path)
    tasks = MemoryTaskStore(database_path)
    profiles = ModelProfileStore(database_path)
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(
            name="Local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://example.com/v1",
            model="test-model",
            embedding_provider_kind=ProviderKind.LOCAL_ONNX,
            embedding_model="builtin",
            embedding_dimensions=512,
        ),
        secrets,
    )
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
    active = profiles.activate(profile.profile_id, secrets)
    supervisor = MemoryProcessingSupervisor(
        tasks=tasks,
        profiles=profiles,
        secrets=secrets,
        evidence=evidence,
        governance=None,  # type: ignore[arg-type]
        data_dir=tmp_path,
        extraction_settings=ExtractionSettingsStore(database_path),
    )
    return evidence, tasks, active, supervisor


def _task(evidence, tasks, active, *, index: int, age_days: int):
    record = evidence.put(
        EvidenceInput(
            source_id="cursor",
            workspace="/Users/me/project",
            conversation_id=f"conv-{index}",
            message_id=f"m{index}",
            correlation_id=f"m{index}",
            role="user",
            written_by=WrittenBy.PERSON,
            created_at=NOW - timedelta(days=age_days),
            verbatim="I prefer concise answers.",
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record
    return tasks.create(
        request_id=f"req-{index}",
        user_id="local",
        kind=MemoryTaskKind.EXTRACT,
        input_ref=record.evidence_id,
        profile=active,
    )


def test_classify_defers_tasks_outside_the_window(tmp_path) -> None:
    evidence, tasks, active, supervisor = _stores(tmp_path)
    task = _task(evidence, tasks, active, index=1, age_days=980)

    work = supervisor._classify([task])

    assert work == []
    assert tasks.require(task.task_id).status is MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW


def test_widening_the_window_enqueues_one_batch_at_a_time(tmp_path) -> None:
    """A wider window must not put every newly eligible task back at once.

    Written against the shape of the original defect: 60 conversations that
    the ninety-day window had deferred all become eligible under one year, and
    if they all go back to pending together the next thing the user says is
    once again behind the whole catch-up.
    """
    evidence, tasks, active, supervisor = _stores(tmp_path)
    deferred = [
        _task(evidence, tasks, active, index=index, age_days=120 + index) for index in range(60)
    ]
    assert supervisor._classify(deferred) == []

    async def widen() -> None:
        supervisor.set_extraction_window(ExtractionWindowPreset.ONE_YEAR)

    asyncio.run(widen())

    statuses = [tasks.require(task.task_id).status for task in deferred]
    # Counted as "no longer deferred" rather than "pending": a worker is free
    # to have claimed one already, and that is the batch moving, not a leak.
    let_through = sum(
        1 for status in statuses if status is not MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW
    )
    assert let_through == MANUAL_EXTRACT_BATCH_SIZE
    assert statuses.count(MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW) == 60 - (
        MANUAL_EXTRACT_BATCH_SIZE
    )
    assert supervisor.manual_batch_progress() == (3, 1)


@pytest.mark.parametrize("recent_count", [2, 0])
def test_older_work_remains_deferred_until_the_window_is_widened(tmp_path, recent_count) -> None:
    """The configured extraction window is a processing boundary, not just ordering.

    Older Evidence remains searchable and can be promoted explicitly, but an
    idle queue must not silently override the user's selected window.
    """
    evidence, tasks, active, supervisor = _stores(tmp_path)
    recent = [
        _task(evidence, tasks, active, index=index, age_days=5 + index)
        for index in range(recent_count)
    ]
    older = [
        _task(evidence, tasks, active, index=10 + index, age_days=120 + index)
        for index in range(MANUAL_EXTRACT_BATCH_SIZE + 5)
    ]
    assert supervisor._classify(older) == []
    dispatched: list[str] = []

    class Recorder:
        async def run(self, task_id: str, *, timeout: float | None = None) -> None:
            dispatched.append(task_id)

    supervisor.runner_factory = Recorder

    async def exercise() -> None:
        supervisor.resume()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if len(dispatched) == len(recent):
                break
        await supervisor.shutdown()

    asyncio.run(exercise())

    assert dispatched[: len(recent)] == [task.task_id for task in recent]
    assert dispatched[len(recent) :] == []
    assert {
        task.task_id for task in tasks.list(statuses=(MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW,))
    } == {task.task_id for task in older}


def test_a_window_that_still_misses_the_evidence_plans_no_batches(tmp_path) -> None:
    """Evidence two years old is untouched by a move to six months.

    The end state alone does not prove this: work promoted without checking
    the new window is re-deferred by the next classify, so the statuses come
    out identical either way. What differs is the plan the task centre is
    told about, so that is what this asserts.
    """
    evidence, tasks, active, supervisor = _stores(tmp_path)
    deferred = [
        _task(evidence, tasks, active, index=index, age_days=900 + index) for index in range(30)
    ]
    assert supervisor._classify(deferred) == []

    async def widen() -> None:
        supervisor.set_extraction_window(ExtractionWindowPreset.SIX_MONTHS)

    asyncio.run(widen())

    statuses = [tasks.require(task.task_id).status for task in deferred]
    assert statuses.count(MemoryTaskStatus.PENDING) == 0
    assert supervisor.manual_batch_progress() == (0, 0)


def test_out_of_window_deferral_is_bounded_per_active_window(tmp_path) -> None:
    """A large legacy pending set must not become one huge write.

    `active_window` marks out-of-window work deferred while preparing the
    scheduler. On a first-run corpus that set can be hundreds of thousands of
    rows; a single unbounded UPDATE holds the only writer for the whole batch.
    The boundary is a bounded page, and the next preparation continues from
    what remains pending.
    """
    evidence, tasks, active, supervisor = _stores(tmp_path)
    created = [
        _task(evidence, tasks, active, index=index, age_days=400 + index)
        for index in range(ACTIVE_WINDOW_DEFER_LIMIT + 7)
    ]

    supervisor._prepare_active_window()

    deferred = tasks.list(statuses=(MemoryTaskStatus.DEFERRED_OUTSIDE_WINDOW,))
    pending = tasks.list(statuses=(MemoryTaskStatus.PENDING,))
    assert len(deferred) == ACTIVE_WINDOW_DEFER_LIMIT
    assert len(pending) == len(created) - ACTIVE_WINDOW_DEFER_LIMIT
