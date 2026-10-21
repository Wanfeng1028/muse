import asyncio
import json
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import zstandard
from pydantic import JsonValue

from one_memory.imports.access import (
    AuthorizedSourceFile,
    AuthorizedSourceRoot,
    opaque_workspace_id,
)
from one_memory.imports.adapters import ScanEvent, ScannedEvidence, ScanOptions
from one_memory.imports.models import EvidenceOrigin, WrittenBy
from one_memory.imports.readers import RawReadEvent
from one_memory.imports.sources.codex import create_codex_adapter
from one_memory.imports.sources.common import JsonlSourceAdapter

WORKSPACE = "/Users/example/projects/atlas"
WORKER_SOURCE: dict[str, JsonValue] = {
    "subagent": {
        "thread_spawn": {
            "parent_thread_id": "parent-thread",
            "depth": 1,
            "agent_path": None,
            "agent_nickname": "Worker",
            "agent_role": None,
        }
    }
}
GUARDIAN_SOURCE: dict[str, JsonValue] = {"subagent": {"other": "guardian"}}


def _header(
    *,
    source: JsonValue = "cli",
    native_id: str = "native-thread",
    version_key: str = "cli_version",
) -> dict[str, JsonValue]:
    return {
        "type": "session_meta",
        "payload": {
            "id": native_id,
            "session_id": "parent-session",
            "parent_thread_id": "parent-thread",
            "cwd": WORKSPACE,
            "originator": "Codex Desktop",
            version_key: "0.153.4",
            "source": source,
            "base_instructions": {"text": "DO_NOT_COPY_HEADER_INSTRUCTIONS" * 5000},
        },
    }


