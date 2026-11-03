"""A4 gate 7: only the holder of a root's scan lease may commit its cursor.

Two scanners on one root both read the same cursor and both compute changed
files. If both commit, the second write is based on a cursor the first already
advanced — so the tail is either ingested twice or skipped entirely, depending
on which write lands last. Neither outcome is detectable from the cursor table
alone afterwards, which is why the gate has to be in the write path and not in
a reconciliation job.

This module is deliberately tiny and dependency-free: the lease decision is a
pure function of (who holds the root, who is asking), so it can be tested
without MySQL, without a daemon, and without a clock.
"""

from __future__ import annotations

from dataclasses import dataclass

from one_memory.memory_server.scanner.classifier import StoredFileCursor
from one_memory.memory_server.scanner.service import CursorStore


class LeaseRefused(RuntimeError):
    """Raised when a cursor write is attempted without holding the lease."""


@dataclass(frozen=True)
class ScanLease:
    """One scanner's right to write cursors for one root."""

    root: str
    owner: str


class LeaseRegistry:
    """Which scanner currently holds which root.

    Modelling the registry in memory keeps the decision testable. The durable
    form is a row with an expiry (the same shape `memory_server.queue` uses for
    job leases), so a scanner that dies does not hold a root forever; what
    matters for this gate is only that *exactly one* owner exists at a time.
    """

    def __init__(self) -> None:
        self._holders: dict[str, str] = {}

    def acquire(self, root: str, owner: str) -> ScanLease:
        """Take the lease, or refuse if another scanner holds it.

        Refusing is the point. Silently transferring the lease would put two
        scanners in the commit path at once, which is exactly the failure this
        gate exists to prevent; the second scanner should instead not scan.
        """
        current = self._holders.get(root)
        if current is not None and current != owner:
            raise LeaseRefused(f"root {root} is leased to {current}, not {owner}")
        self._holders[root] = owner
        return ScanLease(root, owner)

    def release(self, lease: ScanLease) -> None:
        """Release only your own lease."""
        if self._holders.get(lease.root) == lease.owner:
            del self._holders[lease.root]

    def holder_of(self, root: str) -> str | None:
        return self._holders.get(root)

    def holds(self, root: str, owner: str) -> bool:
        return self._holders.get(root) == owner


class LeasedCursorStore:
    """A `CursorStore` whose writes are gated on holding the root's lease.

    Reads stay open: a scanner that lost the lease still needs to see cursors
    to decide, and refusing reads would only make it re-open every file.
    Writes are gated, because a stale cursor commit is the actual corruption.
    """

    def __init__(
        self,
        inner: CursorStore,
        registry: LeaseRegistry,
        root: str,
        owner: str,
    ) -> None:
        self._inner = inner
        self._registry = registry
        self._root = root
        self._owner = owner
        #: Count of writes refused. Observable so a test can assert the gate
        #: fired rather than merely that the cursor did not change.
        self.refused_writes = 0

    def get_many(self, keys: list[str]) -> dict[str, StoredFileCursor]:
        return self._inner.get_many(keys)

    def put_many(self, cursors: dict[str, StoredFileCursor]) -> None:
        if not self._registry.holds(self._root, self._owner):
            self.refused_writes += 1
            raise LeaseRefused(
                f"{self._owner} no longer holds the lease on {self._root}; "
                "refusing to commit a cursor read before the lease was lost"
            )
        self._inner.put_many(cursors)
