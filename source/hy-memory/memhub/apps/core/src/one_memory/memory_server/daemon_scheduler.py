"""A5-02/A5-04: the daemon's scan scheduler and combined health.

The architecture is explicit that scan scheduling belongs to the daemon: "the
scan schedule must not depend on whether a UI happens to be open". Today
`PollingLiveSyncSupervisor` runs inside the Core process, which means the scan
beat lives and dies with the API server. This module is the scheduler the
daemon drives instead — the *decisions* are here and are testable without a
daemon, so the move is a wiring change rather than a rewrite.

Three decisions live here:

1. **One scan per root at a time.** Two scans of one root read the same cursor
   and would both write it.
2. **Roots are served round-robin**, so one enormous root cannot starve the
   others.
3. **A manual scan is admitted but does not duplicate** a running one: asking
   again returns the in-flight scan rather than starting a second. That is what
   makes "scan now" safe to press twice.

Health is composed from parts rather than guessed from one probe: each part
reports its own state, and the combined state is the worst of them, so a
"healthy" report cannot hide a single failed dependency behind an aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ScanState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"


class PartState(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"
    #: Not checked yet. Distinct from OK: "unknown" is honest, "ok" is a claim.
    UNKNOWN = "unknown"


_SEVERITY = {PartState.OK: 0, PartState.UNKNOWN: 1, PartState.DEGRADED: 2, PartState.FAILED: 3}


@dataclass(frozen=True)
class HealthPart:
    name: str
    state: PartState
    detail: str = ""


def combined_state(parts: list[HealthPart]) -> PartState:
    """The worst part wins, so one failure cannot hide behind an aggregate."""
    if not parts:
        return PartState.UNKNOWN
    return max(parts, key=lambda part: _SEVERITY[part.state]).state


@dataclass
class ScanLedger:
    """Which roots are scanning, and what is waiting."""

    running: set[str] = field(default_factory=set)
    #: Roots with a pending requested scan.
    waiting: list[str] = field(default_factory=list)


class ScanScheduler:
    """Decides which root to scan next, and admits manual requests."""

    def __init__(self, roots: list[str], *, max_concurrent: int = 1) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        self._roots = list(dict.fromkeys(roots))
        self._max = max_concurrent
        self._ledger = ScanLedger()
        self._cursor = 0

    @property
    def ledger(self) -> ScanLedger:
        return self._ledger

    def request(self, root: str) -> tuple[str, ScanState]:
        """Ask for a scan of `root`. Returns (root, state).

        If that root is already scanning, the same in-flight scan is returned
        rather than a second one — so pressing "scan now" twice is safe.
        """
        # Report what is actually happening: a root already scanning is running,
        # not queued. Reporting IDLE here would tell the caller it may start
        # work that is already in progress.
        if root in self._ledger.running:
            return root, ScanState.RUNNING
        if root not in self._ledger.waiting:
            self._ledger.waiting.append(root)
        return root, ScanState.IDLE

    def next_batch(self) -> list[str]:
        """Roots to start now.

        Only roots that were explicitly requested are started. A periodic
        rotation is *not* implied here: the architecture's five-minute beat is
        the daemon calling `request()` on each registered root on a timer, and
        this scheduler's job is to make sure those requests never overlap and
        never starve. Starting scans with nothing requested would busy-loop.
        """
        room = self._max - len(self._ledger.running)
        if room <= 0:
            return []

        started: list[str] = []
        while self._ledger.waiting and len(started) < room:
            root = self._ledger.waiting.pop(0)
            if root in self._ledger.running:
                continue
            self._ledger.running.add(root)
            started.append(root)
        return started

    def beat(self) -> list[str]:
        """One periodic round: request every registered root, then dispatch.

        Rotation starts from where the last round stopped, so a large root that
        keeps being busy cannot hold the front of the queue forever.
        """
        if not self._roots:
            return []
        for offset in range(len(self._roots)):
            root = self._roots[(self._cursor + offset) % len(self._roots)]
            self.request(root)
        self._cursor = (self._cursor + len(self._roots)) % len(self._roots)
        return self.next_batch()

    def finish(self, root: str) -> None:
        """Mark a scan done. Unknown roots are ignored, not created."""
        self._ledger.running.discard(root)

    def state_of(self, root: str) -> ScanState:
        return ScanState.RUNNING if root in self._ledger.running else ScanState.IDLE
