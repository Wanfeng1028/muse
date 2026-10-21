import asyncio
import time
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from one_memory.context_models import (
    ContextLaneResult,
    ContextMessage,
    ContextSearchRequest,
    ContextSearchResponse,
    MemoryContextItem,
    RawContextItem,
)
from one_memory.context_search import search_context


def memory(identity="m", text="memory", evidence=("e",)):
    return MemoryContextItem(
        memory_id=identity,
        revision=1,
        content=text,
        memory_kind="chat",
        updated_at=datetime.now(UTC),
        evidence_ids=evidence,
    )


def raw(identity="e", text="raw"):
    return RawContextItem(
        source_id="cursor",
        conversation_id="c",
        anchor_evidence_id=identity,
        messages=(
            ContextMessage(
                evidence_id=identity,
                revision=2,
                role="user",
                written_by="person",
                created_at=None,
                text=text,
            ),
        ),
    )


def reader(*items, status="ok", reason=None, truncated_by=()):
    async def read(deadline):
        assert deadline > time.monotonic()
        return ContextLaneResult(
            items=items, status=status, reason=reason, truncated_by=truncated_by
        )

    return read


async def finalize(kind, items, deadline):
    assert deadline > time.monotonic()
    assert all(item.kind == kind for item in items)
    return items


def run(request=None, raw_reader=None, memory_reader=None, finalizer=finalize):
    return asyncio.run(
        search_context(
            request or ContextSearchRequest(query="q"),
            raw_reader=raw_reader,
            memory_reader=memory_reader,
            finalizer=finalizer,
        )
    )


def test_authorization_and_requested_paths_never_invoke_other_lane():
    async def forbidden(deadline):
        pytest.fail("unrequested lane invoked")

    result = run(
        ContextSearchRequest(query="q", kinds=("memory",)),
        raw_reader=forbidden,
        memory_reader=reader(memory()),
    )
    assert result.paths.raw.status == "not_requested"
    assert result.state == "grounded"
    denied = run(memory_reader=reader(status="empty"))
    assert denied.paths.raw.status == "not_authorized"
    assert denied.paths.raw.reason == "permission_required"
    assert denied.state == "partial" and denied.items == ()


def test_empty_partial_zero_unavailable_and_safe_failures():
    assert (
        run(raw_reader=reader(status="empty"), memory_reader=reader(status="empty")).state
        == "empty"
    )

    async def fail(deadline):
        raise RuntimeError("PRIVATE_SECRET_SQL_PATH")

    result = run(raw_reader=fail, memory_reader=fail)
    assert result.state == "unavailable"
    assert "PRIVATE" not in result.model_dump_json()
    assert result.paths.raw.reason == "read_unavailable"
    partial = run(raw_reader=fail, memory_reader=reader(status="empty"))
    assert partial.state == "partial" and partial.used_characters == 0
    lexical_only = run(
        raw_reader=reader(status="degraded", reason="lexical_only"),
        memory_reader=reader(status="empty"),
    )
    assert lexical_only.state == "empty"
    assert lexical_only.paths.raw.status == "empty"


def test_parallel_common_deadline_and_finalizers_wait_for_both_reads():
    async def scenario():
        entered = set()
        deadlines = []
        finished = set()

        async def read(kind, deadline):
            entered.add(kind)
            deadlines.append(deadline)
            while len(entered) != 2:
                await asyncio.sleep(0)
            await asyncio.sleep(0.005 if kind == "raw" else 0.015)
            finished.add(kind)
            return ContextLaneResult(status="ok", items=(raw() if kind == "raw" else memory(),))

        async def final(kind, items, deadline):
            assert finished == {"raw", "memory"}
            deadlines.append(deadline)
            return () if kind == "raw" else items

        result = await search_context(
            ContextSearchRequest(query="q"),
            raw_reader=lambda d: read("raw", d),
            memory_reader=lambda d: read("memory", d),
            finalizer=final,
        )
        assert len(set(deadlines)) == 1
        assert [i.kind for i in result.items] == ["memory"]
        assert result.paths.raw.reason == "evidence_changed"
        assert result.state == "partial"

    asyncio.run(scenario())


