"""A1-04/A2: the port a database store implements, and a conformance check.

`database_access.MainDatabase` is the SQLite implementation MemHub uses. Per
D56 the business store is SQLite-only (overriding D53's MySQL-only decision);
the MySQL modules remain present but `store_binding` never resolves to them.
The port still earns its keep: 142 call sites across 46 modules depend on this
shape, so naming it keeps every call site engine-neutral even though only one
engine is bound.

So the port is named first. Both implementations satisfy the same four
operations, and `conforms` checks that mechanically:

    write()   — a checked-out writer, committed on success
    read()    — a checked-out reader
    back_up() — a consistent copy
    stats()   — observable counters

Naming the port does not migrate anything by itself. What it buys is that the
migration becomes "swap which implementation is bound", verifiable in one place,
instead of "rewrite every call site".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any


class StoreStats:
    """Counters a store exposes so contention can be observed, not guessed."""

    def __init__(
        self,
        *,
        writers: int = 0,
        readers: int = 0,
        write_waits: int = 0,
        read_waits: int = 0,
        refused: int = 0,
    ) -> None:
        self.writers = writers
        self.readers = readers
        self.write_waits = write_waits
        self.read_waits = read_waits
        self.refused = refused

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StoreStats):
            return NotImplemented
        return self.__dict__ == other.__dict__

    def __repr__(self) -> str:
        return f"StoreStats({self.__dict__})"


class Store(ABC):
    """What every store must do, regardless of engine."""

    @abstractmethod
    def write(self, *, busy_timeout_ms: int | None = None) -> AbstractAsyncContextManager[Any]:
        """A writer. Nested checkout must raise; commit on clean exit."""

    @abstractmethod
    def read(self, *, busy_timeout_ms: int | None = None) -> AbstractAsyncContextManager[Any]:
        """A reader."""

    @abstractmethod
    def back_up(self, target: Path) -> None:
        """A consistent copy. Never deletes or rewrites the live data."""

    @abstractmethod
    def stats(self) -> StoreStats:
        """Counters for contention."""

    @abstractmethod
    def close(self) -> None:
        """Release connections."""


def conforms(candidate: type) -> tuple[bool, tuple[str, ...]]:
    """Whether a class can stand in as a store.

    Checked structurally rather than by isinstance, so a store that cannot
    import this module — or one written before it — can still be validated.
    """
    required = ("write", "read", "back_up", "stats", "close")
    missing = tuple(name for name in required if not callable(getattr(candidate, name, None)))
    return (not missing), missing


def iter_checkouts(store: Store) -> Iterator[str]:
    """Names the checkout kinds, for tests that must cover both."""
    yield "write"
    yield "read"
