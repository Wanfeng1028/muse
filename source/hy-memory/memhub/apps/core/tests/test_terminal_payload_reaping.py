"""Rule 14: dead-end payloads are actually reaped, not just reapable.

`MemoryTaskStore.clear_terminal_payloads` was written and tested but had
**zero callers in `src/`** (09-27 audit: `rg clear_terminal_payloads src/` →
only its own definition). A function nobody calls does not reclaim anything,
and the backlog it exists for grows without bound.

The wiring belongs where the other bounded maintenance already happens —
`prepare_resume`, which is the one path every start and every policy change
goes through. Keeping it bounded matters more than where it lives: this is a
write, and the single writer is the thing the whole database decision rests on.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from one_memory.memory_tasks import MemoryTaskStatus
from tests.test_memory_queue_recency import SteppedRunner, _stores, _supervisor


def _seed(store, task_id: str, status: MemoryTaskStatus) -> None:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO memory_tasks (task_id, request_id, user_id, kind, "
            "input_ref, status, profile_id, profile_revision, "
            "profile_snapshot_json, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                f"req:{task_id}",
                "local",
                "extract",
                "evidence-1",
                str(status),
                "profile-1",
                1,
                "{}",
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO memory_task_inputs VALUES (?,?)",
            (task_id, '[{"evidence_id":"e1"}]'),
        )


def test_resume_reaps_dead_end_payloads(tmp_path) -> None:
    """The wiring: a start actually reclaims the space.

    Before this the function existed, was tested, and was called by nobody —
    so a machine with 1759 dead-end tasks kept every one of their inputs.
    """
    stores = _stores(tmp_path)
    tasks = stores[2]
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    _seed(tasks, "cancelled-1", MemoryTaskStatus.CANCELLED)
    _seed(tasks, "failed-1", MemoryTaskStatus.FAILED)

    supervisor.prepare_resume()

    assert tasks.inputs("cancelled-1") == ()
    assert tasks.inputs("failed-1") == ()


def test_reaping_leaves_completed_inputs_alone(tmp_path) -> None:
    """The half that must not regress while wiring the other half.

    Completed inputs are what a coverage check compares against, so reaping
    them would make a failed verification read as a pass. Wiring the call is
    exactly when this is easiest to get wrong.
    """
    stores = _stores(tmp_path)
    tasks = stores[2]
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    _seed(tasks, "done-1", MemoryTaskStatus.COMPLETED)

    supervisor.prepare_resume()

    assert tasks.inputs("done-1") == ({"evidence_id": "e1"},)


def test_reaping_runs_after_policy_stopped_tasks_are_reclassified(tmp_path, monkeypatch) -> None:
    """Order: convert, then reap.

    A task recorded as `failed` because a policy was stopped is really a
    cancellation, and it only becomes one inside `reclassify_policy_stopped`.
    Reaping first would walk past exactly the backlog this wiring exists for —
    which on the production corpus is 1759 rows — and leave every payload in
    place. The order is asserted, not assumed.
    """
    stores = _stores(tmp_path)
    tasks = stores[2]
    supervisor = _supervisor(tmp_path, stores, SteppedRunner())

    calls: list[str] = []
    reclassify = tasks.reclassify_policy_stopped
    clear = tasks.clear_terminal_payloads
    monkeypatch.setattr(
        tasks, "reclassify_policy_stopped", lambda: (calls.append("reclassify"), reclassify())[1]
    )
    monkeypatch.setattr(
        tasks, "clear_terminal_payloads", lambda: (calls.append("clear"), clear())[1]
    )

    supervisor.prepare_resume()

    assert calls == ["reclassify", "clear"], f"maintenance ran in the wrong order: {calls}"
