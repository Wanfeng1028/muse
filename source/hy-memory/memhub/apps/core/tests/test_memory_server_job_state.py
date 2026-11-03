"""A2-05: the job state machine, especially the parts that protect `unknown`.

`unknown` is the whole reason this machine exists. A0-03 measured that HY has
no idempotency key, so an unresolved write may be neither retried nor dropped.
These tests pin that, and pin that no illegal path can quietly pass.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.job_state import (
    MAX_ATTEMPTS,
    TERMINAL_STATES,
    IllegalTransition,
    JobEvent,
    JobState,
    can_retry,
    is_terminal,
    next_state,
)


def test_pending_claims_to_running() -> None:
    assert next_state(JobState.PENDING, JobEvent.CLAIM) is JobState.RUNNING


def test_success_completes() -> None:
    assert next_state(JobState.RUNNING, JobEvent.SUCCEED) is JobState.COMPLETED


def test_failure_fails() -> None:
    assert next_state(JobState.RUNNING, JobEvent.FAIL) is JobState.FAILED


def test_indeterminate_becomes_unknown() -> None:
    """HY returned but we cannot prove it committed: that is `unknown`."""
    assert next_state(JobState.RUNNING, JobEvent.INDETERMINATE) is JobState.UNKNOWN


def test_unknown_is_not_terminal() -> None:
    """`unknown` still needs work, so it must not be treated as finished."""
    assert not is_terminal(JobState.UNKNOWN)
    assert JobState.UNKNOWN not in TERMINAL_STATES


def test_unknown_can_only_be_resolved_by_inquiry() -> None:
    """An inquiry may close it either way; a blind write may not."""
    assert next_state(JobState.UNKNOWN, JobEvent.RESOLVED) is JobState.COMPLETED
    assert next_state(JobState.UNKNOWN, JobEvent.FAIL) is JobState.FAILED
    assert next_state(JobState.UNKNOWN, JobEvent.GIVE_UP) is JobState.DEAD


def test_terminal_states_are_closed() -> None:
    """Nothing may restart a finished job; that would duplicate a memory."""
    for state in TERMINAL_STATES:
        for event in JobEvent:
            with pytest.raises(IllegalTransition):
                next_state(state, event)


def test_no_silent_no_op_on_illegal_events() -> None:
    """An invalid event must raise, not be ignored.

    A quiet no-op would let a bug look like a successful transition, which is
    how a job ends up run twice without anyone noticing.
    """
    with pytest.raises(IllegalTransition):
        next_state(JobState.PENDING, JobEvent.SUCCEED)
    with pytest.raises(IllegalTransition):
        next_state(JobState.COMPLETED, JobEvent.CLAIM)


def test_failed_jobs_retry_up_to_the_limit() -> None:
    assert can_retry(JobState.FAILED, attempts=0) is True
    assert can_retry(JobState.FAILED, attempts=MAX_ATTEMPTS - 1) is True
    assert can_retry(JobState.FAILED, attempts=MAX_ATTEMPTS) is False


def test_unknown_is_not_retried_as_a_write() -> None:
    """Retrying an unknown write would duplicate the memory.

    A0-03 measured that the SDK accepts a replay without dedup, so the only
    safe move on `unknown` is to inquire, not to write again.
    """
    assert can_retry(JobState.UNKNOWN, attempts=0) is False
    with pytest.raises(IllegalTransition):
        next_state(JobState.UNKNOWN, JobEvent.RETRY)


def test_completed_and_dead_never_retry() -> None:
    for state in (JobState.COMPLETED, JobState.DEAD, JobState.CANCELLED):
        assert can_retry(state, attempts=0) is False


def test_retry_returns_to_pending() -> None:
    assert next_state(JobState.FAILED, JobEvent.RETRY) is JobState.PENDING


def test_cancel_from_pending_or_running() -> None:
    assert next_state(JobState.PENDING, JobEvent.CANCEL) is JobState.CANCELLED
    assert next_state(JobState.RUNNING, JobEvent.CANCEL) is JobState.CANCELLED


def test_happy_path_and_unknown_path_are_both_walkable() -> None:
    happy = JobState.PENDING
    for event in (JobEvent.CLAIM, JobEvent.SUCCEED):
        happy = next_state(happy, event)
    assert happy is JobState.COMPLETED

    unclear = JobState.PENDING
    for event in (JobEvent.CLAIM, JobEvent.INDETERMINATE):
        unclear = next_state(unclear, event)
    assert unclear is JobState.UNKNOWN
    assert next_state(unclear, JobEvent.RESOLVED) is JobState.COMPLETED
