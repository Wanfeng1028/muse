import asyncio
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import JsonValue

from one_memory.imports.access import AuthorizedSourceRoot
from one_memory.imports.adapters import ScanIssueCode, ScannedEvidence, ScanOptions, ScanSkip
from one_memory.imports.models import EvidenceOrigin, WrittenBy
from one_memory.imports.sources.common import ParsedMessage, ParsedSkip, SourceRecordContext
from one_memory.imports.sources.workbuddy import create_workbuddy_adapter, parse_workbuddy_record

CONTEXT = SourceRecordContext(
    file_key="fixture", relative_path="project/session.jsonl", ordinal="1"
)
QUERY = "Keep the exact saved task, including x < 5 and `<user_query>literal</user_query>`."
AUTOMATION = (
    '<system-reminder data-role="user-context">\n'
    "<user_info>Host context</user_info>\n"
    "<additional_data>Host clock</additional_data>\n"
    "<automation_system_reminder>\n"
    "This is a scheduled automation task. The task instructions are provided in <user_query>.\n"
    "Host-only execution instructions.\n"
    "</automation_system_reminder>\n"
    "</system-reminder>\n"
    f"<user_query>{QUERY}</user_query>"
)
NOTIFICATION = (
    "<task-notification>\n"
    "<task-id>task-1</task-id>\n"
    "<tool-use-id>tool-1</tool-use-id>\n"
    "<status>completed</status>\n"
    "<summary>Background command completed.</summary>\n"
    "</task-notification>\n"
    "Host follow-up instructions with <user_query>an example</user_query>."
)
COMPACTION = (
    "<cb_summary>\nSummary of the conversation so far:\n"
    "<previous_user_message><user_query>Original request</user_query></previous_user_message>\n"
    "<previous_assistant_message>Earlier reply</previous_assistant_message>\n"
    "<previous_user_message><user_query>Later request</user_query></previous_user_message>\n"
    "</cb_summary>"
)
COMPACTION_FLAGS: dict[str, JsonValue] = {
    "skipRun": False,
    "compactType": "pre-message-auto",
    "isCompacted": True,
    "isSummary": False,
    "agent": "cli",
}


def message(
    text: str,
    *,
    provider: dict[str, JsonValue] | None = None,
    message_id: str = "message-1",
    timestamp: str = "2026-09-01T01:00:00Z",
) -> dict[str, JsonValue]:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
        "id": message_id,
        "sessionId": "session",
        "timestamp": timestamp,
        "providerData": provider or {"agent": "cli"},
    }


