"""A4 gate 7: two scanners, one root — only the lease holder commits.

The architecture states this as gate 7 and it is the one gate that protects
data rather than speed: a cursor committed from a stale read either duplicates
a tail or drops it, and neither is visible from the cursor table afterwards.

So these tests assert the write is *refused*, not merely that a counter moved.
A gate that swallowed the write and returned normally would look like a
successful no-op while the losing scanner went on to enqueue real writes based
on a cursor it was never allowed to advance.
"""

from __future__ import annotations

import pytest

from one_memory.memory_server.scanner.classifier import StoredFileCursor
from one_memory.memory_server.scanner.lease import (
    LeasedCursorStore,
    LeaseRefused,
    LeaseRegistry,
    ScanLease,
)
from one_memory.memory_server.scanner.service import InMemoryCursorStore


def _cursor(key: str, checkpoint: int) -> StoredFileCursor:
    return StoredFileCursor(
        file_key=key,
        file_identity=f"{key}-inode",
        observed_size=10,
        observed_modified_ns=1_000,
        checkpoint=checkpoint,
        read_to_end=True,
        anchor=None,
    )


@pytest.fixture()
def registry() -> LeaseRegistry:
    return LeaseRegistry()


def test_a_second_scanner_cannot_take_the_lease(registry: LeaseRegistry) -> None:
    """Two holders would put two scanners in the commit path at once."""
    registry.acquire("/root", "scanner-a")
    with pytest.raises(LeaseRefused, match="scanner-a"):
        registry.acquire("/root", "scanner-b")
    assert registry.holder_of("/root") == "scanner-a"


def test_the_same_owner_may_re_acquire(registry: LeaseRegistry) -> None:
    """Re-entering your own lease is not a conflict."""
    registry.acquire("/root", "scanner-a")
    registry.acquire("/root", "scanner-a")
    assert registry.holder_of("/root") == "scanner-a"


def test_release_only_your_own_lease(registry: LeaseRegistry) -> None:
    """A client must not be able to stop a scanner it does not own."""
    lease = registry.acquire("/root", "scanner-a")
    registry.release(lease)
    assert registry.holder_of("/root") is None

    registry.acquire("/root", "scanner-a")
    # A lease object naming a different owner: releasing it must be a no-op.
    foreign_owner = ScanLease(root="/root", owner="scanner-b")
    registry.release(foreign_owner)
    assert registry.holder_of("/root") == "scanner-a"


def test_the_lease_holder_commits(registry: LeaseRegistry) -> None:
    inner = InMemoryCursorStore()
    registry.acquire("/root", "scanner-a")
    store = LeasedCursorStore(inner, registry, "/root", "scanner-a")

    store.put_many({"k": _cursor("k", 42)})

    assert store.get_many(["k"])["k"].checkpoint == 42
    assert store.refused_writes == 0


def test_a_scanner_that_lost_the_lease_cannot_commit(registry: LeaseRegistry) -> None:
    """The gate itself: the losing scanner's write is refused, not applied.

    Asserted on the exception *and* on the cursor table, because a gate that
    dropped the write silently would pass the second half while still leaving
    the caller believing it had committed.
    """
    inner = InMemoryCursorStore()
    lease_a = registry.acquire("/root", "scanner-a")
    store_a = LeasedCursorStore(inner, registry, "/root", "scanner-a")
    store_b = LeasedCursorStore(inner, registry, "/root", "scanner-b")

    store_a.put_many({"k": _cursor("k", 10)})
    # The lease moves: scanner-a finished and scanner-b is now the owner.
    registry.release(lease_a)
    registry.acquire("/root", "scanner-b")

    store_b.put_many({"k": _cursor("k", 20)})
    assert inner.get_many(["k"])["k"].checkpoint == 20

    # scanner-a woke up late and tries to commit the cursor it read earlier.
    with pytest.raises(LeaseRefused):
        store_a.put_many({"k": _cursor("k", 99)})

    assert store_a.refused_writes == 1
    assert inner.get_many(["k"])["k"].checkpoint == 20, "the stale cursor must not land"


def test_reads_stay_open_without_the_lease(registry: LeaseRegistry) -> None:
    """A scanner that lost the lease still needs to see cursors.

    Refusing reads would not make it safer; it would make it re-open every
    file, which is the cost the metadata gate exists to avoid.
    """
    inner = InMemoryCursorStore()
    inner.put_many({"k": _cursor("k", 7)})
    store = LeasedCursorStore(inner, registry, "/root", "scanner-a")

    assert store.get_many(["k"])["k"].checkpoint == 7


def test_two_roots_do_not_block_each_other(registry: LeaseRegistry) -> None:
    """The lease is per root. Serialising unrelated roots would be a
    throughput regression mistaken for safety."""
    registry.acquire("/root-1", "scanner-a")
    registry.acquire("/root-2", "scanner-b")

    assert registry.holder_of("/root-1") == "scanner-a"
    assert registry.holder_of("/root-2") == "scanner-b"
