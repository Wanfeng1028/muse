import asyncio
from types import SimpleNamespace

import pytest

import one_memory.service_levels as service_levels
from one_memory.service_levels import (
    ResourceLimit,
    ServiceLevel,
    ServiceLevelScheduler,
    ServiceResource,
)


def test_background_never_consumes_the_realtime_reservation() -> None:
    async def scenario() -> None:
        scheduler = ServiceLevelScheduler(
            {ServiceResource.IMPORT: ResourceLimit(capacity=2, background_capacity=1)},
            interactive_cooldown_seconds=0,
        )
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()
        realtime_entered = asyncio.Event()

        async def hold_background(work_id: str, entered: asyncio.Event) -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.BACKGROUND,
                work_id=work_id,
            ):
                entered.set()
                await release_first.wait()

        first = asyncio.create_task(hold_background("history-1", first_entered))
        await first_entered.wait()
        second = asyncio.create_task(hold_background("history-2", second_entered))
        await asyncio.sleep(0)
        assert not second_entered.is_set()

        async def realtime() -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.REALTIME,
                work_id="live-1",
            ):
                realtime_entered.set()

        live = asyncio.create_task(realtime())
        await asyncio.wait_for(realtime_entered.wait(), 0.2)
        assert not second_entered.is_set()
        await live
        release_first.set()
        await asyncio.gather(first, second)

    asyncio.run(scenario())


def test_realtime_is_next_for_the_same_source_after_background_yields() -> None:
    async def scenario() -> None:
        scheduler = ServiceLevelScheduler(
            {ServiceResource.IMPORT: ResourceLimit(capacity=2, background_capacity=1)},
            interactive_cooldown_seconds=0,
        )
        release = asyncio.Event()
        order: list[str] = []

        async def hold() -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.BACKGROUND,
                work_id="history-running",
                scope_key="workbuddy",
            ):
                order.append("history-running")
                await release.wait()

        async def enter(level: ServiceLevel, name: str) -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                level,
                work_id=name,
                scope_key="workbuddy",
            ):
                order.append(name)

        running = asyncio.create_task(hold())
        await asyncio.sleep(0)
        background = asyncio.create_task(enter(ServiceLevel.BACKGROUND, "history-next"))
        realtime = asyncio.create_task(enter(ServiceLevel.REALTIME, "live"))
        await asyncio.sleep(0)
        assert scheduler.should_yield(ServiceResource.IMPORT, ServiceLevel.BACKGROUND)
        release.set()
        await asyncio.gather(running, realtime, background)
        assert order == ["history-running", "live", "history-next"]

    asyncio.run(scenario())


def test_import_history_gets_one_slice_after_nine_realtime_admissions() -> None:
    async def scenario() -> None:
        scheduler = ServiceLevelScheduler(
            {ServiceResource.IMPORT: ResourceLimit(capacity=1, background_capacity=1)},
            interactive_cooldown_seconds=0,
        )
        release_holder = asyncio.Event()
        order: list[str] = []

        async def hold() -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.REALTIME,
                work_id="live-holder",
            ):
                order.append("live-holder")
                await release_holder.wait()

        async def enter(level: ServiceLevel, name: str) -> None:
            async with scheduler.admit(ServiceResource.IMPORT, level, work_id=name):
                order.append(name)

        holder = asyncio.create_task(hold())
        while not order:
            await asyncio.sleep(0)
        history = asyncio.create_task(enter(ServiceLevel.BACKGROUND, "history"))
        live = [
            asyncio.create_task(enter(ServiceLevel.REALTIME, f"live-{index}"))
            for index in range(12)
        ]
        release_holder.set()
        await asyncio.gather(holder, history, *live)
        assert "history" in order[1:11]

    asyncio.run(scenario())


def test_recent_interaction_temporarily_holds_background() -> None:
    async def scenario() -> None:
        now = 10.0
        scheduler = ServiceLevelScheduler(
            {
                ServiceResource.INTERACTIVE_READ: ResourceLimit(2, 0),
                ServiceResource.INDEX: ResourceLimit(1, 1),
            },
            interactive_cooldown_seconds=0.5,
            clock=lambda: now,
        )
        await scheduler.note_interactive(work_id="recall-1")
        assert scheduler.should_yield(ServiceResource.INDEX, ServiceLevel.BACKGROUND)
        now = 10.6
        assert not scheduler.should_yield(ServiceResource.INDEX, ServiceLevel.BACKGROUND)

    asyncio.run(scenario())


