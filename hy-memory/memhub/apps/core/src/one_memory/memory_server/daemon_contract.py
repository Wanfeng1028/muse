"""A5-01/A5-03: the daemon's boundary and its independent switches.

A5-01 asks for one owner of process lifecycle. Today Desktop, CLI and Core each
hold some of it, which is how a runtime ends up started twice or stopped by the
wrong client. The rule here is narrow and checkable: **exactly one component may
own starting and stopping a given process**, and ownership is claimed, not
assumed — a second claimant is refused rather than silently taking over.

A5-03 asks for three grants that stay independent (source read, model egress,
host read). They are kept as three separate switches on purpose: collapsing them
into one "connected" flag is what previously made a failed query render as
"0 apps connected" — a refusal to read was displayed as a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Owner(StrEnum):
    """Who may start or stop a process."""

    DAEMON = "daemon"
    DESKTOP = "desktop"
    CLI = "cli"
    CORE = "core"


class Process(StrEnum):
    MYSQL = "mysql"
    SERVER = "server"
    BROKER = "broker"


class AlreadyOwned(RuntimeError):
    """Another component already owns this process."""


@dataclass(frozen=True)
class Claim:
    owner: Owner
    process: Process


class OwnershipLedger:
    """Records who owns which process. One owner each, claimed explicitly."""

    def __init__(self) -> None:
        self._claims: dict[Process, Owner] = {}

    def claim(self, owner: Owner, process: Process) -> Claim:
        """Claim ownership, or refuse if someone else already holds it.

        Refusing is the point: a silent takeover means two components both
        believe they may stop the same process.
        """
        current = self._claims.get(process)
        if current is not None and current is not owner:
            raise AlreadyOwned(f"{process} is already owned by {current}")
        self._claims[process] = owner
        return Claim(owner, process)

    def release(self, owner: Owner, process: Process) -> None:
        """Release only your own claim. Releasing another's would let a client
        stop a process it does not own."""
        if self._claims.get(process) is owner:
            del self._claims[process]

    def owner_of(self, process: Process) -> Owner | None:
        return self._claims.get(process)

    def may_control(self, owner: Owner, process: Process) -> bool:
        return self._claims.get(process) is owner


class Switch(StrEnum):
    ON = "on"
    OFF = "off"


class Grant(StrEnum):
    SOURCE_READ = "source_read"
    MODEL_EGRESS = "model_egress"
    HOST_READ = "host_read"


@dataclass(frozen=True)
class GrantState:
    """The three grants, kept apart.

    `desired` is what the user asked for; `actual` is what is in force. They are
    separate fields because showing the first as if it were the second is how a
    failed read was rendered as "connected".
    """

    desired: dict[Grant, Switch] = field(default_factory=lambda: {g: Switch.OFF for g in Grant})
    actual: dict[Grant, Switch] = field(default_factory=lambda: {g: Switch.OFF for g in Grant})

    def is_actually_on(self, grant: Grant) -> bool:
        return self.actual.get(grant) is Switch.ON

    def is_desired_on(self, grant: Grant) -> bool:
        return self.desired.get(grant) is Switch.ON


def new_state() -> GrantState:
    """All three grants off, and consistent."""
    return GrantState()


def with_desired(state: GrantState, grant: Grant, value: Switch) -> GrantState:
    """Set intent only. Actual changes when the daemon reconciles, not here.

    That separation is the whole point: a switch the user just turned on is not
    yet in force, and must not be reported as if it were.
    """
    desired = dict(state.desired)
    desired[grant] = value
    return GrantState(desired=desired, actual=dict(state.actual))


def reconcile(state: GrantState) -> GrantState:
    """Drive actual toward desired.

    Applied as a whole so the three grants cannot go in piecemeal: a partial
    application would leave one grant in force after the user revoked it.
    """
    return GrantState(desired=dict(state.desired), actual=dict(state.desired))
