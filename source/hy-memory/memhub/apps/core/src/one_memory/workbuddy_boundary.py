"""WorkBuddy SessionStart and UserPromptSubmit. No idle turn is started.

The notice stream is the current Evidence revision projection in
`SessionInbox`; `change_outbox` is retained there only as a legacy event source.
"""

import base64
import binascii
import json
import sqlite3
from pathlib import Path
from typing import TextIO

from one_memory.derived_echo import render_reference
from one_memory.session_inbox import CursorRejected, InboxPosition, SessionInbox
from one_memory.session_registry import SessionIdentityError, SessionRegistry

BOUNDARY_EVENTS = frozenset({"SessionStart", "UserPromptSubmit"})


def database_path() -> Path:
    from one_memory.config import load_settings

    return load_settings().data_dir / "one-memory.sqlite3"


PAGE_LIMIT = 8


def _boundary_session(payload: object, database: Path) -> tuple[str, str] | None:
    """The hook event and the one trusted session it belongs to.

    Identity is the payload's own session id. A parent id is not a substitute.
    More than one matching trusted session is ambiguous, so nothing is injected.
    """

    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name") or payload.get("hookEventName")
    if event not in BOUNDARY_EVENTS:
        return None
    native = payload.get("session_id") or payload.get("sessionId")
    if not isinstance(native, str) or not native or not database.is_file():
        return None
    matches = SessionRegistry(database).matching_native("workbuddy", native)
    if len(matches) != 1:
        return None
    return str(event), matches[0].session_key


def hook_output(payload: object, database: Path) -> dict[str, object]:
    """The JSON WorkBuddy reads on the next session or prompt boundary.

    Reading moves the cursor, so a notice lost before it reaches the host is
    not sent again. Kept for installs whose hook predates `--peek`.
    """

    silent: dict[str, object] = {"continue": True}
    found = _boundary_session(payload, database)
    if found is None:
        return silent
    event, session_key = found
    inbox = SessionInbox(database)
    page = inbox.pull(session_key, inbox.latest_cursor(session_key), PAGE_LIMIT)
    if not page.events:
        return silent
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": render_reference(page.events),
        },
    }


def peek_output(payload: object, database: Path) -> dict[str, object]:
    """The same notice without moving the cursor, plus the token that confirms it.

    Until `confirm` receives the token the notice is sent again next round.
    """

    found = _boundary_session(payload, database)
    if found is None:
        return {}
    event, session_key = found
    peeked = SessionInbox(database).peek(session_key, PAGE_LIMIT)
    if not peeked.events:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": render_reference(peeked.events),
        },
        "one_memory_ack": _token(session_key, peeked.position),
    }


def confirm(token: str, database: Path) -> bool | None:
    """Move the session's cursor up to what the token's peek handed over.

    Raises ValueError for a token this module did not issue.
    """

    session_key, position = _untoken(token)
    return SessionInbox(database).advance_to(session_key, position)


def _token(session_key: str, position: InboxPosition) -> str:
    body = json.dumps(
        {
            "s": session_key,
            "e": position.event_id,
            "p": position.permission_epoch,
            "h": sorted(position.handed_event_ids),
            "r": position.receipt_id,
        },
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")


def _untoken(token: str) -> tuple[str, InboxPosition]:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        body = json.loads(raw)
    except (binascii.Error, ValueError) as error:
        raise ValueError("not a boundary token") from error
    if not isinstance(body, dict):
        raise ValueError("not a boundary token")
    session_key, event_id, epoch, handed, receipt_id = (
        body.get("s"),
        body.get("e"),
        body.get("p"),
        body.get("h", []),
        body.get("r"),
    )
    if not isinstance(session_key, str) or not isinstance(event_id, str):
        raise ValueError("not a boundary token")
    if not isinstance(epoch, int) or isinstance(epoch, bool):
        raise ValueError("not a boundary token")
    if not isinstance(handed, list) or any(not isinstance(item, str) for item in handed):
        raise ValueError("not a boundary token")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise ValueError("not a boundary token")
    return session_key, InboxPosition(event_id, epoch, frozenset(handed), receipt_id)


def _payload(stdin: TextIO) -> object:
    try:
        return json.loads(stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def write_hook(stream: TextIO, stdin: TextIO) -> int:
    """Print the reply only when it carries a notice.

    WorkBuddy reads stdout without `hookSpecificOutput` as context text, so a
    bare `{"continue": true}` would reach the model. Empty stdout also continues.
    """

    body = hook_output(_payload(stdin), database_path())
    if "hookSpecificOutput" in body:
        stream.write(f"{json.dumps(body, ensure_ascii=False)}\n")
    return 0


def write_peek(stream: TextIO, stdin: TextIO) -> int:
    body = peek_output(_payload(stdin), database_path())
    if body:
        stream.write(f"{json.dumps(body, ensure_ascii=False)}\n")
    return 0


def run_confirm(token: str) -> int:
    try:
        confirm(token, database_path())
    except (ValueError, CursorRejected, SessionIdentityError, sqlite3.Error):
        return 1
    return 0
