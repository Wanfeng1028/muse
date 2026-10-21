"""A3-03: the convergence seam every write entry shares."""

from __future__ import annotations

import pytest

from one_memory.memory_server.intake import (
    IntakeRejected,
    IntakeRequest,
    is_live,
    plan_intake,
)


def test_a_valid_request_becomes_a_write() -> None:
    write = plan_intake(
        IntakeRequest(
            internal_session_id="sess-1",
            first_round=1,
            last_round=5,
            evidence_ids=["e1"],
        )
    )
    assert write.internal_session_id == "sess-1"
    assert write.evidence_ids == ["e1"]


def test_missing_evidence_is_refused() -> None:
    """A write with nothing to point at cannot be verified later."""
    with pytest.raises(IntakeRejected):
        plan_intake(
            IntakeRequest(internal_session_id="s", first_round=1, last_round=5, evidence_ids=[])
        )


@pytest.mark.parametrize(
    ("first", "last"),
    [(0, 5), (5, 1), (3, 2)],
)
def test_a_bad_round_range_is_refused(first: int, last: int) -> None:
    with pytest.raises(IntakeRejected):
        plan_intake(
            IntakeRequest(
                internal_session_id="s",
                first_round=first,
                last_round=last,
                evidence_ids=["e1"],
            )
        )


def test_the_key_is_derived_so_a_replay_is_recognised() -> None:
    """A replay re-derives the same key, so it is not written twice."""

    def make() -> str:
        return plan_intake(
            IntakeRequest(
                internal_session_id="sess-1",
                first_round=1,
                last_round=5,
                evidence_ids=["e1"],
            )
        ).idempotency_key

    assert make() == make()


def test_a_different_batch_gets_a_different_key() -> None:
    def make(last: int) -> str:
        return plan_intake(
            IntakeRequest(
                internal_session_id="sess-1",
                first_round=1,
                last_round=last,
                evidence_ids=["e1"],
            )
        ).idempotency_key

    assert make(5) != make(10)


def test_live_requests_are_marked_live() -> None:
    """A person waiting on the result outranks background work."""
    write = plan_intake(
        IntakeRequest(
            internal_session_id="s",
            first_round=1,
            last_round=5,
            evidence_ids=["e1"],
            live=True,
        )
    )
    assert is_live(write) is True


def test_background_requests_are_normal() -> None:
    write = plan_intake(
        IntakeRequest(
            internal_session_id="s",
            first_round=1,
            last_round=5,
            evidence_ids=["e1"],
        )
    )
    assert is_live(write) is False


def test_evidence_ids_are_copied_not_aliased() -> None:
    """The caller's list must not be mutated by later handling."""
    evidence = ["e1"]
    write = plan_intake(
        IntakeRequest(internal_session_id="s", first_round=1, last_round=5, evidence_ids=evidence)
    )
    assert write.evidence_ids is not evidence
    assert write.evidence_ids == evidence
