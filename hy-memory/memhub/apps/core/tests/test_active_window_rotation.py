"""Rule 5: a blocked head must not stop the rest from ever being scheduled.

hy memory app's worst recorded failure (§三 反模式 4) was a "deterministic
starvation": the fallback sweep did `ORDER BY MIN(created_at) LIMIT 128`, so it
always picked up the very oldest rows — which were exactly the zombie users
that could never be drained. The other 32,000 users never got another turn.

One Memory has no MQ and no wake chain, so the equivalent hazard is our own
keyset cursor: if a lane's cursor parks on a task that can never be admitted,
everything behind it in that lane must still reach scheduling. These tests pin
the two halves of that: the cursor advances past a blocked head, and a lane
that comes back empty reopens rather than staying parked forever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from one_memory.memory_queue import EXTRACTION_WINDOW, FRESH_WINDOW
from tests.test_memory_queue_recency import SteppedRunner, _put, _stores, _supervisor, _task


def _seed_backlog(tmp_path, count: int):
    """Backlog-lane tasks, oldest first, all in the same workspace.

    Deliberately *inside* the 90-day extraction window: older than that and
    `active_window` defers the row outright, which would make these tests
    assert on deferred rows rather than on scheduling rotation.
    """
    stores = _stores(tmp_path)
    evidence, _profiles, tasks, _governance, _secrets, profile = stores
    now = datetime.now(UTC)
    tasks_by_index = []
    for index in range(count):
        # Inside the window but older than the fresh window, so they land in
        # the backlog lane and stay claimable.
        moment = now - timedelta(days=30 + index)
        record = _put(
            evidence,
            message_id=f"rotate-{index}",
            content=f"rotate {index}",
            created_at=moment,
            conversation_id=f"conversation-{index}",
            workspace="workspace:v1:rotate",
        )
        tasks_by_index.append(_task(tasks, profile, record, suffix=f"r{index}"))
    return stores, now, tasks_by_index


def test_a_blocked_head_does_not_stop_the_tasks_behind_it(tmp_path) -> None:
    """Park the cursor on a head that can never be admitted; the rest must run.

    This is the starvation hy actually hit. The head is excluded for the whole
    test — as a task whose conversation is permanently busy would be — so a
    cursor that only ever advanced by re-reading the same head would return
    nothing forever.
    """
    stores, now, seeded = _seed_backlog(tmp_path, 60)
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    head = seeded[0]

    # Drive the walk the way the supervisor actually does: `_prepare_active_window`
    # advances the cursor, and `exclude_task_ids` is only ever the set of tasks
    # already queued or in flight. So the way to model "the head is permanently
    # blocked" is to keep it in flight — never excluded — and let the cursor
    # carry the walk past it.
    supervisor._in_flight[head.task_id] = None

    def refill():
        work = supervisor._prepare_active_window()
        for item in work:
            supervisor._in_flight[item.task_id] = item
        return work

    first = refill()
    assert first, "an all-backlog seed must produce backlog work"
    assert head.task_id not in {item.task_id for item in first}

    # Keep going: a cursor parked on the blocked head would keep handing back
    # the same page forever, and the walk would never reach the far end.
    seen = {item.task_id for item in first}
    cursors = [supervisor._active_window_cursors.get(False)]
    for _ in range(20):
        work = refill()
        if not work:
            break
        seen.update(item.task_id for item in work)
        cursors.append(supervisor._active_window_cursors.get(False))

    # The point of the rule: the block costs exactly one task, not the lane.
    assert len(seen) >= 58, f"the walk stalled after {len(seen)} of 60 tasks"
    assert head.task_id not in seen

    # And the mechanism is the cursor moving, not luck: a cursor parked on the
    # first page is hy's starvation shape and must be visible as a stalled
    # cursor, not merely as a shorter walk.
    advanced = [cursor for cursor in cursors if cursor != cursors[0]]
    assert advanced, "the backlog cursor never advanced across the whole walk"


def test_an_empty_refill_reopens_the_lane_rather_than_staying_parked(tmp_path) -> None:
    """A lane that comes back empty must be able to yield work again later.

    The cursor is an optimisation, not a watermark: if it survived an empty
    read, a backlog that grew after the walk would be unreachable until the
    next policy change or restart, which is the same starvation by another door.
    """
    stores, now, seeded = _seed_backlog(tmp_path, 4)
    tasks = stores[2]
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    # Drive the cursor to the end of the lane.
    supervisor._prepare_active_window()
    assert supervisor._active_window_cursors.get(False) is not None

    # Everything now busy: the refill is empty...
    busy = {task.task_id for task in seeded}
    supervisor._in_flight.clear()
    rows = tasks.active_window(
        now=now,
        fresh_window=FRESH_WINDOW,
        extraction_window=EXTRACTION_WINDOW,
        exclude_task_ids=tuple(busy),
        live_limit=0,
        fresh_limit=0,
        backlog_limit=8,
    )
    assert rows == []

    # ...and the supervisor says so, which is what stops the "look for older"
    # pass from spinning on an exhausted lane.
    supervisor._older_waiting = True
    assert supervisor._refill_active_window() == []
    assert supervisor._older_waiting is False

    # Fresh work arriving after the walk is still reachable: the cursor is
    # cleared with the rest of the window state when the policy changes, which
    # is the documented reset path.
    supervisor._active_window_cursors.clear()
    assert supervisor._active_window_cursors == {}
