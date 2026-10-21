import os
from pathlib import PurePosixPath

from pydantic import JsonValue

from one_memory.imports.access import AuthorizedSourceRoot
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
    followed_by_tool,
)
from one_memory.imports.sources.parsing import (
    as_record,
    conversation_from_relative_path,
    first_string,
    parse_timestamp,
    strip_host_wrappers,
    text_content,
    tool_blocks_evidence,
)


def subagent_trace_enabled() -> bool:
    """Whether a sub agent's own transcript is imported at all.

    The privacy-preserving option is not to send the sub-agent trace at all.
    On by default — the trace is ordinary user-assistant data and the sub
    agent's work is part of what happened. Off skips it at the scan, so
    nothing downstream has to know.
    """
    return os.environ.get("ONE_MEMORY_IMPORT_SUBAGENT_TRACE", "1").strip() not in {
        "0",
        "false",
        "off",
    }


def _sidechain_conversation_id(
    conversation_id: str,
    record: dict[str, JsonValue],
    context: SourceRecordContext,
) -> str:
    """Which conversation a sidechain record belongs to.

    One main session can delegate to several sub agents, and every one of them
    needs its own conversation — one shared suffix would splice them all into a
    single thread and hand HY a transcript that never happened.

    `agentId` is the stable grouping key: it is present on every sidechain
    record in a real transcript and repeats for the whole delegation. Where it
    is missing, a `subagents/` transcript is already its own file, so the file
    names it; otherwise the record's own id keeps at least this record apart.

    Known limit: without `agentId`, every sidechain record in one file falls
    into a single `{session}:subagent` conversation. Two delegations that both
    lack it would be spliced together. No real transcript does this — the
    field is always there — so it is left as one conversation rather than
    guessed at from `parentUuid` chains.
    """
    agent = first_string(record.get("agentId"))
    if agent:
        return f"{conversation_id}:subagent:{agent}"
    if "subagents" in PurePosixPath(context.relative_path).parts:
        return (
            f"{conversation_id}:subagent:{conversation_from_relative_path(context.relative_path)}"
        )
    return f"{conversation_id}:subagent"


#: Anthropic content blocks: calls in assistant content, results in user content.
TOOL_BLOCKS = frozenset({"tool_use", "tool_result"})

CLAUDE_CODE_DESCRIPTOR = SourceDescriptor(
    source_id="claude-code",
    display_name="Claude Code",
    storage_kinds=frozenset({StorageKind.JSONL}),
    capabilities=SourceCapabilities(
        can_append=True,
        can_observe_edits=True,
        can_observe_deletes=False,
        can_reconcile_complete_set=False,
    ),
)


def create_claude_code_adapter(
    grant: AuthorizedSourceRoot,
    *,
    source_version: str | None = None,
) -> JsonlSourceAdapter:
    return JsonlSourceAdapter(
        descriptor=CLAUDE_CODE_DESCRIPTOR,
        grant=grant,
        parser=parse_claude_code_record,
        source_version=source_version,
    )


def parse_claude_code_record(
    record: dict[str, JsonValue],
    context: SourceRecordContext,
) -> ParsedMessage | ParsedSkip:
    record_type = first_string(record.get("type"))
    if record_type not in {"user", "assistant"}:
        return ParsedSkip(ScanIssueCode.UNKNOWN_RECORD)
    message = as_record(record.get("message"))
    if message is None:
        return ParsedSkip(ScanIssueCode.UNKNOWN_RECORD)
    content = text_content(
        message.get("content"),
        allowed_block_types=frozenset({"text"}),
    )
    if not content:
        tool_text = tool_blocks_evidence(message.get("content"), block_types=TOOL_BLOCKS)
        if tool_text is not None:
            # A tool_result arrives in a `user` record; the person did not write it.
            return ParsedMessage(
                conversation_id=first_string(record.get("sessionId"))
                or conversation_from_relative_path(context.relative_path),
                message_id=first_string(record.get("uuid")),
                role="tool",
                written_by=WrittenBy.TOOL,
                created_at=parse_timestamp(record.get("timestamp")),
                verbatim=tool_text,
                workspace=first_string(record.get("cwd")),
                record_type=f"{record_type}.tool",
            )
        reason = (
            ScanIssueCode.TOOL_CONTENT_EXCLUDED if record_type == "user" else ScanIssueCode.NO_TEXT
        )
        return ParsedSkip(reason)
    content = strip_host_wrappers(content)
    if not content:
        return ParsedSkip(ScanIssueCode.INTERNAL_REASONING_EXCLUDED)
    conversation_id = first_string(record.get("sessionId")) or (
        conversation_from_relative_path(context.relative_path)
    )
    workspace = first_string(record.get("cwd"))
    is_sidechain = (
        record.get("isSidechain") is True
        or "subagents" in PurePosixPath(context.relative_path).parts
    )
    if is_sidechain and not subagent_trace_enabled():
        return ParsedSkip(ScanIssueCode.SUBAGENT_TRACE_DISABLED)
    has_machine_result = (
        record.get("toolUseResult") is not None or message.get("toolUseResult") is not None
    )
    if record_type == "assistant" or is_sidechain:
        written_by = WrittenBy.AGENT
    elif has_machine_result:
        written_by = WrittenBy.UNKNOWN
    else:
        written_by = WrittenBy.PERSON
    if is_sidechain:
        # D98: a sidechain is a sub agent's own transcript, written into the
        # same file as the main session. Keeping it in the main conversation
        # hands HY one long turn sequence whose questions are not the
        # person's, and dropping it loses the sub agent's work. It gets a
        # conversation of its own.
        conversation_id = _sidechain_conversation_id(conversation_id, record, context)
    return followed_by_tool(
        ParsedMessage(
            conversation_id=conversation_id,
            message_id=first_string(record.get("uuid")),
            role=record_type,
            written_by=written_by,
            created_at=parse_timestamp(record.get("timestamp")),
            verbatim=content,
            workspace=workspace,
            record_type=record_type,
        ),
        tool_blocks_evidence(message.get("content"), block_types=TOOL_BLOCKS),
    )