def test_automation_preserves_query_without_claiming_fresh_human_authorship() -> None:
    record = message(AUTOMATION)
    before = deepcopy(record)
    result = parse_workbuddy_record(record, CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == QUERY
    assert result.role == "user"
    assert result.written_by is WrittenBy.UNKNOWN
    assert result.record_type == "message.scheduled_automation"
    assert result.message_id == "message-1"
    assert result.created_at == datetime(2026, 9, 1, 1, tzinfo=UTC)
    assert record == before


@pytest.mark.parametrize(
    "opening",
    [
        "<system-reminder data-role='user-context'>",
        '<system-reminder data-extra="host" data-role="user-context">',
        '<system-reminder data-role = "user-context" data-extra="host">',
    ],
)
def test_automation_context_attributes_do_not_depend_on_order_or_quote_style(opening: str) -> None:
    text = AUTOMATION.replace('<system-reminder data-role="user-context">', opening)
    result = parse_workbuddy_record(message(text), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == QUERY
    assert result.written_by is WrittenBy.UNKNOWN


def test_quoted_full_automation_envelope_is_not_scheduled_provenance() -> None:
    text = f"Please explain this literal host envelope:\n{AUTOMATION}"
    result = parse_workbuddy_record(message(text), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == text
    assert result.written_by is WrittenBy.PERSON
    assert result.record_type == "message"


def test_minified_automation_envelope_retains_scheduled_provenance() -> None:
    text = AUTOMATION.replace(">\n<", "><")
    result = parse_workbuddy_record(message(text), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == QUERY
    assert result.written_by is WrittenBy.UNKNOWN
    assert result.record_type == "message.scheduled_automation"


def test_ambiguous_query_preserves_raw_text_without_losing_known_automation_origin() -> None:
    text = AUTOMATION.replace(QUERY, "Explain the literal <user_query> opening tag.")
    result = parse_workbuddy_record(message(text), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == text
    assert result.written_by is WrittenBy.UNKNOWN
    assert result.record_type == "message.scheduled_automation"


@pytest.mark.parametrize("is_meta", [False, True])
@pytest.mark.parametrize(
    "text",
    [
        "Please create a scheduled automation task; this is my request.",
        "Explain `<automation_system_reminder>This is a scheduled automation task."
        "</automation_system_reminder>`.",
        f"Explain this notification:\n{NOTIFICATION}",
        f"<user_query>I am quoting this notification:\n{NOTIFICATION}</user_query>",
        "<user_query><automation_system_reminder>This is a scheduled automation task."
        "</automation_system_reminder> is a quoted example.</user_query>",
    ],
)
def test_quotations_do_not_override_native_authorship_metadata(text: str, is_meta: bool) -> None:
    result = parse_workbuddy_record(
        message(text, provider={"isMeta": is_meta, "agent": "cli"}), CONTEXT
    )
    assert isinstance(result, ParsedMessage)
    expected = text.removeprefix("<user_query>").removesuffix("</user_query>")
    assert result.verbatim == expected
    assert result.written_by is (WrittenBy.UNKNOWN if is_meta else WrittenBy.PERSON)
    assert result.record_type == "message"


def test_meta_notification_uses_existing_tool_exclusion_and_preserves_raw_record() -> None:
    record = message(NOTIFICATION, provider={"isMeta": True, "agent": "cli"})
    before = deepcopy(record)
    result = parse_workbuddy_record(record, CONTEXT)
    assert result == ParsedSkip(ScanIssueCode.TOOL_CONTENT_EXCLUDED, conversation_id="session")
    assert record == before


@pytest.mark.parametrize("provider", [{"agent": "cli"}, {"agent": "cli", "isMeta": False}])
def test_task_notification_quotation_without_meta_flag_is_not_reclassified(provider) -> None:
    result = parse_workbuddy_record(message(NOTIFICATION, provider=provider), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == NOTIFICATION
    assert result.written_by is WrittenBy.PERSON


def test_unrecognized_meta_flag_does_not_prove_human_or_agent_authorship() -> None:
    result = parse_workbuddy_record(message("Ordinary text", provider={"isMeta": True}), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.written_by is WrittenBy.UNKNOWN
    assert result.verbatim == "Ordinary text"


def test_attributed_error_recovery_reminder_is_not_conversation_text() -> None:
    text = (
        '<system-reminder data-role="error-recovery">'
        "Network error occurred, please continue</system-reminder>"
    )
    result = parse_workbuddy_record(message(text, provider={"isMeta": True}), CONTEXT)
    assert result == ParsedSkip(ScanIssueCode.NO_TEXT)
    quoted = parse_workbuddy_record(message(f"Explain `{text}`"), CONTEXT)
    assert isinstance(quoted, ParsedMessage)
    assert quoted.verbatim == f"Explain `{text}`"
    assert quoted.written_by is WrittenBy.PERSON


@pytest.mark.parametrize("has_original", [False, True])
def test_compaction_replay_does_not_invent_original_identity_or_timestamp(
    has_original: bool,
) -> None:
    records = []
    if has_original:
        records.append(
            message("Original request", message_id="original", timestamp="2026-09-01T00:00:00Z")
        )
    records.append(message(COMPACTION, provider=COMPACTION_FLAGS, message_id="compaction"))
    before = deepcopy(records)
    results = [parse_workbuddy_record(record, CONTEXT) for record in records]
    assert results[-1] == ParsedSkip(
        ScanIssueCode.INTERNAL_REASONING_EXCLUDED, conversation_id="session"
    )
    if has_original:
        original = results[0]
        assert isinstance(original, ParsedMessage)
        assert original.message_id == "original"
        assert original.created_at == datetime(2026, 9, 1, tzinfo=UTC)
        assert original.verbatim == "Original request"
        assert original.written_by is WrittenBy.PERSON
    assert records == before


@pytest.mark.parametrize(
    ("text", "provider"),
    [
        ("Ordinary request", COMPACTION_FLAGS),
        (f"Explain this historical summary:\n{COMPACTION}", COMPACTION_FLAGS),
        (COMPACTION, {"isCompacted": False}),
    ],
)
def test_compaction_requires_both_explicit_metadata_and_outer_summary(text, provider) -> None:
    result = parse_workbuddy_record(message(text, provider=provider), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.verbatim == text
    assert result.written_by is WrittenBy.PERSON


@pytest.mark.parametrize("provider", [{"isSubAgent": True}, {"isTeamMember": True}])
def test_existing_explicit_agent_authorship_remains_intact(provider) -> None:
    result = parse_workbuddy_record(message("Delegated task", provider=provider), CONTEXT)
    assert isinstance(result, ParsedMessage)
    assert result.written_by is WrittenBy.AGENT


@pytest.mark.parametrize(
    "record_type",
    ["reasoning", "file-history-snapshot", "ai-title", "summary"],
)
def test_real_workbuddy_metadata_records_never_become_conversation_evidence(
    record_type: str,
) -> None:
    """Real WorkBuddy transcripts carry these beside message records.

    They have no conversation role and carry host metadata or model state, so
    the parser must skip them as unknown rather than treating their payload as
    something a person said.
    """
    record: dict[str, JsonValue] = {
        "type": record_type,
        "timestamp": 1786983187628,
        "sessionId": "session",
        "cwd": "/private/tmp/project",
    }
    if record_type == "reasoning":
        record["rawContent"] = [{"type": "reasoning_text", "text": "internal model reasoning"}]
    elif record_type == "summary":
        record["summary"] = "host-generated conversation summary"
    elif record_type == "ai-title":
        record["aiTitle"] = "host-generated title"
    else:
        record["snapshot"] = {"messageId": "message-1", "trackedFileBackups": {}}

    assert parse_workbuddy_record(record, CONTEXT) == ParsedSkip(ScanIssueCode.UNKNOWN_RECORD)


def test_real_workbuddy_function_result_is_tool_evidence_not_human_text() -> None:
    result = parse_workbuddy_record(
        {
            "id": "result-1",
            "timestamp": 1786983188663,
            "type": "function_call_result",
            "name": "Write",
            "callId": "call-1",
            "status": "completed",
            "output": {"type": "text", "text": "Successfully created and wrote to new file"},
            "sessionId": "session",
            "cwd": "/private/tmp/project",
        },
        CONTEXT,
    )
    assert isinstance(result, ParsedMessage)
    assert result.role == "tool"
    assert result.written_by is WrittenBy.TOOL
    assert result.verbatim.startswith("[Write]")
    assert "Successfully created and wrote to new file" in result.verbatim


def test_adapter_receipts_and_resumption_preserve_inputs_and_originals(tmp_path: Path) -> None:
    root = tmp_path / "workbuddy"
    root.mkdir()
    source = root / "session.jsonl"
    records = [
        message("Original request", message_id="original", timestamp="2026-09-01T00:00:00Z"),
        message(COMPACTION, provider=COMPACTION_FLAGS, message_id="compaction"),
        message(AUTOMATION, message_id="automation"),
        message(NOTIFICATION, provider={"isMeta": True}, message_id="notification"),
    ]
    source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    before = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat())
    grant = AuthorizedSourceRoot.grant(
        source_id="workbuddy", root=root, user_confirmed=True, home=tmp_path / "other-home"
    )
    adapter = create_workbuddy_adapter(grant)

    async def scan(options: ScanOptions):
        return [event async for event in adapter.scan(options)]

    events = asyncio.run(scan(ScanOptions(cursors={})))
    evidence = [event.evidence for event in events if isinstance(event, ScannedEvidence)]
    skips = [event for event in events if isinstance(event, ScanSkip)]
    assert [item.message_id for item in evidence] == ["original", "automation"]
    assert [item.written_by for item in evidence] == [WrittenBy.PERSON, WrittenBy.UNKNOWN]
    assert [item.verbatim for item in evidence] == ["Original request", QUERY]
    assert evidence[0].created_at == datetime(2026, 9, 1, tzinfo=UTC)
    for item in evidence:
        legacy = item.model_copy(update={"written_by": WrittenBy.PERSON, "verbatim": "Legacy text"})
        assert item.evidence_id == legacy.evidence_id
    assert (
        evidence[1].origin_meta[EvidenceOrigin.FILE].raw_meta["record_type"]
        == "message.scheduled_automation"
    )
    assert len(skips) == 2
    assert skips[0].reason_code is ScanIssueCode.INTERNAL_REASONING_EXCLUDED
    assert skips[0].conversation_id == "session"
    assert skips[1].reason_code is ScanIssueCode.TOOL_CONTENT_EXCLUDED
    assert skips[1].conversation_id == "session"
    cursor = skips[1].cursor
    assert cursor is not None
    resumed = asyncio.run(scan(ScanOptions(cursors={cursor.file_key: cursor})))
    assert not any(isinstance(event, (ScannedEvidence, ScanSkip)) for event in resumed)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before[0]
    assert source.stat().st_mtime_ns == before[1].st_mtime_ns


def test_frozen_workbuddy_audit_copies_without_import_or_database_writes() -> None:
    audit_dir = os.environ.get("ONE_MEMORY_WORKBUDDY_AUDIT_DIR")
    if not audit_dir:
        pytest.skip("requires an explicitly authorized frozen WorkBuddy audit directory")
    audit = Path(audit_dir).resolve(strict=True)
    report = json.loads((audit / "REPORT.json").read_bytes())
    measured = json.loads((audit / "measurements.json").read_bytes())["sources"]["workbuddy"]
    census = json.loads((audit / "workbuddy-records.json").read_bytes())
    source_dir = audit.parent / "s13-real-four-import-v1" / "workbuddy"
    snapshot = Path(measured["snapshot_root"]).resolve(strict=True)
    assert snapshot.is_relative_to(source_dir / "import-snapshots")
    assert snapshot.name == "files"
    fingerprints = {
        source_dir / key: value
        for key, value in measured["input_fingerprints"].items()
        if key.startswith(f"import-snapshots/{snapshot.parent.name}/")
    }
    assert len(fingerprints) == measured["manifest"]["files"] + 1

    def check_frozen_inputs() -> None:
        for path, expected in fingerprints.items():
            assert path.resolve(strict=True).is_relative_to(snapshot.parent)
            stat = path.stat()
            actual = {
                "bytes": stat.st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
                "inode": stat.st_ino,
                "mode": stat.st_mode,
            }
            assert actual == expected, path.name

    findings = {
        item["evidence_id"]: (finding["id"], item)
        for finding in report["findings"]
        if finding["id"] in {"F01", "F02", "F05"}
        for item in finding["evidence"]
    }
    accepted = [item for item in census if item["native_kind"] == "evidence"]
    assert len(accepted) == 7539
    by_id = {item["evidence_id"]: item for item in accepted}
    observed: Counter[str] = Counter()
    check_frozen_inputs()
    try:
        for item in census:
            path = (snapshot / item["relative_path"]).resolve(strict=True)
            assert path.is_relative_to(snapshot)
            with path.open("rb") as stream:
                stream.seek(item["byte_start"])
                line = stream.read(item["byte_end"] - item["byte_start"])
            assert hashlib.sha256(line).hexdigest() == item["line_sha256"]
            raw = json.loads(line)
            raw_before = deepcopy(raw)
            context = SourceRecordContext(
                file_key=item["file_key"],
                relative_path=item["relative_path"],
                ordinal=f"{item['file_key']}:byte:{item['byte_end']}",
            )
            result = parse_workbuddy_record(raw, context)
            assert raw == raw_before
            if item["native_kind"] == "skip":
                assert isinstance(result, ParsedSkip), (item["relative_path"], item["line"])
                assert result.reason_code.value == item["native_reason"]
                observed["existing_skip"] += 1
                continue
            category, detail = findings.get(item["evidence_id"], ("unchanged", {}))
            blocks = raw.get("content", [])
            if (
                category == "unchanged"
                and raw.get("providerData", {}).get("isMeta") is True
                and len(blocks) == 1
                and blocks[0].get("type") == "input_text"
                and blocks[0]
                .get("text", "")
                .startswith('<system-reminder data-role="error-recovery">')
                and blocks[0]["text"].endswith("</system-reminder>")
            ):
                category = "host_error_recovery"
            observed[category] += 1
            if category == "host_error_recovery":
                assert result == ParsedSkip(ScanIssueCode.NO_TEXT), item["evidence_id"]
                continue
            if category == "F02":
                assert result == ParsedSkip(
                    ScanIssueCode.TOOL_CONTENT_EXCLUDED, item["conversation_id"]
                )
                continue
            if category == "F05":
                assert result == ParsedSkip(
                    ScanIssueCode.INTERNAL_REASONING_EXCLUDED, item["conversation_id"]
                )
                for original_id in detail["original_non_compaction_ids"]:
                    assert original_id in by_id and original_id not in findings
                continue
            assert isinstance(result, ParsedMessage), item["evidence_id"]
            actual_hash = hashlib.sha256(result.verbatim.encode()).hexdigest()
            if category == "F01":
                assert actual_hash == detail["query_sha256"], item["evidence_id"]
                assert result.written_by is WrittenBy.UNKNOWN
                assert result.record_type == "message.scheduled_automation"
            else:
                assert actual_hash == item["stored_sha256"], item["evidence_id"]
                assert result.written_by.value == item["written_by"], item["evidence_id"]
            assert result.message_id == raw["id"]
            assert result.conversation_id == item["conversation_id"]
            assert result.created_at == datetime.fromtimestamp(raw["timestamp"] / 1000, UTC)
        assert observed == {
            "F01": 110,
            "F02": 84,
            "F05": 5,
            "host_error_recovery": 24,
            "unchanged": 7316,
            "existing_skip": 45043,
        }
    finally:
        check_frozen_inputs()
