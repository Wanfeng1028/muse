"""A session inbox is not a shared mailbox and a pull is not adoption."""

import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.session_inbox import CursorRejected, InboxPosition, SessionInbox
from one_memory.session_registry import ForgedSession, SessionRegistry


def _evidence(message_id: str, verbatim: str) -> EvidenceInput:
    return EvidenceInput(
        source_id="workbuddy",
        conversation_id="session-a",
        message_id=message_id,
        role="user",
        written_by=WrittenBy.PERSON,
        verbatim=verbatim,
        origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
    )


def _world(tmp_path):
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    registry = SessionRegistry(path)
    registry.initialize()
    inbox = SessionInbox(path)
    inbox.initialize()
    installation = str(uuid4())
    shared = dict(
        installation_id=installation,
        host_id="workbuddy",
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    first = registry.open(**shared, native_session_id="session-a")
    second = registry.open(**shared, native_session_id="session-b")
    inbox.subscribe(first.session_key, ("workbuddy",), permission_epoch=1)
    inbox.subscribe(second.session_key, ("workbuddy",), permission_epoch=1)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        store.put(_evidence("m1", "SECRET_DECISION"), connection=db)
        store.put(_evidence("m2", "SECOND_UPDATE"), connection=db)
        db.commit()
    return inbox, first, second


def test_another_session_cannot_use_this_cursor(tmp_path) -> None:
    inbox, first, second = _world(tmp_path)
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    with pytest.raises(CursorRejected):
        inbox.pull(second.session_key, cursor=page.cursor, limit=10)


def test_forged_session_cannot_pull(tmp_path) -> None:
    inbox, _first, _second = _world(tmp_path)
    with pytest.raises(ForgedSession):
        inbox.pull("0" * 64, cursor=None, limit=10)


def test_a_full_page_does_not_skip_the_rest(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    page = inbox.pull(first.session_key, cursor=None, limit=1)
    assert len(page.events) == 1
    rest = inbox.pull(first.session_key, cursor=page.cursor, limit=10)
    assert len(rest.events) == 1
    assert {item.evidence_id for item in (*page.events, *rest.events)} == {
        page.events[0].evidence_id,
        rest.events[0].evidence_id,
    }


def test_a_lost_signal_still_leaves_the_updates_pullable(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    signal = inbox.signal(first.session_key)
    dumped = repr(signal)
    assert "SECRET_DECISION" not in dumped
    assert "SECOND_UPDATE" not in dumped
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    assert len(page.events) == 2


def test_an_event_arriving_during_snapshot_is_not_lost(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    inbox, first, _second = _world(tmp_path)
    store = EvidenceStore(path)
    token = inbox.begin_snapshot(first.session_key)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        arrived = store.put(_evidence("m3", "DURING_SNAPSHOT"), connection=db)
        db.commit()
    closed = inbox.finish_snapshot(first.session_key, token)
    rest = inbox.pull(first.session_key, cursor=closed.cursor, limit=10)
    found = {event.evidence_id for event in (*closed.events, *rest.events)}
    assert arrived.record.evidence_id in found


def test_revoking_a_source_hides_a_queued_update(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    inbox.subscribe(first.session_key, (), permission_epoch=2)
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    assert page.events == ()


def test_a_position_whose_target_is_no_longer_granted_does_not_confirm(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    peeked = inbox.peek(first.session_key, 8)
    assert peeked.events
    inbox.subscribe(first.session_key, (), permission_epoch=2)
    with pytest.raises(CursorRejected):
        inbox.advance_to(first.session_key, peeked.position)


def test_a_position_that_does_not_receipt_the_whole_range_does_not_confirm(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    peeked = inbox.peek(first.session_key, 8)
    assert len(peeked.events) == 2
    partial = InboxPosition(
        peeked.position.event_id,
        peeked.position.permission_epoch,
        frozenset({peeked.events[-1].event_id}),
        peeked.position.receipt_id,
    )
    with pytest.raises(CursorRejected):
        inbox.advance_to(first.session_key, partial)


def test_a_cursor_whose_event_is_gone_resyncs_instead_of_an_empty_page(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    assert page.state == "delivered"
    assert len(page.events) == 2
    with closing(sqlite3.connect(tmp_path / "one-memory.sqlite3")) as db, db:
        db.execute("DELETE FROM evidence WHERE evidence_id = ?", (page.events[1].evidence_id,))
    again = inbox.pull(first.session_key, cursor=page.cursor, limit=10)
    assert again.state == "resync-required"
    assert again.adoption == "unknown"
    assert [event.event_id for event in again.events] == [page.events[0].event_id]
    quiet = inbox.pull(first.session_key, cursor=again.cursor, limit=10)
    assert quiet.state == "delivered"
    assert quiet.events == ()


def test_nothing_new_after_a_live_cursor_is_not_a_resync(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    again = inbox.pull(first.session_key, cursor=page.cursor, limit=10)
    assert again.state == "delivered"
    assert again.events == ()


def test_pull_and_ack_are_not_adoption(tmp_path) -> None:
    inbox, first, _second = _world(tmp_path)
    page = inbox.pull(first.session_key, cursor=None, limit=10)
    assert page.adoption == "unknown"
    assert page.state == "delivered"
    acked = inbox.ack(first.session_key, page.batch_id)
    assert acked.state == "acknowledged"
    assert acked.adoption == "unknown"