def test_realtime_model_work_preempts_background_import_globally() -> None:
    async def scenario() -> None:
        scheduler = ServiceLevelScheduler(
            {
                ServiceResource.IMPORT: ResourceLimit(2, 1),
                ServiceResource.MODEL: ResourceLimit(2, 1),
            },
            interactive_cooldown_seconds=0,
        )
        realtime_entered = asyncio.Event()
        release = asyncio.Event()
        background_entered = asyncio.Event()

        async def realtime_model() -> None:
            async with scheduler.admit(
                ServiceResource.MODEL,
                ServiceLevel.REALTIME,
                work_id="live-memory",
            ):
                assert scheduler.should_yield(ServiceResource.IMPORT, ServiceLevel.BACKGROUND)
                realtime_entered.set()
                await release.wait()

        async def background_import() -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.BACKGROUND,
                work_id="history",
            ):
                background_entered.set()

        live = asyncio.create_task(realtime_model())
        await realtime_entered.wait()
        history = asyncio.create_task(background_import())
        await asyncio.sleep(0)
        assert not background_entered.is_set()
        release.set()
        await live
        await asyncio.wait_for(background_entered.wait(), 0.2)
        await history

    asyncio.run(scenario())


def test_cancelled_waiter_does_not_block_the_next_job() -> None:
    async def scenario() -> None:
        scheduler = ServiceLevelScheduler(
            {ServiceResource.IMPORT: ResourceLimit(capacity=1, background_capacity=1)},
            interactive_cooldown_seconds=0,
        )
        release = asyncio.Event()

        async def hold() -> None:
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.REALTIME,
                work_id="holder",
                scope_key="workbuddy",
            ):
                await release.wait()

        holder = asyncio.create_task(hold())
        await asyncio.sleep(0)
        cancelled = asyncio.create_task(
            scheduler._acquire(
                ServiceResource.IMPORT,
                ServiceLevel.REALTIME,
                work_id="cancelled",
                scope_key="workbuddy",
            )
        )
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        release.set()
        await holder
        async with asyncio.timeout(0.2):
            async with scheduler.admit(
                ServiceResource.IMPORT,
                ServiceLevel.BACKGROUND,
                work_id="next",
                scope_key="cursor",
            ):
                pass
        assert scheduler.snapshot().waiting[ServiceResource.IMPORT.value]["realtime"] == 0

    asyncio.run(scenario())


def test_zero_wait_admissions_are_aggregated_without_hiding_real_waits(monkeypatch) -> None:
    async def scenario() -> None:
        now = 10.0
        events: list[dict[str, object]] = []
        monkeypatch.setattr(
            service_levels,
            "diagnostic_event",
            lambda **event: events.append(event),
        )
        scheduler = ServiceLevelScheduler(
            {ServiceResource.INTERACTIVE_READ: ResourceLimit(2, 0)},
            interactive_cooldown_seconds=0,
            clock=lambda: now,
        )
        for index in range(100):
            async with scheduler.admit(
                ServiceResource.INTERACTIVE_READ,
                ServiceLevel.INTERACTIVE,
                work_id=f"poll-{index}",
            ):
                pass
        assert [event["event"] for event in events] == ["service_level.admitted"]

        now = 311.0
        async with scheduler.admit(
            ServiceResource.INTERACTIVE_READ,
            ServiceLevel.INTERACTIVE,
            work_id="poll-summary",
        ):
            pass
        assert [event["event"] for event in events] == [
            "service_level.admitted",
            "service_level.summary",
        ]
        assert events[-1]["details"] == {
            "mode": "interactive",
            "phase": "interactive_read",
            "queue_depth": 0,
            "count": 100,
        }

        scheduler._record_admission(  # noqa: SLF001
            SimpleNamespace(
                resource=ServiceResource.INTERACTIVE_READ,
                level=ServiceLevel.INTERACTIVE,
                work_id="queued-poll",
            ),
            waited_ms=0,
            queue_depth=6,
        )
        assert len(events) == 2

    asyncio.run(scenario())


def test_one_day_of_idle_polling_produces_only_five_minute_summaries(monkeypatch) -> None:
    now = 0.0
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        service_levels,
        "diagnostic_event",
        lambda **event: events.append(event),
    )
    scheduler = ServiceLevelScheduler(
        {ServiceResource.INTERACTIVE_READ: ResourceLimit(2, 0)},
        interactive_cooldown_seconds=0,
        clock=lambda: now,
    )
    waiter = SimpleNamespace(
        resource=ServiceResource.INTERACTIVE_READ,
        level=ServiceLevel.INTERACTIVE,
        work_id="poll",
    )

    for tick in range(24 * 60 * 60 * 33 // 2):
        now = tick / 16.5
        scheduler._record_admission(waiter, waited_ms=0, queue_depth=0)  # noqa: SLF001

    assert len(events) <= 1 + (24 * 60 * 60 // 300)
    assert events[0]["event"] == "service_level.admitted"
    assert all(event["event"] == "service_level.summary" for event in events[1:])