def test_stage_timings_separate_lanes_revalidation_fusion_and_total():
    async def scenario():
        observed = []

        async def delayed(item, delay):
            await asyncio.sleep(delay)
            return ContextLaneResult(status="ok", items=(item,))

        async def delayed_final(kind, items, deadline):
            await asyncio.sleep(0.004 if kind == "raw" else 0.008)
            return items

        result = await search_context(
            ContextSearchRequest(query="q"),
            raw_reader=lambda _deadline: delayed(raw(), 0.006),
            memory_reader=lambda _deadline: delayed(memory(), 0.012),
            finalizer=delayed_final,
            timing_observer=observed.append,
        )
        assert result.state == "grounded" and len(observed) == 1
        timing = observed[0]
        assert set(timing) == {
            "raw_ms",
            "memory_ms",
            "raw_revalidation_ms",
            "memory_revalidation_ms",
            "fusion_ms",
            "total_ms",
        }
        assert 4 <= timing["raw_ms"] < timing["memory_ms"]
        assert 2 <= timing["raw_revalidation_ms"] < timing["memory_revalidation_ms"]
        assert timing["fusion_ms"] >= 0
        assert timing["total_ms"] >= timing["memory_ms"] + timing["memory_revalidation_ms"]

    asyncio.run(scenario())


def test_finalizer_failure_never_releases_old_items():
    async def fail(kind, items, deadline):
        raise ValueError("PRIVATE")

    result = run(raw_reader=reader(raw()), memory_reader=reader(memory()), finalizer=fail)
    assert result.items == () and result.state == "unavailable"
    assert "PRIVATE" not in result.model_dump_json()


def test_shared_count_text_fairness_and_anchor_metadata():
    result = run(
        ContextSearchRequest(query="q", character_budget=200, limit=2),
        raw_reader=reader(raw(text="R" * 1000), raw("e2")),
        memory_reader=reader(memory(text="M" * 1000), memory("m2")),
    )
    assert [i.kind for i in result.items] == ["raw", "memory"]
    assert result.used_characters == 200
    assert len(result.items[0].messages[0].text) == 100
    assert len(result.items[1].content) == 100
    assert result.items[0].anchor_evidence_id == "e"
    assert result.items[0].messages[0].revision == 2
    assert result.items[0].messages[0].written_by == "person"
    for path in (result.paths.raw, result.paths.memory):
        assert path.returned_count == 1
        assert set(path.truncated_by) == {"count_budget", "character_budget"}
    assert all(i.truncated for i in result.items)
    assert result.state == "grounded" and result.adoption == "unknown"
    assert result.paths.raw.status == "ok"
    assert result.paths.memory.status == "ok"
    ContextSearchResponse.model_validate_json(result.model_dump_json())


def test_dedup_preserves_cross_kind_evidence_relations():
    item = raw()
    result = run(
        raw_reader=reader(item, item),
        memory_reader=reader(memory(), memory(), memory("other", evidence=("e", "e"))),
    )
    assert len(result.items) == 3
    assert result.paths.raw.returned_count == 1
    assert result.paths.memory.returned_count == 2
    assert result.items[-1].evidence_ids == ("e",)


def test_timeout_cancels_tasks_and_late_results_are_not_released():
    async def scenario():
        cancelled = []

        async def slow(deadline):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                return ContextLaneResult(status="ok", items=(raw(text="late"),))

        result = await search_context(
            ContextSearchRequest(query="q", timeout_ms=50),
            raw_reader=slow,
            memory_reader=reader(memory()),
            finalizer=finalize,
        )
        assert cancelled == [True]
        assert result.items == ()
        assert result.paths.raw.reason == "timeout_budget"
        assert result.paths.memory.reason == "timeout_budget"
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(scenario())


