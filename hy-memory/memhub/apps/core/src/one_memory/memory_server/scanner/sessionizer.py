"""A4-05: turn normalized messages into sessions and rounds.

This is where A0-02's session identity meets real adapter output. Two product
decisions are encoded here, and both are the non-obvious direction:

**A round is "user turn(s) + their answer(s)", not "one message".** Consecutive
user messages belong to the same round, because a harness that writes two user
lines in a row is still mid-turn. Splitting them would make an unanswered user
turn look finished and batch it early.

**A round is only complete once it has been answered.** A trailing user turn
with nothing after it is still being written to; batching it would snapshot a
half-finished exchange. The batcher relies on this by counting complete rounds
only.

Session identity comes from `SessionIdentity.derive`, so a harness' own id is a
display label and the identity is the pair (harness, external id). Cross-file
sessions work because identity is derived, not per-file: the caller passes
`last_committed_round_by_session` so round numbers continue across files.
"""

from __future__ import annotations

from dataclasses import dataclass

from one_memory.memory_server.contracts import CanonicalMessage, SessionIdentity

#: Anything that is not the user's own turn counts as "the round was answered".
_USER_ROLE = "user"


@dataclass(frozen=True)
class Round:
    internal_session_id: str
    #: Absolute within the session. Absolute so a replay re-derives the same
    #: number and therefore the same batch id.
    round_number: int
    messages: tuple[CanonicalMessage, ...]
    #: False for a trailing round that is still awaiting an answer.
    is_complete: bool


def sessionize(
    messages: list[CanonicalMessage],
    *,
    harness_id: str,
    source_file_key: str,
    last_committed_round_by_session: dict[str, int] | None = None,
) -> tuple[Round, ...]:
    """Group messages into per-session rounds, in conversation order."""
    if not messages:
        return ()

    committed = last_committed_round_by_session or {}
    ordered = sorted(messages, key=lambda message: (message.ordinal, message.message_id or ""))

    sessions: dict[str, list[list[CanonicalMessage]]] = {}
    for message in ordered:
        identity = SessionIdentity.derive(
            harness_id=harness_id,
            external_session_id=message.external_session_id or None,
            source_file_key=source_file_key,
        )
        rounds = sessions.setdefault(identity.internal_session_id, [])
        if not rounds:
            rounds.append([message])
            continue
        current = rounds[-1]
        answered = any(item.role != _USER_ROLE for item in current)
        if message.role == _USER_ROLE and answered:
            # The previous turn was answered, so this starts a new round.
            rounds.append([message])
        else:
            current.append(message)

    result: list[Round] = []
    for session_id, rounds in sessions.items():
        base = committed.get(session_id, 0)
        for offset, messages_in_round in enumerate(rounds, start=1):
            is_complete = any(item.role != _USER_ROLE for item in messages_in_round)
            result.append(
                Round(
                    internal_session_id=session_id,
                    round_number=base + offset,
                    messages=tuple(messages_in_round),
                    is_complete=is_complete,
                )
            )
    return tuple(sorted(result, key=lambda item: (item.internal_session_id, item.round_number)))


def complete_rounds(rounds: list[Round]) -> int:
    """How many rounds are safe to batch. Unanswered trailing rounds do not count."""
    return sum(1 for item in rounds if item.is_complete)
