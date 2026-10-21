"""A session file on disk is not proof that the session is online."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from one_memory.session_lease import SessionLease
from one_memory.session_registry import SessionRegistry


def _session(tmp_path):
    path = tmp_path / "one-memory.sqlite3"
    path.write_bytes(b"")
    registry = SessionRegistry(path)
    registry.initialize()
    lease = SessionLease(path)
    lease.initialize()
    opened = registry.open(
        installation_id=str(uuid4()),
        host_id="workbuddy",
        native_session_id="session-a",
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    return lease, opened.session_key


def test_a_present_file_does_not_keep_an_expired_session_online(tmp_path) -> None:
    lease, session_key = _session(tmp_path)
    marker = tmp_path / "session.jsonl"
    marker.write_text("still on disk")
    started = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    lease.beat(session_key, pid=42, generation=1, now=started, ttl_seconds=10)
    assert lease.online(session_key, now=started, generation=1, source_file=marker)
    assert (
        lease.online(
            session_key,
            now=started + timedelta(seconds=11),
            generation=1,
            source_file=marker,
        )
        is False
    )


def test_a_reused_pid_does_not_revive_the_previous_generation(tmp_path) -> None:
    lease, session_key = _session(tmp_path)
    started = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    lease.beat(session_key, pid=42, generation=1, now=started, ttl_seconds=60)
    lease.beat(session_key, pid=42, generation=2, now=started, ttl_seconds=60)
    assert lease.online(session_key, now=started, generation=1) is False
    assert lease.online(session_key, now=started, generation=2) is True


def test_a_file_without_a_lease_is_offline(tmp_path) -> None:
    lease, session_key = _session(tmp_path)
    marker = tmp_path / "session.jsonl"
    marker.write_text("still on disk")
    assert (
        lease.online(
            session_key,
            now=datetime(2026, 9, 22, 12, 0, tzinfo=UTC),
            generation=1,
            source_file=marker,
        )
        is False
    )
