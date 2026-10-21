import asyncio

from one_memory.background_work import shutdown_bulk_pool
from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.source_totals import SourceTotals


def evidence(message_id: str, *, source_id: str = "fixture", conversation: str) -> EvidenceInput:
    return EvidenceInput(
        source_id=source_id,
        conversation_id=conversation,
        message_id=message_id,
        role="user",
        written_by=WrittenBy.PERSON,
        verbatim=f"message {message_id}",
        origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
    )


class _Counted:
    """An evidence store that says how often it has been asked to count."""

    def __init__(self, inner: EvidenceStore) -> None:
        self._inner = inner
        self.counts = 0
        self.mark_reads = 0

    def source_totals_by_source(self, *, user_id: str):
        self.counts += 1
        return self._inner.source_totals_by_source(user_id=user_id)

    def high_water_mark(self) -> int:
        self.mark_reads += 1
        return self._inner.high_water_mark()


def build(tmp_path):
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    counted = _Counted(store)
    clock = {"now": 1_000.0}
    totals = SourceTotals(counted, interval_seconds=2.0, now=lambda: clock["now"])
    return store, counted, clock, totals


def test_the_first_ask_is_answered_from_the_rows(tmp_path) -> None:
    store, counted, _clock, totals = build(tmp_path)
    store.put(evidence("1", conversation="a"))
    store.put(evidence("2", conversation="a"))
    store.put(evidence("3", conversation="b"))

    try:
        answered = asyncio.run(totals.by_source(user_id="local"))
    finally:
        shutdown_bulk_pool()

    assert answered == {"fixture": (3, 2)}
    assert counted.counts == 1


def test_same_named_sessions_in_two_workspaces_count_as_two_conversations(tmp_path) -> None:
    """Cursor can reuse a session name across projects.

    The read path already keeps those histories separate by workspace. The
    totals shown to the user must use the same identity instead of collapsing
    the two source conversations back into one.
    """
    store, _counted, _clock, totals = build(tmp_path)
    first = evidence("1", source_id="cursor", conversation="same")
    first = first.model_copy(update={"workspace": "workspace:v1:project-a"})
    second = evidence("2", source_id="cursor", conversation="same")
    second = second.model_copy(update={"workspace": "workspace:v1:project-b"})
    store.put(first)
    store.put(second)

    try:
        answered = asyncio.run(totals.by_source(user_id="local"))
    finally:
        shutdown_bulk_pool()

    assert answered == {"cursor": (2, 2)}
    assert store.source_totals(user_id="local", source_id="cursor") == (2, 2)


def test_insert_during_count_is_not_marked_as_already_counted(tmp_path):
    store, counted, clock, totals = build(tmp_path)
    store.put(evidence("1", conversation="a"))
    original = counted.source_totals_by_source

    def count_and_insert(*, user_id):
        values = original(user_id=user_id)
        store.put(evidence("2", conversation="b"))
        return values

    counted.source_totals_by_source = count_and_insert

    async def scenario():
        assert await totals.by_source(user_id="local") == {"fixture": (1, 1)}
        clock["now"] += 3
        assert await totals.by_source(user_id="local") == {"fixture": (2, 2)}

    try:
        asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()


def test_asking_again_straight_away_does_not_count_again(tmp_path) -> None:
    """The screen asks once a second; counting takes up to 1.37s of that."""
    store, counted, _clock, totals = build(tmp_path)
    store.put(evidence("1", conversation="a"))

    try:

        async def scenario() -> None:
            for _ in range(10):
                assert await totals.by_source(user_id="local") == {"fixture": (1, 1)}

        asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()

    assert counted.counts == 1


def test_an_idle_machine_costs_nothing_however_long_it_waits(tmp_path) -> None:
    """Time passing is not a reason to count; a new row is."""
    store, counted, clock, totals = build(tmp_path)
    store.put(evidence("1", conversation="a"))

    try:

        async def scenario() -> None:
            await totals.by_source(user_id="local")
            for _ in range(5):
                clock["now"] += 10.0  # long past the interval
                await totals.by_source(user_id="local")

        asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()

    assert counted.counts == 1
    # It did look, which is what makes the answer above trustworthy rather
    # than merely cheap.
    assert counted.mark_reads > 1


def test_a_new_row_is_reflected_once_the_interval_has_passed(tmp_path) -> None:
    store, counted, clock, totals = build(tmp_path)
    store.put(evidence("1", conversation="a"))

    try:

        async def scenario() -> tuple[dict, dict]:
            before = await totals.by_source(user_id="local")
            store.put(evidence("2", conversation="b"))
            clock["now"] += 3.0
            return before, await totals.by_source(user_id="local")

        before, after = asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()

    assert before == {"fixture": (1, 1)}
    assert after == {"fixture": (2, 2)}
    assert counted.counts == 2


def test_what_an_import_just_finished_writing_is_not_hidden_for_long(tmp_path) -> None:
    """Whatever is served stale, the finished numbers must arrive.

    An import ending with the screen showing a number from mid-import would
    be worse than a slow screen: it would be wrong and stay wrong.
    """
    store, _counted, clock, totals = build(tmp_path)

    try:

        async def scenario() -> dict:
            await totals.by_source(user_id="local")  # nothing yet
            for index in range(40):
                store.put(evidence(str(index), conversation=f"c{index // 4}"))
            clock["now"] += 2.0
            return await totals.by_source(user_id="local")

        after = asyncio.run(scenario())
    finally:
        shutdown_bulk_pool()

    assert after == {"fixture": (40, 10)}
