"""A host that saves our injection back must not mint a new user decision."""

import sqlite3
from contextlib import closing
from uuid import uuid4

from one_memory.change_outbox import ChangeOutbox, evidence_event_id
from one_memory.derived_echo import render_reference
from one_memory.imports.models import EvidenceInput, EvidenceOrigin, OriginMetadata, WrittenBy
from one_memory.imports.storage import EvidenceStore
from one_memory.session_inbox import SessionInbox
from one_memory.session_registry import SessionRegistry


def _evidence(message_id: str, verbatim: str) -> EvidenceInput:
    return EvidenceInput(
        source_id="workbuddy",
        conversation_id="session-b",
        message_id=message_id,
        role="assistant",
        written_by=WrittenBy.PERSON,
        verbatim=verbatim,
        origin_meta={EvidenceOrigin.FILE: OriginMetadata(raw_meta={"root": "proj"})},
    )


def test_a_restatement_is_not_broadcast_and_a_correction_still_is(tmp_path) -> None:
    path = tmp_path / "one-memory.sqlite3"
    store = EvidenceStore(path)
    registry = SessionRegistry(path)
    registry.initialize()
    inbox = SessionInbox(path)
    inbox.initialize()
    opened = registry.open(
        installation_id=str(uuid4()),
        host_id="workbuddy",
        native_session_id="session-b",
        runtime_instance="runtime-1",
        workspace="/work/same-project",
    )
    inbox.subscribe(opened.session_key, ("workbuddy",), permission_epoch=1)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        decision = store.put(_evidence("decision", "周五前交一版"), connection=db)
        ChangeOutbox(path).record(
            db,
            event_id=evidence_event_id(decision.record.evidence_id, decision.record.revision),
            cause="import",
            evidence_id=decision.record.evidence_id,
            evidence_revision=decision.record.revision,
            permission_epoch=0,
        )
        db.commit()
    page = inbox.pull(opened.session_key, cursor=None, limit=8)
    injected = render_reference(page.events)
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        store.put(_evidence("echo", injected), connection=db)
        db.commit()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM change_outbox").fetchone()[0] == 1
    echoed = inbox.pull(opened.session_key, cursor=page.cursor, limit=8)
    assert echoed.events == ()
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        correction = store.put(
            _evidence("correction", injected + "\n不对，改成下周三"), connection=db
        )
        ChangeOutbox(path).record(
            db,
            event_id=evidence_event_id(correction.record.evidence_id, correction.record.revision),
            cause="import",
            evidence_id=correction.record.evidence_id,
            evidence_revision=correction.record.revision,
            permission_epoch=0,
        )
        db.commit()
    corrected = inbox.pull(opened.session_key, cursor=page.cursor, limit=8)
    assert len(corrected.events) == 1


def test_stripping_removes_the_notice_block_as_well_as_the_memory_block() -> None:
    from one_memory.derived_echo import strip_injected_memory

    merged = (
        "把按钮改成蓝色\n"
        '<system-reminder data-role="hook"><memhub_memory_context>\n[1] 深绿色\n'
        "</memhub_memory_context>\n\n<memhub_session_notice>\n来源 codex 修订 1 证据 ev\n"
        "</memhub_session_notice></system-reminder>"
    )
    notice_only = (
        '<system-reminder data-role="hook"><memhub_session_notice>\n来源 codex\n'
        "</memhub_session_notice></system-reminder>\n把按钮改成蓝色"
    )
    assert strip_injected_memory(merged) == "把按钮改成蓝色"
    assert strip_injected_memory(notice_only) == "把按钮改成蓝色"


def test_injected_blocks_are_stripped_in_case_and_spacing_variants() -> None:
    from one_memory.derived_echo import strip_injected_memory

    for opening, closing_tag in (
        ("<MEMHUB_MEMORY_CONTEXT>", "</MEMHUB_MEMORY_CONTEXT>"),
        ("<memhub_memory_context >", "</ memhub_memory_context >"),
        ("< memhub_session_notice>", "< /memhub_session_notice>"),
        ("<Memhub_Session_Notice>", "</memhub_session_notice\n>"),
    ):
        text = f"真正的问题\n{opening}\n回忆出来的内容\n{closing_tag}"
        assert strip_injected_memory(text) == "真正的问题", opening


def test_the_tags_stripped_here_are_the_tags_the_hook_writes() -> None:
    """Two runtimes spell the same format; a rename on one side must fail here."""

    import re
    from pathlib import Path

    from one_memory.derived_echo import _INJECTED_TAGS

    hook = (
        Path(__file__).resolve().parents[3] / "packages/host-bridge/src/recall-injection.ts"
    ).read_text()
    written = set(re.findall(r'^const (?:TAG|NOTICE_TAG) = "([a-z_]+)";', hook, re.MULTILINE))
    assert len(written) == 2
    assert written == set(_INJECTED_TAGS)


def _shared_cases() -> dict[str, list[str]]:
    import json
    from pathlib import Path

    return json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "packages/host-bridge/src/reserved-tags.cases.json"
        ).read_text(encoding="utf-8")
    )


def test_core_recognizes_the_reserved_tags_the_hook_disarms() -> None:
    from one_memory.derived_echo import reserved_tags

    cases = _shared_cases()
    for text in cases["reserved"]:
        assert reserved_tags(text) == [(0, len(text))], text
    for text in cases["ordinary"]:
        assert reserved_tags(text) == [], text


def test_core_strips_an_injected_block_in_any_spelling_the_hook_would_recognize() -> None:
    from one_memory.derived_echo import strip_injected_memory

    cases = _shared_cases()
    for block in cases["blocks"]:
        assert strip_injected_memory(f"前{block}后") == "前后", block
    for text in cases["ordinary"]:
        assert strip_injected_memory(text) == text, text


def test_the_fast_path_knows_every_character_that_reads_as_an_opening_bracket() -> None:
    import sys
    import unicodedata

    from one_memory.derived_echo import _OPENING_BRACKETS

    found = {
        chr(point)
        for point in range(sys.maxunicode + 1)
        if "<" in unicodedata.normalize("NFKC", chr(point)).lower()
    }
    assert found == set(_OPENING_BRACKETS)


def test_many_unmatched_tags_do_not_slow_an_import_down() -> None:
    import time

    from one_memory.derived_echo import strip_injected_memory

    text = "<memhub_memory_context>x" * 20_000
    started = time.perf_counter()
    assert strip_injected_memory(text) == text
    assert time.perf_counter() - started < 5


def test_a_long_message_with_brackets_but_no_tag_is_not_walked_character_by_character() -> None:
    import time

    from one_memory.derived_echo import strip_injected_memory

    text = "<" + "普通中文消息，a < b。" * 400_000
    started = time.perf_counter()
    assert strip_injected_memory(text) == text
    assert time.perf_counter() - started < 1.5
