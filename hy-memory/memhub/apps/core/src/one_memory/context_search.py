"""Bounded two-lane orchestration; readers and finalizers own trusted read access."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import TypeAdapter

from one_memory.context_models import (
    ContextItem,
    ContextKind,
    ContextLaneResult,
    ContextLimit,
    ContextPath,
    ContextPaths,
    ContextSearchRequest,
    ContextSearchResponse,
    MemoryContextItem,
    RawContextItem,
)

Reader = Callable[[float], Awaitable[ContextLaneResult]]
Finalizer = Callable[
    [ContextKind, tuple[ContextItem, ...], float], Awaitable[tuple[ContextItem, ...]]
]
TimingObserver = Callable[[Mapping[str, float]], None]
FailureObserver = Callable[[ContextKind, str, str], None]
_KINDS: tuple[ContextKind, ...] = ("raw", "memory")
_ITEMS = TypeAdapter(tuple[ContextItem, ...])


@dataclass
class _Lane:
    result: ContextLaneResult
    elapsed_ms: float = 0
    limits: list[ContextLimit] = field(default_factory=list)


def _identity(item: ContextItem) -> tuple[str, ...]:
    if isinstance(item, RawContextItem):
        return (item.kind, item.source_id, item.conversation_id, item.anchor_evidence_id)
    return (item.kind, item.memory_id)


def _validate_items(kind: ContextKind, items: tuple[ContextItem, ...]) -> None:
    if len(items) > 21 or any(item.kind != kind for item in items):
        raise ValueError("invalid lane items")
    for item in items:
        if isinstance(item, RawContextItem) and item.anchor_evidence_id not in {
            message.evidence_id for message in item.messages
        }:
            raise ValueError("missing raw anchor")


async def _read(reader: Reader, kind: ContextKind, deadline: float) -> ContextLaneResult:
    value = await reader(deadline)
    # Revalidate even BaseModel instances: model_construct/model_copy bypass validation.
    result = ContextLaneResult.model_validate(value.model_dump())
    _validate_items(kind, result.items)
    if result.status not in ("ok", "empty", "degraded", "unavailable"):
        raise ValueError("reader cannot decide requested authority")
    if result.status in ("empty", "unavailable") and result.items:
        raise ValueError("non-result lane has items")
    return result


async def _finalize(
    finalizer: Finalizer, kind: ContextKind, items: tuple[ContextItem, ...], deadline: float
) -> tuple[ContextItem, ...]:
    value = await finalizer(kind, items, deadline)
    if not isinstance(value, tuple):
        raise ValueError("invalid finalization result")
    checked = _ITEMS.validate_python([item.model_dump() for item in value])
    _validate_items(kind, checked)
    if not {_identity(item) for item in checked} <= {_identity(item) for item in items}:
        raise ValueError("finalizer introduced an unselected identity")
    return checked


async def _collect(
    jobs: dict[ContextKind, Awaitable[object]], deadline: float
) -> tuple[
    dict[ContextKind, object],
    dict[ContextKind, BaseException],
    set[ContextKind],
    dict[ContextKind, float],
]:
    """Cancel and await every owned task on deadline, failure or caller cancellation."""

    durations: dict[ContextKind, float] = {}

    async def measured(kind: ContextKind, job: Awaitable[object]) -> object:
        started = time.monotonic()
        try:
            value = await job
            if time.monotonic() >= deadline:
                raise TimeoutError
            return value
        finally:
            durations[kind] = (time.monotonic() - started) * 1000

    tasks = {kind: asyncio.create_task(measured(kind, job)) for kind, job in jobs.items()}
    values: dict[ContextKind, object] = {}
    failed: dict[ContextKind, BaseException] = {}
    timed_out: set[ContextKind] = set()
    try:
        if not tasks:
            return values, failed, timed_out, durations
        done, pending = await asyncio.wait(
            tasks.values(), timeout=max(0, deadline - time.monotonic())
        )
        for kind, task in tasks.items():
            if task in pending:
                timed_out.add(kind)
            elif task in done:
                if not task.cancelled() and isinstance(task.exception(), TimeoutError):
                    timed_out.add(kind)
                elif task.cancelled() or task.exception() is not None:
                    failed[kind] = task.exception() or asyncio.CancelledError()
                else:
                    values[kind] = task.result()
        return values, failed, timed_out, durations
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        if tasks:
            # Cooperative readers finish immediately and still get their
            # normal cleanup. A bridge that suppresses cancellation must not
            # hold a host response past its hard deadline while an underlying
            # SDK thread winds down.
            cleanup: asyncio.Future[list[object]] = asyncio.gather(
                *tasks.values(), return_exceptions=True
            )
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                await cleanup
            else:
                try:
                    await asyncio.wait_for(asyncio.shield(cleanup), timeout=0.05)
                except TimeoutError:
                    cleanup.add_done_callback(_consume_cleanup)


def _consume_cleanup(task: asyncio.Future[list[object]]) -> None:
    if not task.cancelled():
        task.exception()


def _deduplicate(
    items: tuple[ContextItem, ...], limits: list[ContextLimit]
) -> tuple[ContextItem, ...]:
    unique: dict[tuple[str, ...], ContextItem] = {}
    for item in items:
        key = _identity(item)
        previous = unique.get(key)
        if isinstance(previous, MemoryContextItem) and isinstance(item, MemoryContextItem):
            if item.revision != previous.revision:
                # Never graft older evidence onto a newer memory version.
                unique[key] = item if item.revision > previous.revision else previous
                continue
            evidence = tuple(dict.fromkeys((*previous.evidence_ids, *item.evidence_ids)))
            if len(evidence) > 128:
                limits.append("metadata_budget")
            unique[key] = previous.model_copy(
                update={
                    "evidence_ids": evidence[:128],
                    "truncated": previous.truncated or item.truncated or len(evidence) > 128,
                }
            )
        elif isinstance(previous, RawContextItem) and isinstance(item, RawContextItem):
            messages = {message.evidence_id: message for message in previous.messages}
            for message in item.messages:
                if (
                    message.evidence_id not in messages
                    or message.revision > messages[message.evidence_id].revision
                ):
                    messages[message.evidence_id] = message
            if len(messages) > 3:
                limits.append("metadata_budget")
            # The first window already contains the anchor; dict order preserves it.
            unique[key] = previous.model_copy(
                update={
                    "messages": tuple(messages.values())[:3],
                    "truncated": previous.truncated or item.truncated or len(messages) > 3,
                }
            )
        else:
            unique[key] = item
    # Reserve each raw anchor for its own window before deduplicating context messages.
    anchors = {
        (item.source_id, item.conversation_id, item.anchor_evidence_id)
        for item in unique.values()
        if isinstance(item, RawContextItem)
    }
    seen: set[tuple[str, ...]] = set()
    result: list[ContextItem] = []
    for item in unique.values():
        if isinstance(item, MemoryContextItem):
            result.append(
                item.model_copy(update={"evidence_ids": tuple(dict.fromkeys(item.evidence_ids))})
            )
            continue
        retained_messages = []
        for message in item.messages:
            key = (item.source_id, item.conversation_id, message.evidence_id)
            if key in seen or (key in anchors and message.evidence_id != item.anchor_evidence_id):
                continue
            seen.add(key)
            retained_messages.append(message)
        result.append(item.model_copy(update={"messages": tuple(retained_messages)}))
    return tuple(result)


def _characters(item: ContextItem) -> int:
    if isinstance(item, MemoryContextItem):
        return len(item.content)
    return sum(len(message.text) for message in item.messages)


def _shares(lengths: list[int], budget: int) -> list[int]:
    """Water-fill allocations so a large first item cannot consume every character."""
    allocations = [0] * len(lengths)
    pending = list(range(len(lengths)))
    while pending and budget:
        share, remainder = divmod(budget, len(pending))
        next_pending = []
        for position, index in enumerate(pending):
            added = min(lengths[index] - allocations[index], share + (position < remainder))
            allocations[index] += added
            budget -= added
            if allocations[index] < lengths[index]:
                next_pending.append(index)
        pending = next_pending
    return allocations


def _clip(item: ContextItem, budget: int) -> ContextItem:
    if _characters(item) <= budget:
        return item
    if isinstance(item, MemoryContextItem):
        return item.model_copy(update={"content": item.content[:budget], "truncated": True})
    # The first raw message is the lexical anchor. Give it the first share of
    # the budget, then water-fill the adjacent context; otherwise a long
    # neighbor can consume the whole window and hide the answer.
    anchor = item.messages[0]
    anchor_budget = min(len(anchor.text), budget)
    remaining = budget - anchor_budget
    adjacent = list(item.messages[1:])
    shares = [anchor_budget, *_shares([len(message.text) for message in adjacent], remaining)]
    return item.model_copy(
        update={
            "truncated": True,
            "messages": tuple(
                message.model_copy(
                    update={
                        "text": message.text[:share],
                        "truncated": message.truncated or len(message.text) > share,
                    }
                )
                for message, share in zip(item.messages, shares, strict=True)
            ),
        }
    )


async def search_context(
    request: ContextSearchRequest,
    *,
    raw_reader: Reader | None,
    memory_reader: Reader | None,
    finalizer: Finalizer,
    deadline: float | None = None,
    timing_observer: TimingObserver | None = None,
    failure_observer: FailureObserver | None = None,
) -> ContextSearchResponse:
    request = ContextSearchRequest.model_validate(request.model_dump())
    started = time.monotonic()
    deadline = min(
        deadline if deadline is not None else float("inf"), started + request.timeout_ms / 1000
    )
    lanes: dict[ContextKind, _Lane] = {}
    jobs: dict[ContextKind, Awaitable[object]] = {}
    readers: dict[ContextKind, Reader | None] = {"raw": raw_reader, "memory": memory_reader}
    for kind, reader in readers.items():
        if kind not in request.kinds:
            lanes[kind] = _Lane(ContextLaneResult(status="not_requested", reason="not_requested"))
        elif reader is None:
            lanes[kind] = _Lane(
                ContextLaneResult(status="not_authorized", reason="permission_required")
            )
        elif time.monotonic() >= deadline:
            lanes[kind] = _Lane(
                ContextLaneResult(status="degraded", reason="timeout_budget", timed_out=True),
                limits=["timeout_budget"],
            )
        else:
            jobs[kind] = _read(reader, kind, deadline)
    values, failed, timed_out, read_ms = await _collect(jobs, deadline)
    for kind in jobs:
        result = values.get(kind)
        if kind in timed_out:
            result = ContextLaneResult(
                status="degraded",
                reason="timeout_budget",
                truncated_by=("timeout_budget",),
                timed_out=True,
            )
        elif kind in failed or not isinstance(result, ContextLaneResult):
            error = failed.get(kind)
            if failure_observer is not None:
                failure_observer(
                    kind,
                    "collect",
                    type(error).__name__ if error is not None else "InvalidLaneResult",
                )
            result = ContextLaneResult(
                status="unavailable",
                reason="read_unavailable",
                failure_site="collect",
                error_class=type(error).__name__ if error is not None else "InvalidLaneResult",
            )
        lanes[kind] = _Lane(result, read_ms.get(kind, 0), list(dict.fromkeys(result.truncated_by)))

    final_jobs: dict[ContextKind, Awaitable[object]] = {}
    for kind in jobs:
        lane = lanes[kind]
        if lane.result.status not in ("ok", "empty", "degraded"):
            continue
        if time.monotonic() >= deadline:
            lane.result = ContextLaneResult(
                status="degraded", reason="timeout_budget", timed_out=True
            )
            lane.limits.append("timeout_budget")
        else:
            final_jobs[kind] = _finalize(finalizer, kind, lane.result.items, deadline)
    final_values, final_failed, final_timed_out, revalidation_ms = await _collect(
        final_jobs, deadline
    )
    for kind in final_jobs:
        lane = lanes[kind]
        lane.elapsed_ms += revalidation_ms.get(kind, 0)
        if kind in final_timed_out:
            lane.result = ContextLaneResult(
                status="unavailable", reason="timeout_budget", timed_out=True
            )
            lane.limits.append("timeout_budget")
        elif kind in final_failed:
            error = final_failed[kind]
            if failure_observer is not None:
                failure_observer(kind, "finalize", type(error).__name__)
            lane.result = ContextLaneResult(
                status="unavailable",
                reason="read_unavailable",
                failure_site="finalize",
                error_class=type(error).__name__,
            )
        else:
            final_items = _ITEMS.validate_python(final_values[kind])
            changed = {_identity(item): item for item in lane.result.items} != {
                _identity(item): item for item in final_items
            }
            lane.result = lane.result.model_copy(
                update={
                    "items": final_items,
                    "status": "degraded" if changed else lane.result.status,
                    "reason": ("evidence_changed" if kind == "raw" else "memory_changed")
                    if changed
                    else lane.result.reason,
                }
            )

    # Nothing previously verified may escape once the common release deadline expired.
    if time.monotonic() >= deadline:
        for kind in jobs:
            if lanes[kind].result.status in ("ok", "empty", "degraded"):
                lanes[kind].result = ContextLaneResult(
                    status="degraded", reason="timeout_budget", timed_out=True
                )
                lanes[kind].limits.append("timeout_budget")
    fusion_started = time.monotonic()
    queues = {kind: _deduplicate(lanes[kind].result.items, lanes[kind].limits) for kind in _KINDS}
    interleaved = [
        queues[kind][index]
        for index in range(max(map(len, queues.values()), default=0))
        for kind in _KINDS
        if index < len(queues[kind])
    ]
    selected = interleaved[: request.limit]
    for item in interleaved[request.limit :]:
        lanes[item.kind].limits.append("count_budget")
    shares = _shares([_characters(item) for item in selected], request.character_budget)
    items = tuple(_clip(item, share) for item, share in zip(selected, shares, strict=True))
    for before, after in zip(selected, items, strict=True):
        if _characters(before) != _characters(after):
            lanes[after.kind].limits.append("character_budget")
    if time.monotonic() >= deadline:
        items = ()
        for kind in jobs:
            if lanes[kind].result.status in ("ok", "empty", "degraded"):
                lanes[kind].result = ContextLaneResult(
                    status="degraded", reason="timeout_budget", timed_out=True
                )
                lanes[kind].limits.append("timeout_budget")
                lanes[kind].elapsed_ms = (time.monotonic() - started) * 1000
    paths: dict[ContextKind, ContextPath] = {}
    for kind in _KINDS:
        lane = lanes[kind]
        emitted = [item for item in items if item.kind == kind]
        limits = tuple(dict.fromkeys(lane.limits))
        truncated = bool(limits) or any(item.truncated for item in emitted)
        status = lane.result.status
        benign_limits = set(limits) <= {"count_budget", "character_budget"}
        benign_degradation = (
            not lane.result.timed_out
            and benign_limits
            and (
                lane.result.reason is None
                or (kind == "raw" and lane.result.reason == "lexical_only")
            )
        )
        if status in ("ok", "empty") or (status == "degraded" and benign_degradation):
            status = "ok" if emitted or lane.result.items else "empty"
        paths[kind] = ContextPath(
            status=status,
            reason=lane.result.reason,
            elapsed_ms=lane.elapsed_ms,
            returned_count=len(emitted),
            truncated=truncated,
            truncated_by=limits,
        )
    requested_paths = [paths[kind] for kind in request.kinds]
    completed = any(path.status in ("ok", "empty", "degraded") for path in requested_paths)
    incomplete = any(path.status not in ("ok", "empty") for path in requested_paths)
    response = ContextSearchResponse(
        request_id=str(uuid4()),
        state="unavailable"
        if not completed
        else "partial"
        if incomplete
        else "grounded"
        if items
        else "empty",
        paths=ContextPaths(raw=paths["raw"], memory=paths["memory"]),
        items=items,
        used_characters=sum(map(_characters, items)),
        truncated=any(path.truncated for path in paths.values()),
        total_ms=(time.monotonic() - started) * 1000,
    )
    checked = ContextSearchResponse.model_validate(response.model_dump())
    if timing_observer is not None:
        timing_observer(
            {
                "raw_ms": read_ms.get("raw", 0),
                "memory_ms": read_ms.get("memory", 0),
                "raw_revalidation_ms": revalidation_ms.get("raw", 0),
                "memory_revalidation_ms": revalidation_ms.get("memory", 0),
                "fusion_ms": (time.monotonic() - fusion_started) * 1000,
                "total_ms": checked.total_ms,
            }
        )
    return checked
