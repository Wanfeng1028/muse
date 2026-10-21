from datetime import UTC, datetime, timedelta

from one_memory.ui_session import EXCHANGE_TTL, UISessionStore


def test_exchange_is_single_use_and_creates_a_session() -> None:
    store = UISessionStore(instance_id="instance-a")

    code, _ = store.issue_exchange()
    session = store.consume_exchange(code)

    assert session is not None
    assert store.valid_session(session)
    assert store.consume_exchange(code) is None


def test_expired_exchange_cannot_create_a_session() -> None:
    store = UISessionStore(instance_id="instance-a")
    now = datetime(2026, 9, 29, tzinfo=UTC)
    code, _ = store.issue_exchange(now=now)

    assert store.consume_exchange(code, now=now + EXCHANGE_TTL) is None


def test_exchange_is_bound_to_the_core_instance() -> None:
    store = UISessionStore(instance_id="instance-a")
    now = datetime(2026, 9, 29, tzinfo=UTC)
    code, _ = store.issue_exchange(now=now)
    store.instance_id = "instance-b"

    assert store.consume_exchange(code, now=now) is None


def test_revoked_session_stops_being_valid() -> None:
    store = UISessionStore(instance_id="instance-a")
    session = store.consume_exchange(store.issue_exchange()[0])
    assert session is not None

    store.revoke_session(session)

    assert not store.valid_session(session)


def test_session_expires() -> None:
    store = UISessionStore(instance_id="instance-a")
    now = datetime(2026, 9, 29, tzinfo=UTC)
    session = store.consume_exchange(store.issue_exchange(now=now)[0], now=now)
    assert session is not None

    assert not store.valid_session(session, now=now + timedelta(hours=13))
