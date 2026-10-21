from __future__ import annotations

from one_memory import memory_processing


def _failure() -> RuntimeError:
    try:
        memory_processing.memory_task_timeout_seconds("database is locked")  # type: ignore[arg-type]
    except ValueError as error:
        return RuntimeError("database is locked").with_traceback(error.__traceback__)
    raise AssertionError("expected invalid timeout")


def test_conversation_prepare_failure_includes_safe_message_and_stack(monkeypatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(memory_processing, "diagnostic_event", lambda **event: events.append(event))

    memory_processing._report_conversation_prepare_failure("workbuddy", _failure())

    assert events[0]["error_type"] == "RuntimeError"
    assert events[0]["details"] == {
        "source_id": "workbuddy",
        "reason": "database is locked",
    }
    assert events[0]["safe_stack"]
    assert "/Users/" not in str(events[0]["safe_stack"])


def test_deletion_sync_failure_includes_safe_message_and_stack(monkeypatch) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(memory_processing, "diagnostic_event", lambda **event: events.append(event))

    memory_processing._report_deletion_sync_failure(_failure())

    assert events[0]["error_type"] == "RuntimeError"
    assert events[0]["details"] == {"reason": "database is locked"}
    assert events[0]["safe_stack"]
