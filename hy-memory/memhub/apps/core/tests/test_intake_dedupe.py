"""A4-07: hook and scan share one identity, so order cannot duplicate."""

from __future__ import annotations

from one_memory.memory_server.intake_dedupe import (
    EnqueueLedger,
    batch_key,
    enqueue_batch,
    enqueue_message,
    message_key,
    replay,
)


def test_the_key_ignores_the_arrival_path() -> None:
    """If hook and scan produced different keys, one batch would become two."""
    assert batch_key(session="s1", first_round=1, last_round=5) == "s1:1-5"


def test_the_same_batch_from_both_paths_enqueues_once() -> None:
    ledger = EnqueueLedger()
    assert enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="hook") is True
    assert enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="scan") is False
    assert len(ledger.jobs) == 1


def test_replay_is_one_in_hook_first_order() -> None:
    assert replay(session="s1", first_round=1, last_round=5) == 1


def test_replay_is_one_in_scan_first_order() -> None:
    """A dedupe that only works one way round is a race, not a fix."""
    ledger = EnqueueLedger()
    assert enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="scan") is True
    assert enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="hook") is False
    assert len(ledger.jobs) == 1


def test_different_batches_are_distinct() -> None:
    ledger = EnqueueLedger()
    enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="scan")
    enqueue_batch(ledger, session="s1", first_round=6, last_round=10, path="scan")
    assert len(ledger.jobs) == 2


def test_sessions_are_isolated() -> None:
    ledger = EnqueueLedger()
    enqueue_batch(ledger, session="s1", first_round=1, last_round=5, path="scan")
    enqueue_batch(ledger, session="s2", first_round=1, last_round=5, path="scan")
    assert len(ledger.jobs) == 2


def test_messages_dedupe_on_identity() -> None:
    ledger = EnqueueLedger()
    kwargs = {"session": "s1", "ordinal": 3, "content_hash": "abc"}
    assert enqueue_message(ledger, path="hook", **kwargs) is True
    assert enqueue_message(ledger, path="scan", **kwargs) is False


def test_a_changed_content_hash_is_a_new_message() -> None:
    """An edited turn must not be suppressed as a duplicate."""
    ledger = EnqueueLedger()
    enqueue_message(ledger, session="s1", ordinal=3, content_hash="abc", path="hook")
    assert enqueue_message(ledger, session="s1", ordinal=3, content_hash="xyz", path="scan") is True


def test_the_message_key_shape() -> None:
    assert message_key(session="s1", ordinal=3, content_hash="abc") == "s1:3:abc"