def test_caller_cancellation_propagates_and_cleans_readers():
    async def scenario():
        started = asyncio.Event()
        exits = []

        async def slow(deadline):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                exits.append(1)

        task = asyncio.create_task(
            search_context(
                ContextSearchRequest(query="q"),
                raw_reader=slow,
                memory_reader=slow,
                finalizer=finalize,
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(exits) == 2
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(scenario())


def test_invalid_lane_shape_and_wrong_kind_fail_closed():
    async def invalid(deadline):
        return {"status": "ok", "items": [], "private_diagnostic": "secret"}

    assert run(raw_reader=invalid, memory_reader=reader(memory())).paths.raw.status == "unavailable"
    assert (
        run(raw_reader=reader(memory()), memory_reader=reader(memory())).paths.raw.status
        == "unavailable"
    )
    with pytest.raises(ValidationError):
        ContextSearchRequest(query="q", limit=21)
    with pytest.raises(ValidationError):
        ContextSearchRequest(query="q", character_budget=20001)


def test_expired_entry_deadline_never_reads_or_releases_content():
    async def forbidden(*args):
        pytest.fail("expired deadline must not invoke work")

    result = asyncio.run(
        search_context(
            ContextSearchRequest(query="q"),
            raw_reader=forbidden,
            memory_reader=forbidden,
            finalizer=forbidden,
            deadline=time.monotonic() - 1,
        )
    )
    assert result.state == "partial" and result.items == ()
    assert result.paths.raw.reason == result.paths.memory.reason == "timeout_budget"


def test_entry_deadline_is_not_reset_and_request_timeout_caps_it():
    async def scenario():
        observed = []

        async def read(deadline):
            observed.append(deadline)
            return ContextLaneResult(status="ok", items=(memory(),))

        entry = time.monotonic() + 0.1
        await search_context(
            ContextSearchRequest(query="q"),
            raw_reader=None,
            memory_reader=read,
            finalizer=finalize,
            deadline=entry,
        )
        assert observed == [entry]
        started = time.monotonic()
        await search_context(
            ContextSearchRequest(query="q", timeout_ms=50),
            raw_reader=None,
            memory_reader=read,
            finalizer=finalize,
            deadline=started + 10,
        )
        assert observed[-1] < started + 0.1

    asyncio.run(scenario())


def test_finalizer_timeout_cannot_release_previously_read_items():
    async def scenario():
        cancelled = []

        async def slow(kind, items, deadline):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(kind)
                return items

        result = await search_context(
            ContextSearchRequest(query="q", timeout_ms=50),
            raw_reader=reader(raw()),
            memory_reader=reader(memory()),
            finalizer=slow,
        )
        assert set(cancelled) == {"raw", "memory"}
        assert result.items == () and result.state == "unavailable"
        assert result.paths.memory.truncated_by == ("timeout_budget",)
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(scenario())


def test_overlapping_raw_windows_keep_each_anchor_and_cross_kind_reference():
    first = raw("e1")
    second = raw("e2")
    first = first.model_copy(update={"messages": first.messages + second.messages})
    result = run(
        raw_reader=reader(first, second), memory_reader=reader(memory(evidence=("e1", "e2")))
    )
    windows = [item for item in result.items if item.kind == "raw"]
    assert [item.anchor_evidence_id for item in windows] == ["e1", "e2"]
    assert [message.evidence_id for item in windows for message in item.messages] == ["e1", "e2"]
    assert next(item for item in result.items if item.kind == "memory").evidence_ids == ("e1", "e2")


def test_twenty_item_and_twenty_thousand_character_caps():
    result = run(
        ContextSearchRequest(query="q", limit=20, character_budget=20000),
        raw_reader=reader(*(raw(f"e{i}", "r" * 20000) for i in range(21))),
        memory_reader=reader(*(memory(f"m{i}", "m" * 20000) for i in range(21))),
    )
    assert len(result.items) == 20 and result.used_characters == 20000
    assert result.paths.raw.returned_count == result.paths.memory.returned_count == 10
    assert (
        sum(
            len(i.content) if i.kind == "memory" else sum(len(m.text) for m in i.messages)
            for i in result.items
        )
        == 20000
    )


def test_caller_cancel_during_finalization_cleans_all_tasks():
    async def scenario():
        started = asyncio.Event()
        finished = []

        async def final(kind, items, deadline):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                finished.append(kind)

        task = asyncio.create_task(
            search_context(
                ContextSearchRequest(query="q"),
                raw_reader=reader(raw()),
                memory_reader=reader(memory()),
                finalizer=final,
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert set(finished) == {"raw", "memory"}
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    asyncio.run(scenario())


def test_invalid_finalizer_output_and_constructed_models_fail_closed():
    async def wrong(kind, items, deadline):
        return (memory("unselected"),)

    assert run(memory_reader=reader(memory()), finalizer=wrong).items == ()
    invalid = memory().model_copy(update={"content": "x" * 20001})
    assert run(memory_reader=reader(invalid)).state == "unavailable"
    with pytest.raises(ValidationError):
        run(ContextSearchRequest.model_construct(query="q", limit=100))


def test_duplicate_memory_identity_keeps_combined_evidence_relations():
    result = run(memory_reader=reader(memory(evidence=("a",)), memory(evidence=("b",))))
    assert result.items[0].evidence_ids == ("a", "b")


def test_one_slow_finalizer_exhausts_release_deadline_for_both_lanes():
    async def final(kind, items, deadline):
        if kind == "raw":
            await asyncio.sleep(10)
        return items

    result = run(
        ContextSearchRequest(query="q", timeout_ms=50),
        raw_reader=reader(raw()),
        memory_reader=reader(memory()),
        finalizer=final,
    )
    assert result.items == ()
    assert result.state == "partial"


def test_multiple_raw_messages_clipped_without_losing_anchor_or_authorship():
    item = raw("anchor", "A" * 20000)
    item = item.model_copy(
        update={
            "messages": (
                raw("before", "B" * 20000).messages[0],
                item.messages[0],
                raw("after", "C" * 20000).messages[0],
            )
        }
    )
    result = run(
        ContextSearchRequest(query="q", character_budget=200),
        raw_reader=reader(item),
        memory_reader=reader(memory(text="M" * 20000)),
    )
    emitted = result.items[0]
    assert emitted.anchor_evidence_id == "anchor"
    assert [m.evidence_id for m in emitted.messages] == ["before", "anchor", "after"]
    assert all(
        m.truncated and m.written_by == "person" and m.revision == 2 for m in emitted.messages
    )
    assert result.used_characters == 200


def test_metadata_union_stays_bounded_and_reports_truncation():
    result = run(
        memory_reader=reader(
            memory(evidence=tuple(f"a{i}" for i in range(128))), memory(evidence=("extra",))
        )
    )
    assert len(result.items[0].evidence_ids) == 128
    assert result.items[0].truncated
    assert "metadata_budget" in result.paths.memory.truncated_by


def test_finalizer_removed_context_message_reports_partial_not_complete():
    item = raw()
    item = item.model_copy(update={"messages": item.messages + raw("other").messages})

    async def final(kind, items, deadline):
        return tuple(i.model_copy(update={"messages": i.messages[:1]}) for i in items)

    result = run(
        ContextSearchRequest(query="q", kinds=("raw",)), raw_reader=reader(item), finalizer=final
    )
    assert result.state == "partial"
    assert result.paths.raw.reason == "evidence_changed"


def test_noncooperative_synchronous_reader_return_after_deadline_is_discarded():
    async def late(deadline):
        time.sleep(0.06)
        return ContextLaneResult(status="ok", items=(raw(),))

    result = run(ContextSearchRequest(query="q", kinds=("raw",), timeout_ms=50), raw_reader=late)
    assert result.items == () and result.paths.raw.reason == "timeout_budget"


def test_timeout_does_not_wait_for_a_reader_that_suppresses_cancellation():
    async def scenario():
        release = asyncio.Event()

        async def stuck(_deadline):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                return ContextLaneResult(status="empty")

        started = time.monotonic()
        result = await search_context(
            ContextSearchRequest(query="q", kinds=("memory",), timeout_ms=50),
            raw_reader=None,
            memory_reader=stuck,
            finalizer=finalize,
        )
        assert time.monotonic() - started < 0.2
        assert result.paths.memory.reason == "timeout_budget"
        release.set()
        await asyncio.sleep(0)

    asyncio.run(scenario())
