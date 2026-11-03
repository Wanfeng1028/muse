"""A frozen Harness produces no extraction tasks.

Unit-level, on the one method that decides it, because driving a whole
backfill needs a model profile, a permission receipt and a bridge; the
decision under test is only "is this conversation's source allowed".
"""

from types import SimpleNamespace

import pytest

from one_memory.memory_processing import MemoryProcessingSupervisor


def _record(source_id: str) -> SimpleNamespace:
    return SimpleNamespace(source_id=source_id)


def _supervisor(permitted) -> MemoryProcessingSupervisor:
    supervisor = MemoryProcessingSupervisor.__new__(MemoryProcessingSupervisor)
    supervisor.source_writes_permitted = permitted
    return supervisor


def test_an_enabled_harness_is_kept() -> None:
    supervisor = _supervisor(lambda source_id: True)

    assert supervisor._source_may_write([_record("cursor")]) is True


def test_a_frozen_harness_is_skipped() -> None:
    supervisor = _supervisor(lambda source_id: False)

    assert supervisor._source_may_write([_record("cursor")]) is False


def test_only_the_conversation_s_own_harness_decides() -> None:
    """A closed source must not stop another one's conversations."""
    supervisor = _supervisor(lambda source_id: source_id != "cursor")

    assert supervisor._source_may_write([_record("claude-code")]) is True
    assert supervisor._source_may_write([_record("cursor")]) is False


def test_a_mixed_conversation_follows_its_frozen_harness() -> None:
    """One closed member is enough: the chunk would carry its content."""
    supervisor = _supervisor(lambda source_id: source_id != "cursor")

    assert supervisor._source_may_write([_record("claude-code"), _record("cursor")]) is False


def test_without_a_switch_everything_is_processable() -> None:
    """A Core or a test that wires none keeps the behaviour it had before."""
    supervisor = _supervisor(None)

    assert supervisor._source_may_write([_record("cursor")]) is True


def test_an_empty_conversation_is_not_a_reason_to_skip() -> None:
    supervisor = _supervisor(lambda source_id: False)

    assert supervisor._source_may_write([]) is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