def _message(
    text: str,
    *,
    message_id: str | None = "user-1",
    role: str = "user",
    attributes: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    return {
        "type": "response_item",
        "timestamp": "2026-09-13T01:02:03Z",
        "payload": {
            "type": "message",
            "id": message_id,
            "role": role,
            "content": [{"type": "input_text", "text": text}],
            "internal_chat_message_metadata_passthrough": {
                "turn_id": "native-turn",
                "content_item_kinds": ["user.text"],
            },
            **(attributes or {}),
        },
    }


def _write(path: Path, records: list[dict[str, JsonValue]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _adapter(root: Path, *, source_version: str | None = None) -> JsonlSourceAdapter:
    return create_codex_adapter(
        AuthorizedSourceRoot.grant(
            source_id="codex",
            root=root,
            user_confirmed=True,
            home=root.parent / "unused-home",
        ),
        source_version=source_version,
    )


def _scan(adapter: JsonlSourceAdapter, options: ScanOptions | None = None) -> list[ScanEvent]:
    async def collect() -> list[ScanEvent]:
        return [event async for event in adapter.scan(options or ScanOptions())]

    return asyncio.run(collect())


def _evidence(events: list[ScanEvent]) -> list[ScannedEvidence]:
    return [event for event in events if isinstance(event, ScannedEvidence)]


@pytest.mark.parametrize("version_key", ["cli_version", "client_version"])
def test_header_workspace_versions_and_native_ids_reach_file_origin(
    tmp_path: Path, version_key: str
) -> None:
    transcript = tmp_path / "codex" / "rollout-a.jsonl"
    _write(
        transcript,
        [
            _header(source="mcp", version_key=version_key),
            _message("Keep the original request"),
            _message("Original answer", message_id="assistant-1", role="assistant"),
        ],
    )

    records = _evidence(_scan(_adapter(transcript.parent, source_version="fallback-version")))

    assert len(records) == 2
    assert [item.evidence.written_by for item in records] == [WrittenBy.PERSON, WrittenBy.AGENT]
    for item in records:
        evidence = item.evidence
        assert evidence.workspace == opaque_workspace_id("codex", WORKSPACE)
        assert evidence.project == "atlas"
        assert evidence.conversation_id == "rollout-a"
        assert evidence.created_at == datetime(2026, 9, 13, 1, 2, 3, tzinfo=UTC)
        origin = evidence.origin_meta[EvidenceOrigin.FILE]
        assert origin.source_version == "0.153.4"
        assert origin.raw_meta["native_session_id"] == "native-thread"
        assert origin.raw_meta["session_meta"] == {
            "id": "native-thread",
            "session_id": "parent-session",
            "parent_thread_id": "parent-thread",
            "originator": "Codex Desktop",
            version_key: "0.153.4",
            "source": "mcp",
        }
        assert origin.raw_meta["file_key"] == item.cursor.file_key
        assert origin.raw_meta["record_type"] == "response_item.message"
        assert "DO_NOT_COPY_HEADER_INSTRUCTIONS" not in origin.model_dump_json()
        assert WORKSPACE not in origin.model_dump_json()


@pytest.mark.parametrize("source", ["cli", WORKER_SOURCE, GUARDIAN_SOURCE])
@pytest.mark.parametrize("has_message_id", [True, False])
def test_new_adapter_rereads_header_after_a_real_checkpoint(
    tmp_path: Path, source: JsonValue, has_message_id: bool
) -> None:
    root = tmp_path / "codex"
    _write(
        root / "rollout-resume.jsonl",
        [
            _header(source=source),
            _message("First request", message_id="first" if has_message_id else None),
            _message("Future request", message_id="second" if has_message_id else None),
            _message("Visible answer", message_id="third", role="assistant"),
        ],
    )
    full = _evidence(_scan(_adapter(root)))
    first = _evidence(_scan(_adapter(root), ScanOptions(max_messages=1)))
    assert len(first) == 1
    cursor = first[0].cursor
    resumed = _evidence(_scan(_adapter(root), ScanOptions(cursors={cursor.file_key: cursor})))

    assert [item.evidence.verbatim for item in resumed] == ["Future request", "Visible answer"]
    assert [item.evidence for item in resumed] == [item.evidence for item in full[1:]]
    assert {item.evidence.workspace for item in resumed} == {
        opaque_workspace_id("codex", WORKSPACE)
    }
    expected_user = WrittenBy.PERSON if source == "cli" else WrittenBy.UNKNOWN
    assert [item.evidence.written_by for item in resumed] == [expected_user, WrittenBy.AGENT]
    assert all(
        item.evidence.origin_meta[EvidenceOrigin.FILE].source_version == "0.153.4"
        for item in resumed
    )
    end_cursor = resumed[-1].cursor
    assert not _evidence(
        _scan(_adapter(root), ScanOptions(cursors={end_cursor.file_key: end_cursor}))
    )


@pytest.mark.parametrize(
    "source",
    [
        WORKER_SOURCE,
        GUARDIAN_SOURCE,
        {"subagent": "review"},
        {"subagent": {"future_worker": {"depth": 2}}},
        {"subagent": "future_worker"},
        {"subagent": None},
        {"future_machine": {}},
        "future_source",
    ],
)
def test_machine_and_unknown_session_sources_do_not_establish_human_or_agent_sender(
    tmp_path: Path, source: JsonValue
) -> None:
    root = tmp_path / "codex"
    _write(
        root / "rollout-worker.jsonl",
        [
            _header(source=source),
            _message("Initial request with no sender attribution"),
            _message("A later request could come from either author", message_id="future"),
        ],
    )

    records = _evidence(_scan(_adapter(root)))

    assert len(records) == 2
    assert [item.evidence.written_by for item in records] == [WrittenBy.UNKNOWN] * 2
    for item in records:
        metadata = item.evidence.origin_meta[EvidenceOrigin.FILE].raw_meta
        header = metadata["session_meta"]
        assert isinstance(header, dict)
        assert header["source"] == source
        assert header["parent_thread_id"] == "parent-thread"


@pytest.mark.parametrize("location", ["record", "payload"])
@pytest.mark.parametrize("written_by", list(WrittenBy))
def test_explicit_per_record_author_is_not_inferred_from_session_source(
    tmp_path: Path, location: str, written_by: WrittenBy
) -> None:
    root = tmp_path / "codex"
    record = _message("Explicitly attributed input")
    target = record if location == "record" else record["payload"]
    assert isinstance(target, dict)
    target["written_by"] = written_by.value
    _write(
        root / "rollout-author.jsonl",
        [
            _header(source=WORKER_SOURCE),
            record,
            _message("Unattributed follow-up", message_id="next"),
        ],
    )

    records = _evidence(_scan(_adapter(root)))

    assert [item.evidence.written_by for item in records] == [written_by, WrittenBy.UNKNOWN]
    provenance = records[0].evidence.origin_meta[EvidenceOrigin.FILE].raw_meta
    assert provenance["message_provenance"] == {location: {"written_by": written_by.value}}


@pytest.mark.parametrize("author", ["future_author", {"kind": "human"}, None])
def test_unknown_explicit_author_is_retained_but_not_promoted(
    tmp_path: Path, author: JsonValue
) -> None:
    root = tmp_path / "codex"
    _write(
        root / "rollout-author.jsonl",
        [_header(), _message("Unknown sender", attributes={"written_by": author})],
    )

    record = _evidence(_scan(_adapter(root)))[0].evidence

    assert record.verbatim == "Unknown sender"
    assert record.written_by is WrittenBy.UNKNOWN
    assert record.origin_meta[EvidenceOrigin.FILE].raw_meta["message_provenance"] == {
        "payload": {"written_by": author}
    }


def test_conflicting_record_authors_are_unknown(tmp_path: Path) -> None:
    root = tmp_path / "codex"
    record = _message("Conflicting attribution", attributes={"written_by": "person"})
    record["written_by"] = "agent"
    _write(root / "rollout-conflict.jsonl", [_header(source=WORKER_SOURCE), record])

    evidence = _evidence(_scan(_adapter(root)))[0].evidence

    assert evidence.written_by is WrittenBy.UNKNOWN


@pytest.mark.parametrize("source", [WORKER_SOURCE, GUARDIAN_SOURCE, {"subagent": "future"}])
def test_machine_transcript_never_sends_inner_query_to_shared_wrapper_stripper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: JsonValue
) -> None:
    from one_memory.imports.sources import codex

    root = tmp_path / "codex"
    text = (
        "The following is the Codex agent history whose request action you are assessing.\n"
        ">>> TRANSCRIPT START\n"
        "[1] user: quoted <user_query>inner text</user_query> inside a past transcript.\n"
        ">>> TRANSCRIPT END\n"
        "Assess the planned action."
    )
    _write(root / "rollout-guardian.jsonl", [_header(source=source), _message(text)])

    def forbidden_strip(value: str) -> str | None:
        pytest.fail("Machine transcripts must bypass the shared human-wrapper stripper")

    monkeypatch.setattr(codex, "strip_host_wrappers", forbidden_strip)
    record = _evidence(_scan(_adapter(root)))[0].evidence

    assert record.verbatim == text
    assert record.written_by is WrittenBy.UNKNOWN


@pytest.mark.parametrize("source", ["cli", "vscode", "mcp", "exec"])
def test_ordinary_human_turns_remain_human_even_when_discussing_machine_sessions(
    tmp_path: Path, source: JsonValue
) -> None:
    root = tmp_path / "codex"
    texts = [
        "Explain how source.subagent and guardian sessions work.",
        "I wrote this request for the worker, and I am changing it now.",
        "Quoted guardian assessment: >>> TRANSCRIPT START; no machine provenance.",
    ]
    _write(
        root / "rollout-human.jsonl",
        [_header(source=source)]
        + [_message(text, message_id=str(index)) for index, text in enumerate(texts)],
    )

    records = _evidence(_scan(_adapter(root)))

    assert [item.evidence.verbatim for item in records] == texts
    assert [item.evidence.written_by for item in records] == [WrittenBy.PERSON] * len(texts)


@pytest.mark.parametrize("same_native_session", [True, False])
@pytest.mark.parametrize("has_message_id", [True, False])
def test_rollover_metadata_does_not_change_filename_identity_or_deduplicate_files(
    tmp_path: Path, same_native_session: bool, has_message_id: bool
) -> None:
    root = tmp_path / "codex"
    for filename, native_id in [
        ("rollout-first", "native-thread"),
        ("rollout-second", "native-thread" if same_native_session else "other-thread"),
    ]:
        _write(
            root / f"{filename}.jsonl",
            [
                _header(native_id=native_id),
                _message("Same message", message_id="same-id" if has_message_id else None),
            ],
        )

    current = _evidence(_scan(_adapter(root)))
    legacy = _adapter(root)
    legacy.header_selector = None
    without_header = _evidence(_scan(legacy))

    assert len(current) == len(without_header) == 2
    assert {item.evidence.conversation_id for item in current} == {
        "rollout-first",
        "rollout-second",
    }
    assert len({item.evidence.evidence_id for item in current}) == 2
    # Native message IDs bind identity to source metadata. Without one,
    # derived identity deliberately ignores workspace metadata so hook and
    # file ingestion can converge on the same evidence.
    current_keys = [item.evidence.idempotency_key for item in current]
    legacy_keys = [item.evidence.idempotency_key for item in without_header]
    current_ids = [item.evidence.evidence_id for item in current]
    legacy_ids = [item.evidence.evidence_id for item in without_header]
    if has_message_id:
        assert current_keys != legacy_keys
        assert current_ids != legacy_ids
    else:
        assert current_keys == legacy_keys
        assert current_ids == legacy_ids
    assert len({item.evidence.evidence_id for item in without_header}) == 2
    assert {
        item.evidence.conversation_id: item.evidence.origin_meta[EvidenceOrigin.FILE].raw_meta[
            "native_session_id"
        ]
        for item in current
    } == {
        "rollout-first": "native-thread",
        "rollout-second": "native-thread" if same_native_session else "other-thread",
    }


def test_headerless_files_keep_legacy_metadata_and_adapter_version(tmp_path: Path) -> None:
    root = tmp_path / "codex"
    _write(root / "rollout-old.jsonl", [_message("Ordinary legacy user")])

    event = _evidence(_scan(_adapter(root, source_version="configured-version")))[0]

    assert event.evidence.written_by is WrittenBy.PERSON
    assert event.evidence.workspace is None
    origin = event.evidence.origin_meta[EvidenceOrigin.FILE]
    assert origin.source_version == "configured-version"
    assert origin.raw_meta == {
        "file_key": event.cursor.file_key,
        "record_type": "response_item.message",
    }


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("immutable", [False, True])
def test_header_and_resumed_records_use_the_same_explicit_immutable_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, compressed: bool, immutable: bool
) -> None:
    from one_memory.imports.sources import common

    root = tmp_path / "codex"
    root.mkdir()
    body = "\n".join(
        json.dumps(record)
        for record in [
            _header(),
            _message("Complete first message", message_id="first"),
            _message("Final message without newline", message_id="final"),
        ]
    ).encode()
    suffix = ".jsonl.zstd" if compressed else ".jsonl"
    transcript = root / f"rollout-frozen{suffix}"
    transcript.write_bytes(zstandard.ZstdCompressor().compress(body) if compressed else body)
    before = transcript.read_bytes()
    reader_name = "read_zstd_jsonl" if compressed else "read_jsonl"
    original_reader = getattr(common, reader_name)
    calls: list[tuple[bool, str | None]] = []

    def observe_reader(
        source_file: AuthorizedSourceFile,
        *,
        checkpoint: str | None = None,
        max_bytes: int | None = None,
        immutable: bool = False,
    ) -> Generator[RawReadEvent, None, None]:
        calls.append((immutable, checkpoint))
        yield from original_reader(
            source_file, checkpoint=checkpoint, max_bytes=max_bytes, immutable=immutable
        )

    monkeypatch.setattr(common, reader_name, observe_reader)
    adapter = _adapter(root)
    adapter.suffixes = frozenset({".jsonl", ".zstd"})
    first = _evidence(_scan(adapter, ScanOptions(max_messages=1, immutable=immutable)))
    assert len(first) == 1
    assert calls == [(immutable, None), (immutable, None)]
    assert first[0].evidence.workspace == opaque_workspace_id("codex", WORKSPACE)
    cursor = first[0].cursor
    calls.clear()

    resumed = _evidence(
        _scan(adapter, ScanOptions(cursors={cursor.file_key: cursor}, immutable=immutable))
    )

    # The header was cached from the first authorized read. Resuming should
    # read only from the checkpoint, with the same immutable mode.
    assert calls == (
        [(immutable, None), (immutable, cursor.checkpoint)]
        if immutable
        else [(immutable, cursor.checkpoint)]
    )
    assert [item.evidence.verbatim for item in resumed] == (
        ["Final message without newline"] if immutable else []
    )
    assert all(item.evidence.workspace == first[0].evidence.workspace for item in resumed)
    assert transcript.read_bytes() == before


def test_default_live_mode_still_defers_unfinished_tail(tmp_path: Path) -> None:
    root = tmp_path / "codex"
    root.mkdir()
    (root / "rollout-live.jsonl").write_text(json.dumps(_message("Unfinished")), encoding="utf-8")

    assert not _evidence(_scan(_adapter(root)))


@pytest.mark.parametrize(
    "opening", [{"type": "event_msg", "payload": {}}, {"type": "session_meta", "payload": []}]
)
def test_invalid_or_nonopening_session_metadata_does_not_leak_between_files(
    tmp_path: Path, opening: dict[str, JsonValue]
) -> None:
    root = tmp_path / "codex"
    _write(root / "rollout-a.jsonl", [_header(source=WORKER_SOURCE), _message("Machine input")])
    _write(
        root / "rollout-b.jsonl",
        [opening, _header(source=GUARDIAN_SOURCE), _message("Human input")],
    )

    records = sorted(
        _evidence(_scan(_adapter(root))), key=lambda item: item.evidence.conversation_id
    )

    assert [item.evidence.verbatim for item in records] == ["Machine input", "Human input"]
    assert records[0].evidence.written_by is WrittenBy.UNKNOWN
    assert records[1].evidence.written_by is WrittenBy.PERSON
    assert records[1].evidence.workspace is None
    assert "native_session_id" not in records[1].evidence.origin_meta[EvidenceOrigin.FILE].raw_meta


def test_session_id_fallback_is_only_metadata_and_missing_version_uses_configured_value(
    tmp_path: Path,
) -> None:
    root = tmp_path / "codex"
    _write(
        root / "rollout-fallback.jsonl",
        [
            {
                "type": "session_meta",
                "payload": {"session_id": "older-native-id", "cwd": WORKSPACE},
            },
            _message("Visible request"),
        ],
    )

    record = _evidence(_scan(_adapter(root, source_version="configured")))[0].evidence

    assert record.conversation_id == "rollout-fallback"
    assert record.workspace == opaque_workspace_id("codex", WORKSPACE)
    assert record.origin_meta[EvidenceOrigin.FILE].source_version == "configured"
    assert (
        record.origin_meta[EvidenceOrigin.FILE].raw_meta["native_session_id"] == "older-native-id"
    )
