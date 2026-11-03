"""A7-02: prove the probe can see a change before trusting "nothing changed".

This is the project's D2 rule, made mechanical. The failure it guards is
specific and has already happened here: two equal readings were taken as
"no change", when in fact the probe was pointed at the wrong thing and could
never have moved. A green "nothing happened" from a probe that cannot observe
is worse than no check at all — it certifies the absence.

So before a "did not happen" claim is accepted, the same probe must be shown
to move when the change *is* present. That is the liveness control, and it is
required, not optional:

    moved_on_control() is True  ->  a later "no movement" is evidence
    moved_on_control() is False ->  the probe is blind; the claim is void

Only three verdicts exist, and `UNPROVEN` is one of them on purpose. Collapsing
"we did not check" into "nothing changed" is exactly the mistake this exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    #: The probe never demonstrated it could move. "Unchanged" would be a guess.
    UNPROVEN = "unproven"


@dataclass(frozen=True)
class Probe:
    """One measured quantity, before and after."""

    name: str
    before: int
    after: int

    @property
    def moved(self) -> bool:
        return self.before != self.after


@dataclass(frozen=True)
class Control:
    """The same probe measured where the change is known to be present."""

    probe: Probe


def liveness(control: Control) -> bool:
    """Whether the probe demonstrated it can observe the change at all."""
    return control.probe.moved


def judge(*, observed: Probe, control: Control) -> Verdict:
    """Decide what an observed reading means.

    `UNPROVEN` when the control did not move: the probe is blind, so neither
    CHANGED nor UNCHANGED can be concluded from it.
    """
    if not liveness(control):
        return Verdict.UNPROVEN
    return Verdict.CHANGED if observed.moved else Verdict.UNCHANGED


def may_claim_unchanged(*, observed: Probe, control: Control) -> bool:
    """Whether "nothing changed" is a claim you are entitled to make."""
    return judge(observed=observed, control=control) is Verdict.UNCHANGED


@dataclass(frozen=True)
class GateResult:
    probe: str
    verdict: Verdict
    reason: str


def gate_all(pairs: list[tuple[Probe, Control]]) -> list[GateResult]:
    """Judge several probes, so a claim can rest on more than one reading."""
    results: list[GateResult] = []
    for observed, control in pairs:
        verdict = judge(observed=observed, control=control)
        if verdict is Verdict.UNPROVEN:
            reason = (
                f"control for {observed.name} did not move; the probe cannot observe this change"
            )
        elif verdict is Verdict.CHANGED:
            reason = f"{observed.name}: {observed.before} -> {observed.after}"
        else:
            reason = f"{observed.name} stayed at {observed.before}, control moved"
        results.append(GateResult(observed.name, verdict, reason))
    return results
