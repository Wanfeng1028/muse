"""BUG-04: Cursor thinking text must not be stored as the assistant's answer.

Cursor keeps thinking and answer in one text block, separated by a blank line,
with no `thinking` field to filter on. These fixtures come from that shape as
observed in `~/.cursor/projects/*/agent-transcripts/`.

The strip must not disturb identity: BUG-03 made the key hash the pre-strip
text, so re-scanning a transcript after this change has to reach the rows that
are already stored rather than inserting them again.
"""

from datetime import UTC, datetime

from one_memory.imports.models import (
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.sources.cursor_unified import strip_thinking
from one_memory.imports.storage import EvidenceStore

ANSWER = "把标题改成深绿色，正文保持原样。"
THINKING = (
    "I need to check whether the stylesheet already defines a dark green token "
    "before editing it, and I should confirm the body copy is untouched."
)


def test_strip_thinking_removes_a_trailing_thinking_tail() -> None:
    assert strip_thinking(f"{ANSWER}\n\n{THINKING}") == ANSWER


def test_strip_thinking_leaves_an_answer_without_a_tail_alone() -> None:
    assert strip_thinking(ANSWER) == ANSWER


def test_strip_thinking_keeps_an_answer_that_mentions_its_reasoning() -> None:
    """A real answer can open with the same cue words; it is still the answer."""
    answer = "我先确认了样式表里已有的深绿色记号，然后改了标题。"
    assert strip_thinking(answer) == answer


def test_rescanning_a_stripped_transcript_does_not_duplicate(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    raw = f"{ANSWER}\n\n{THINKING}"

    def scanned(verbatim: str) -> EvidenceInput:
        return EvidenceInput(
            source_id="cursor",
            conversation_id="conversation-1",
            workspace="/repo",
            message_id="cursor-transcript:17",
            role="assistant",
            written_by=WrittenBy.AGENT,
            created_at=datetime(2026, 10, 12, 21, 0, tzinfo=UTC),
            verbatim=verbatim,
            raw_verbatim=raw,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )

    # The first scan happened before the strip existed, so its stored body still
    # carries the thinking tail. What matters is that the rescan reaches that
    # row instead of inserting a second copy under a new identity.
    before = store.put(scanned(raw)).record
    assert before.verbatim == raw

    after = store.put(scanned(strip_thinking(raw))).record

    assert after.evidence_id == before.evidence_id
    assert store.count() == 1


def test_a_fresh_scan_stores_the_answer_without_the_thinking_tail(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    raw = f"{ANSWER}\n\n{THINKING}"
    stored = store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="conversation-1",
            workspace="/repo",
            message_id="cursor-transcript:17",
            role="assistant",
            written_by=WrittenBy.AGENT,
            created_at=datetime(2026, 10, 12, 21, 0, tzinfo=UTC),
            verbatim=strip_thinking(raw),
            raw_verbatim=raw,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    ).record

    assert stored.verbatim == ANSWER


def test_stripping_thinking_does_not_split_one_message_into_two(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    raw = f"{ANSWER}\n\n{THINKING}"
    store.put(
        EvidenceInput(
            source_id="cursor",
            conversation_id="conversation-1",
            workspace="/repo",
            message_id="cursor-transcript:17",
            role="assistant",
            written_by=WrittenBy.AGENT,
            created_at=datetime(2026, 10, 12, 21, 0, tzinfo=UTC),
            verbatim=strip_thinking(raw),
            raw_verbatim=raw,
            origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
        )
    )

    assert store.count() == 1


def test_rescanning_a_whole_batch_after_the_strip_keeps_one_row_each(tmp_path) -> None:
    """The batch is rescanned once; that must not duplicate anything.

    `evidence.idempotency_key` is UNIQUE and the insert is
    `ON CONFLICT DO NOTHING`, so a duplicate would be dropped silently rather
    than raised. Counting the rows is the only way to see it happen.
    """
    store = EvidenceStore(tmp_path / "one-memory.sqlite3")
    bodies = [
        f"{ANSWER}\n\n{THINKING}",
        "把按钮改成圆角。\n\nI should check the design tokens before editing the radius.",
        "已经改好了，按钮现在是圆角。",
    ]

    def scan(source: list[str]) -> int:
        for index, body in enumerate(source):
            store.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation-1",
                    workspace="/repo",
                    message_id=f"cursor-transcript:{index}",
                    role="assistant",
                    written_by=WrittenBy.AGENT,
                    created_at=datetime(2026, 10, 12, 21, 0, tzinfo=UTC),
                    verbatim=strip_thinking(body),
                    # The transcript text as Cursor wrote it, before the strip.
                    raw_verbatim=body,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            )
        return store.count()

    assert scan(bodies) == 3
    assert scan(bodies) == 3
