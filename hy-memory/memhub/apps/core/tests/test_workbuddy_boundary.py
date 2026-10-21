"""WorkBuddy only injects on SessionStart and UserPromptSubmit."""

import json
import re
import sqlite3
import threading
from contextlib import closing
from io import StringIO
from uuid import uuid4

from one_memory import cli
from one_memory.change_outbox import evidence_event_id
from one_memory.derived_echo import PREFACE
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.session_inbox import SessionInbox
from one_memory.session_registry import SessionRegistry
from one_memory.workbuddy_boundary import hook_output


def _ready(tmp_path, native_id: str = "child-session"):
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    registry = SessionRegistry(path)
    registry.initialize()
    inbox = SessionInbox(path)
    inbox.initialize()
    opened = registry.open(
        installation_id=str(uuid4()),
        host_id="workbuddy",
        native_session_id=native_id,
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    inbox.subscribe(opened.session_key, ("workbuddy", "codex"), permission_epoch=1)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        store.put(
            EvidenceInput(
                source_id="codex",
                conversation_id="elsewhere",
                message_id="m1",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="接口改成按会话拉",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
            ),
            connection=db,
        )
        db.commit()
    return path, store


def test_session_start_and_prompt_submit_carry_context_stop_does_not(tmp_path) -> None:
    path, store = _ready(tmp_path)
    started = hook_output(
        {
            "hook_event_name": "SessionStart",
            "session_id": "child-session",
            "parent_session_id": "parent-session",
        },
        path,
    )
    quiet = hook_output(
        {"hook_event_name": "UserPromptSubmit", "session_id": "child-session"},
        path,
    )
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        store.put(
            EvidenceInput(
                source_id="codex",
                conversation_id="elsewhere",
                message_id="m2",
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim="再补一条",
                origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
            ),
            connection=db,
        )
        db.commit()
    submitted = hook_output(
        {"hook_event_name": "UserPromptSubmit", "session_id": "child-session"},
        path,
    )
    stopped = hook_output({"hook_event_name": "Stop", "session_id": "child-session"}, path)
    for body, event_name in (
        (started, "SessionStart"),
        (submitted, "UserPromptSubmit"),
    ):
        output = body["hookSpecificOutput"]
        assert isinstance(output, dict)
        assert output["hookEventName"] == event_name
        context = output["additionalContext"]
        assert isinstance(context, str)
        assert PREFACE in context
        assert "om-derived:" in context
        assert "来源 codex" in context
        assert "continueRequest" not in body
    assert quiet == {"continue": True}
    assert stopped == {"continue": True}
    assert "hookSpecificOutput" not in stopped


def test_a_parent_id_does_not_stand_in_for_the_session(tmp_path) -> None:
    path, _store = _ready(tmp_path, native_id="child-session")
    body = hook_output(
        {"hook_event_name": "SessionStart", "session_id": "parent-session"},
        path,
    )
    assert body == {"continue": True}


def test_evidence_writes_feed_the_boundary_without_the_dormant_outbox(tmp_path) -> None:
    path, _store = _ready(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        row = db.execute(
            """
            SELECT evidence_id, revision FROM evidence
            WHERE source_id = 'codex' AND message_id = 'm1'
            """
        ).fetchone()
    assert row is not None
    assert row[1] == 1
    events = SessionInbox(path)._events()
    assert evidence_event_id(str(row[0]), int(row[1])) in {event.event_id for event in events}
    assert events


def test_two_trusted_rows_for_one_native_id_inject_nothing(tmp_path) -> None:
    path, _store = _ready(tmp_path)
    SessionRegistry(path).open(
        installation_id=str(uuid4()),
        host_id="workbuddy",
        native_session_id="child-session",
        runtime_instance="runtime-2",
        workspace="/work/same-project",
    )
    body = hook_output({"hook_event_name": "UserPromptSubmit", "session_id": "child-session"}, path)
    assert body == {"continue": True}


def test_boundary_command_reads_stdin(tmp_path, monkeypatch) -> None:
    path, _store = _ready(tmp_path)
    monkeypatch.setattr("one_memory.workbuddy_boundary.database_path", lambda: path)
    monkeypatch.setattr(
        "sys.stdin",
        StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": "child-session"})),
    )
    output = StringIO()
    assert cli.run(["boundary"], output=output) == 0
    body = json.loads(output.getvalue())
    assert body["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "continueRequest" not in body


def test_boundary_command_prints_nothing_when_there_is_no_notice(tmp_path, monkeypatch) -> None:
    """Hosts read stdout that is not a hook reply as context; silence must be empty."""

    path, _store = _ready(tmp_path)
    monkeypatch.setattr("one_memory.workbuddy_boundary.database_path", lambda: path)
    first = StringIO()
    monkeypatch.setattr(
        "sys.stdin",
        StringIO(json.dumps({"hook_event_name": "SessionStart", "session_id": "child-session"})),
    )
    assert cli.run(["boundary"], output=first) == 0
    assert "hookSpecificOutput" in json.loads(first.getvalue())
    for payload in (
        {"hook_event_name": "UserPromptSubmit", "session_id": "child-session"},
        {"hook_event_name": "UserPromptSubmit", "session_id": "someone-else"},
        {"hook_event_name": "Stop", "session_id": "child-session"},
    ):
        monkeypatch.setattr("sys.stdin", StringIO(json.dumps(payload)))
        quiet = StringIO()
        assert cli.run(["boundary"], output=quiet) == 0
        assert quiet.getvalue() == "", payload


def _codex_says(store: EvidenceStore, path, message_id: str, text: str) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        store.put(
            EvidenceInput(
                source_id="codex",
                conversation_id="elsewhere",
                message_id=message_id,
                role="user",
                written_by=WrittenBy.PERSON,
                verbatim=text,
                origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
            ),
            connection=db,
        )
        db.commit()


def _boundary(monkeypatch, path, *arguments: str) -> tuple[int, str]:
    monkeypatch.setattr("one_memory.workbuddy_boundary.database_path", lambda: path)
    monkeypatch.setattr(
        "sys.stdin",
        StringIO(
            json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "child-session"})
        ),
    )
    output = StringIO()
    code = cli.run(["boundary", *arguments], output=output)
    return code, output.getvalue()


def _peek(monkeypatch, path) -> tuple[list[str], str | None]:
    """The event ids a peek hands over, and the token that confirms them."""

    code, text = _boundary(monkeypatch, path, "--peek")
    assert code == 0
    if not text:
        return [], None
    body = json.loads(text)
    context = body["hookSpecificOutput"]["additionalContext"]
    token = body["one_memory_ack"]
    assert isinstance(token, str) and token
    return re.findall(r"om-derived:([0-9a-f]{64})", context), token


def _ack(monkeypatch, path, token: str) -> int:
    code, text = _boundary(monkeypatch, path, "--ack", token)
    assert text == ""
    return code


def test_a_peek_does_not_move_the_cursor(tmp_path, monkeypatch) -> None:
    path, _store = _ready(tmp_path)
    first, _token = _peek(monkeypatch, path)
    second, _token = _peek(monkeypatch, path)
    assert len(first) == 1
    assert second == first


def test_a_confirmed_peek_does_not_come_back_and_later_notices_still_do(
    tmp_path, monkeypatch
) -> None:
    path, store = _ready(tmp_path)
    delivered, token = _peek(monkeypatch, path)
    assert len(delivered) == 1 and token is not None
    assert _ack(monkeypatch, path, token) == 0
    assert _peek(monkeypatch, path) == ([], None)
    _codex_says(store, path, "m2", "再补一条")
    later, _token = _peek(monkeypatch, path)
    assert len(later) == 1
    assert later != delivered


def test_confirming_moves_only_to_what_that_peek_handed_over(tmp_path, monkeypatch) -> None:
    path, store = _ready(tmp_path)
    handed, token = _peek(monkeypatch, path)
    _codex_says(store, path, "m2", "peek 之后才到")
    assert token is not None
    assert _ack(monkeypatch, path, token) == 0
    after, _token = _peek(monkeypatch, path)
    assert len(after) == 1
    assert after != handed


def test_two_rounds_confirming_out_of_order_do_not_pull_each_other_back(
    tmp_path, monkeypatch
) -> None:
    for order in ("later-first", "earlier-first"):
        (tmp_path / order).mkdir()
        path, store = _ready(tmp_path / order)
        early, early_token = _peek(monkeypatch, path)
        _codex_says(store, path, "m2", "第二条")
        late, late_token = _peek(monkeypatch, path)
        assert len(early) == 1 and len(late) == 2 and late[0] == early[0]
        assert early_token is not None and late_token is not None
        tokens = [late_token, early_token] if order == "later-first" else [early_token, late_token]
        for token in tokens:
            assert _ack(monkeypatch, path, token) == 0
        assert _peek(monkeypatch, path) == ([], None), order
        _codex_says(store, path, "m3", "第三条")
        newest, _token = _peek(monkeypatch, path)
        assert len(newest) == 1 and newest[0] not in late, order


def test_a_token_that_is_not_ours_changes_nothing(tmp_path, monkeypatch) -> None:
    path, _store = _ready(tmp_path)
    before, _token = _peek(monkeypatch, path)
    assert _ack(monkeypatch, path, "not-a-token") != 0
    after, _token = _peek(monkeypatch, path)
    assert after == before


def test_a_token_from_before_a_permission_change_does_not_confirm(tmp_path, monkeypatch) -> None:
    path, _store = _ready(tmp_path)
    before, token = _peek(monkeypatch, path)
    assert len(before) == 1 and token is not None
    session_key = SessionRegistry(path).matching_native("workbuddy", "child-session")[0].session_key
    SessionInbox(path).subscribe(session_key, ("workbuddy", "codex"), permission_epoch=2)
    assert _ack(monkeypatch, path, token) == 0
    after, _token = _peek(monkeypatch, path)
    assert after == before


def test_a_token_whose_target_is_no_longer_granted_does_not_confirm(tmp_path, monkeypatch) -> None:
    path, _store = _ready(tmp_path)
    before, token = _peek(monkeypatch, path)
    assert before and token is not None
    session_key = SessionRegistry(path).matching_native("workbuddy", "child-session")[0].session_key
    SessionInbox(path).subscribe(session_key, ("workbuddy",), permission_epoch=2)
    assert _ack(monkeypatch, path, token) != 0
    SessionInbox(path).subscribe(session_key, ("workbuddy", "codex"), permission_epoch=2)
    after, _token = _peek(monkeypatch, path)
    assert after == before


def _revoke_from_another_thread(path, session_key) -> None:
    # The reader holds its checkout; a second checkout on the same thread is refused.
    revoke = threading.Thread(
        target=SessionInbox(path).subscribe,
        args=(session_key, ("workbuddy",)),
        kwargs={"permission_epoch": 2},
    )
    revoke.start()
    revoke.join()


def test_a_peek_reads_grants_events_and_epoch_from_one_snapshot(tmp_path, monkeypatch) -> None:
    """A revoke landing mid-peek must not pair the old grants with the new epoch.

    That pairing would let a confirm under the new epoch skip the resync the
    revoke is meant to force, after handing over events the new grants deny.
    """

    path, _store = _ready(tmp_path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    session_key = SessionRegistry(path).matching_native("workbuddy", "child-session")[0].session_key
    original = SessionInbox._events
    revoked = []

    def revoke_mid_read(self, *args, **kwargs):
        if not revoked:
            revoked.append(True)
            _revoke_from_another_thread(path, session_key)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SessionInbox, "_events", revoke_mid_read)
    peeked = SessionInbox(path).peek(session_key, 8)

    assert revoked
    sources = {event.source_id for event in peeked.events}
    if peeked.position.permission_epoch == 2:
        assert "codex" not in sources
    else:
        assert peeked.position.permission_epoch == 1


def test_a_pull_reads_grants_events_and_epoch_from_one_snapshot(tmp_path) -> None:
    path, store = _ready(tmp_path)
    session_key = SessionRegistry(path).matching_native("workbuddy", "child-session")[0].session_key
    first = SessionInbox(path).pull(session_key, None, 8)
    _codex_says(store, path, "m2", "第二条")
    original = SessionInbox._events
    revoked = []

    def revoke_mid_read(self, *args, **kwargs):
        if not revoked:
            revoked.append(True)
            _revoke_from_another_thread(path, session_key)
        return original(self, *args, **kwargs)

    racing = SessionInbox(path)
    racing._events = revoke_mid_read.__get__(racing)  # type: ignore[method-assign]
    page = racing.pull(session_key, first.cursor, 8)

    assert revoked
    with closing(sqlite3.connect(path)) as db:
        stored = db.execute(
            "SELECT permission_epoch FROM session_inbox_cursors WHERE cursor_token = ?",
            (page.cursor,),
        ).fetchone()[0]
    if stored == 2:
        assert "codex" not in {event.source_id for event in page.events}


def test_a_confirm_racing_another_process_does_not_move_the_cursor_back(
    tmp_path, monkeypatch
) -> None:
    """The confirm reads the latest cursor and writes after it as one step.

    The other confirm is another process: it holds the file's write lock and
    moves the cursor further while this one is deciding. It commits only once
    this confirm has begun its first statement that needs that lock.
    """

    import threading
    from contextlib import contextmanager

    from one_memory.database_access import MainDatabase

    path, store = _ready(tmp_path)
    session_key = SessionRegistry(path).matching_native("workbuddy", "child-session")[0].session_key
    inbox = SessionInbox(path)
    early = inbox.peek(session_key, 8).position
    _codex_says(store, path, "m2", "第二条")
    late = inbox.peek(session_key, 8).position
    assert early.event_id != late.event_id

    waiting = threading.Event()
    original_write = MainDatabase.write

    @contextmanager
    def traced_write(self, *args, **kwargs):
        with original_write(self, *args, **kwargs) as db:
            if threading.current_thread().name == "racing-confirm":
                db.set_trace_callback(
                    lambda sql: (
                        waiting.set()
                        if sql.lstrip().upper().startswith(("BEGIN IMMEDIATE", "INSERT"))
                        else None
                    )
                )
            yield db

    monkeypatch.setattr(MainDatabase, "write", traced_write)
    outcome: list[object] = []

    def confirm_early() -> None:
        try:
            outcome.append(SessionInbox(path).advance_to(session_key, early))
        except Exception as error:  # noqa: BLE001 - the outcome is the assertion
            outcome.append(error)

    with closing(sqlite3.connect(path, isolation_level=None)) as other:
        other.execute("BEGIN IMMEDIATE")
        other.execute(
            """
            INSERT INTO session_inbox_cursors (
                cursor_token, session_key, scanned_event_id, permission_epoch
            ) VALUES ('other-process', ?, ?, ?)
            """,
            (session_key, late.event_id, late.permission_epoch),
        )
        racing = threading.Thread(target=confirm_early, name="racing-confirm")
        racing.start()
        assert waiting.wait(4), "the confirm never reached the write lock"
        other.execute("COMMIT")
    racing.join(10)

    assert outcome == [None]
    with closing(sqlite3.connect(path)) as db:
        latest = db.execute(
            """
            SELECT scanned_event_id FROM session_inbox_cursors
            WHERE session_key = ? ORDER BY rowid DESC LIMIT 1
            """,
            (session_key,),
        ).fetchone()[0]
    assert latest == late.event_id
