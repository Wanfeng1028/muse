"""A search hit carries who wrote the row it matched.

The Reader used to send back everything about a matched row except its author,
and the one client that lists hits as dialogue filled the gap in by hand, as
"the user". These pin the author to the row so the gap cannot reopen.
"""

from one_memory.reader_app import _conversation_hit


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "evidence_id": "evidence-1",
        "conversation_id": "conversation-1",
        "source_id": "codex",
        "workspace": "/Users/k/one-memory",
        "project": "one-memory",
        "created_at": "2026-10-04T10:00:00Z",
        "verbatim": "红眼航班要靠过道",
        "role": "assistant",
        "written_by": "agent",
    }
    row.update(overrides)
    return row


def test_an_assistant_row_stays_attributed_to_the_assistant() -> None:
    hit = _conversation_hit(_row())
    assert hit["role"] == "assistant"
    assert hit["written_by"] == "agent"


def test_a_row_the_person_wrote_is_not_relabelled_on_the_way_out() -> None:
    hit = _conversation_hit(_row(role="user", written_by="person"))
    assert hit["role"] == "user"
    assert hit["written_by"] == "person"


def test_a_long_row_is_excerpted_and_an_empty_one_is_not_a_crash() -> None:
    assert _conversation_hit(_row(verbatim="航" * 400))["excerpt"] == "航" * 200
    assert _conversation_hit(_row(verbatim=None))["excerpt"] == ""
