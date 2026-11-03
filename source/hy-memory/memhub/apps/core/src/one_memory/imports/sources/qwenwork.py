from pathlib import PurePosixPath

from pydantic import JsonValue

from one_memory.imports.access import AuthorizedSourceRoot, safe_project_label
from one_memory.imports.adapters import (
    ScanIssueCode,
    SourceCapabilities,
    SourceDescriptor,
    StorageKind,
)
from one_memory.imports.models import WrittenBy
from one_memory.imports.sources.common import (
    JsonlSourceAdapter,
    ParsedMessage,
    ParsedSkip,
    SourceRecordContext,
)
from one_memory.imports.sources.parsing import (
    as_record,
    first_string,
    parse_timestamp,
    strip_host_wrappers,
    text_content,
)

QWENWORK_DESCRIPTOR = SourceDescriptor(
    source_id="qwenwork",
    display_name="Qwen Work",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=True,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


def create_qwenwork_adapter(
    grant: AuthorizedSourceRoot,
    *,
    descriptor: SourceDescriptor = QWENWORK_DESCRIPTOR,
    source_version: str | None = None,
) -> JsonlSourceAdapter:
    return JsonlSourceAdapter(
        descriptor=descriptor,
        grant=grant,
        parser=parse_qwenwork_record,
        source_version=source_version,
    )


def parse_qwenwork_record(
    record: dict[str, JsonValue],
    context: SourceRecordContext,
) -> ParsedMessage | ParsedSkip:
    message = as_record(record.get("message"))
    role = first_string(
        message.get("role") if message else None,
        record.get("type"),
    )
    conversation_id = (
        first_string(record.get("sessionId"), record.get("conversationId"))
        or PurePosixPath(context.relative_path).stem
    )
    if record.get("isSidechain") is True:
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    if message is None:
        return ParsedSkip(
            reason_code=ScanIssueCode.UNKNOWN_RECORD,
            conversation_id=conversation_id,
        )
    origin = as_record(record.get("origin"))
    if role == "user" and origin is not None and origin.get("kind") != "human":
        # Qwen Work states authorship outright. Pi reaches the same conclusion
        # from its session's working directory and now takes the same action:
        # a machine-written prompt wearing the user's role is not imported
        # (decision D-17).
        return ParsedSkip(
            reason_code=ScanIssueCode.NOT_WRITTEN_BY_PERSON,
            conversation_id=conversation_id,
        )
    if role == "system":
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    if role not in {"user", "assistant"}:
        return ParsedSkip(
            reason_code=ScanIssueCode.TOOL_CONTENT_EXCLUDED,
            conversation_id=conversation_id,
        )
    text = text_content(
        message.get("content"),
        allowed_block_types=frozenset({"text"}),
    )
    if not text:
        return ParsedSkip(
            reason_code=ScanIssueCode.NO_TEXT,
            conversation_id=conversation_id,
        )
    text = strip_host_wrappers(text)
    if not text:
        return ParsedSkip(
            reason_code=ScanIssueCode.INTERNAL_REASONING_EXCLUDED,
            conversation_id=conversation_id,
        )
    workspace = first_string(record.get("cwd"))
    return ParsedMessage(
        conversation_id=conversation_id,
        message_id=first_string(
            record.get("uuid"),
            record.get("id"),
            record.get("messageId"),
        ),
        role=role,
        written_by=WrittenBy.PERSON if role == "user" else WrittenBy.AGENT,
        created_at=parse_timestamp(record.get("timestamp") or message.get("timestamp")),
        verbatim=text,
        workspace=workspace,
        project=safe_project_label(workspace),
        record_type="message",
    )
