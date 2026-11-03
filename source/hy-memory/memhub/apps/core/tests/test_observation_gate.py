"""A7-02: the gate that stops "nothing changed" from being certified blind.

The dangerous case is not a wrong CHANGED; it is an UNCHANGED reported by a
probe that could never have moved. That reading certifies an absence, and this
project has already been bitten by exactly that (two equal readings taken as
"no change" while the probe was pointed at the wrong thing).
"""

from __future__ import annotations

from one_memory.memory_server.observation_gate import (
    Control,
    GateResult,
    Probe,
    Verdict,
    gate_all,
    judge,
    liveness,
    may_claim_unchanged,
)


def _probe(name: str, before: int, after: int) -> Probe:
    return Probe(name=name, before=before, after=after)


def test_a_moving_control_means_the_probe_is_alive() -> None:
    assert liveness(Control(_probe("files_opened", 0, 6))) is True


def test_a_still_control_means_the_probe_is_blind() -> None:
    """If the change is present and the probe did not move, it cannot observe."""
    assert liveness(Control(_probe("files_opened", 0, 0))) is False


def test_movement_with_a_live_control_is_changed() -> None:
    verdict = judge(
        observed=_probe("files_opened", 0, 6),
        control=Control(_probe("files_opened", 0, 6)),
    )
    assert verdict is Verdict.CHANGED


def test_no_movement_with_a_live_control_is_unchanged() -> None:
    verdict = judge(
        observed=_probe("files_opened", 0, 0),
        control=Control(_probe("files_opened", 0, 6)),
    )
    assert verdict is Verdict.UNCHANGED


def test_a_blind_probe_yields_unproven_not_unchanged() -> None:
    """'We did not check' must not collapse into 'nothing changed'."""
    verdict = judge(
        observed=_probe("files_opened", 0, 0),
        control=Control(_probe("files_opened", 0, 0)),
    )
    assert verdict is Verdict.UNPROVEN
    assert verdict is not Verdict.UNCHANGED


def test_a_blind_probe_may_not_report_no_duplication() -> None:
    """The concrete case: claiming 'no duplicate writes' from a blind probe."""
    entitled = may_claim_unchanged(
        observed=_probe("jobs_created", 20, 20),
        control=Control(_probe("jobs_created", 20, 20)),
    )
    assert entitled is False


def test_a_live_probe_may_report_no_duplication() -> None:
    entitled = may_claim_unchanged(
        observed=_probe("jobs_created", 20, 20),
        control=Control(_probe("jobs_created", 20, 24)),
    )
    assert entitled is True


def test_gate_all_names_the_blind_probe() -> None:
    results = gate_all(
        [
            (
                _probe("evidence_stored", 4, 24),
                Control(_probe("evidence_stored", 4, 24)),
            ),
            (_probe("jobs_created", 20, 20), Control(_probe("jobs_created", 20, 20))),
        ]
    )
    assert isinstance(results[0], GateResult)
    assert results[0].verdict is Verdict.CHANGED
    assert results[1].verdict is Verdict.UNPROVEN
    assert "cannot observe" in results[1].reason


def test_gate_all_on_nothing_is_nothing() -> None:
    assert gate_all([]) == []
